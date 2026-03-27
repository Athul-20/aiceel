"""
Universal Observability SDK - Drop-in logging, tracing, and monitoring for any Python project
Usage:
    from observability import trace, log, setup

    setup(service_name="my-app", backends=["file", "http://my-api.com"])

    @trace
    def my_function():
        log.info("Hello World")
"""

import atexit
import functools
import inspect
import json
import os
import threading
import time
import traceback as tb
import uuid
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional, Union


# ============================================================================
# CONFIGURATION & GLOBAL STATE
# ============================================================================

class Config:
    """Global configuration"""
    service_name: str = os.getenv("OBS_SERVICE_NAME", "app")
    environment: str = os.getenv("OBS_ENV", "production")
    backends: list[str] = []
    enabled: bool = True
    debug: bool = os.getenv("OBS_DEBUG", "false").lower() == "true"
    sample_rate: float = 1.0  # 0.0 to 1.0

config = Config()

# Thread-local storage for trace context
_context = threading.local()

# Active backends
_backends: list['Backend'] = []
_initialized = False


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class LogEvent:
    """Log event structure"""
    timestamp: str
    level: str
    message: str
    service: str
    environment: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    attributes: dict[str, Any] = None
    error: Optional[dict[str, Any]] = None

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class SpanEvent:
    """Trace span structure"""
    span_id: str
    trace_id: str
    name: str
    start_time: float
    end_time: Optional[float] = None
    duration_ms: Optional[float] = None
    parent_id: Optional[str] = None
    service: str = ""
    environment: str = ""
    status: str = "ok"
    attributes: dict[str, Any] = None
    error: Optional[dict[str, Any]] = None

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}


# ============================================================================
# BACKEND INTERFACE
# ============================================================================

class Backend:
    """Base backend class"""

    def send_log(self, event: LogEvent):
        """Send log event"""
        pass

    def send_span(self, span: SpanEvent):
        """Send span event"""
        pass

    def flush(self):
        """Flush any buffered data"""
        pass

    def close(self):
        """Close backend connection"""
        pass


class FileBackend(Backend):
    """File backend - writes to JSON files"""

    def __init__(self, path: str = "logs"):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.log_file = self.path / "app.jsonl"
        self.trace_file = self.path / "traces.jsonl"
        self._lock = threading.Lock()

    def send_log(self, event: LogEvent):
        with self._lock, open(self.log_file, 'a') as f:
            f.write(json.dumps(event.to_dict()) + '\n')

    def send_span(self, span: SpanEvent):
        with self._lock, open(self.trace_file, 'a') as f:
            f.write(json.dumps(span.to_dict()) + '\n')


class ConsoleBackend(Backend):
    """Console backend - pretty prints to stdout"""

    def __init__(self, colored: bool = True):
        self.colored = colored
        self.colors = {
            'DEBUG': '\033[36m',    # Cyan
            'INFO': '\033[32m',     # Green
            'WARNING': '\033[33m',  # Yellow
            'ERROR': '\033[31m',    # Red
            'CRITICAL': '\033[35m', # Magenta
            'RESET': '\033[0m'
        }

    def send_log(self, event: LogEvent):
        color = self.colors.get(event.level, '') if self.colored else ''
        reset = self.colors['RESET'] if self.colored else ''

        msg = f"{color}[{event.timestamp}] [{event.level}] {event.message}{reset}"
        if event.attributes:
            msg += f" | {json.dumps(event.attributes)}"
        if event.error:
            msg += f"\n{event.error.get('traceback', '')}"
        print(msg)

    def send_span(self, span: SpanEvent):
        if config.debug:
            print(f"[TRACE] {span.name} ({span.duration_ms:.2f}ms)")


class HTTPBackend(Backend):
    """HTTP backend - sends to remote API"""

    def __init__(self, endpoint: str, api_key: Optional[str] = None,
                 batch_size: int = 100, flush_interval: float = 5.0):
        import requests
        self.endpoint = endpoint.rstrip('/')
        self.session = requests.Session()
        self.session.headers['Content-Type'] = 'application/json'
        if api_key:
            self.session.headers['Authorization'] = f'Bearer {api_key}'

        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._buffer = []
        self._lock = threading.Lock()
        self._last_flush = time.time()

    def send_log(self, event: LogEvent):
        self._add_to_buffer('log', event.to_dict())

    def send_span(self, span: SpanEvent):
        self._add_to_buffer('span', span.to_dict())

    def _add_to_buffer(self, event_type: str, data: dict):
        with self._lock:
            self._buffer.append({'type': event_type, 'data': data})

            should_flush = (
                len(self._buffer) >= self.batch_size or
                time.time() - self._last_flush >= self.flush_interval
            )

            if should_flush:
                self._flush_buffer()

    def _flush_buffer(self):
        if not self._buffer:
            return

        batch = self._buffer.copy()
        self._buffer.clear()
        self._last_flush = time.time()

        try:
            self.session.post(
                f"{self.endpoint}/batch",
                json={'events': batch},
                timeout=5
            )
        except Exception as e:
            if config.debug:
                print(f"HTTPBackend error: {e}")

    def flush(self):
        with self._lock:
            self._flush_buffer()

    def close(self):
        self.flush()
        self.session.close()


class DatabaseBackend(Backend):
    """Database backend - supports PostgreSQL, MySQL, SQLite"""

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self._init_connection()
        self._init_tables()

    def _init_connection(self):
        if 'postgresql' in self.connection_string or 'postgres' in self.connection_string:
            import psycopg2
            self.conn = psycopg2.connect(self.connection_string)
            self.db_type = 'postgres'
        elif 'mysql' in self.connection_string:
            import pymysql
            # Parse connection string
            self.conn = pymysql.connect(host='localhost')  # Simplified
            self.db_type = 'mysql'
        elif 'sqlite' in self.connection_string or self.connection_string.endswith('.db'):
            import sqlite3
            db_path = self.connection_string.replace('sqlite:///', '')
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.db_type = 'sqlite'
        else:
            raise ValueError(f"Unsupported database: {self.connection_string}")

    def _init_tables(self):
        cursor = self.conn.cursor()

        # Logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS observability_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                level TEXT,
                message TEXT,
                service TEXT,
                environment TEXT,
                trace_id TEXT,
                span_id TEXT,
                attributes TEXT,
                error TEXT
            )
        """ if self.db_type == 'sqlite' else """
            CREATE TABLE IF NOT EXISTS observability_logs (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP,
                level VARCHAR(20),
                message TEXT,
                service VARCHAR(255),
                environment VARCHAR(50),
                trace_id VARCHAR(64),
                span_id VARCHAR(32),
                attributes JSONB,
                error JSONB
            )
        """)

        # Spans table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS observability_spans (
                span_id TEXT PRIMARY KEY,
                trace_id TEXT,
                name TEXT,
                start_time REAL,
                end_time REAL,
                duration_ms REAL,
                parent_id TEXT,
                service TEXT,
                environment TEXT,
                status TEXT,
                attributes TEXT,
                error TEXT
            )
        """ if self.db_type == 'sqlite' else """
            CREATE TABLE IF NOT EXISTS observability_spans (
                span_id VARCHAR(32) PRIMARY KEY,
                trace_id VARCHAR(64),
                name VARCHAR(255),
                start_time DOUBLE PRECISION,
                end_time DOUBLE PRECISION,
                duration_ms DOUBLE PRECISION,
                parent_id VARCHAR(32),
                service VARCHAR(255),
                environment VARCHAR(50),
                status VARCHAR(20),
                attributes JSONB,
                error JSONB
            )
        """)

        self.conn.commit()

    def send_log(self, event: LogEvent):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO observability_logs
            (timestamp, level, message, service, environment, trace_id, span_id, attributes, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """ if self.db_type == 'sqlite' else """
            INSERT INTO observability_logs
            (timestamp, level, message, service, environment, trace_id, span_id, attributes, error)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            event.timestamp,
            event.level,
            event.message,
            event.service,
            event.environment,
            event.trace_id,
            event.span_id,
            json.dumps(event.attributes) if event.attributes else None,
            json.dumps(event.error) if event.error else None
        ))
        self.conn.commit()

    def send_span(self, span: SpanEvent):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO observability_spans
            (span_id, trace_id, name, start_time, end_time, duration_ms, parent_id,
             service, environment, status, attributes, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """ if self.db_type == 'sqlite' else """
            INSERT INTO observability_spans
            (span_id, trace_id, name, start_time, end_time, duration_ms, parent_id,
             service, environment, status, attributes, error)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (span_id) DO UPDATE SET
                end_time = EXCLUDED.end_time,
                duration_ms = EXCLUDED.duration_ms,
                status = EXCLUDED.status,
                attributes = EXCLUDED.attributes,
                error = EXCLUDED.error
        """, (
            span.span_id,
            span.trace_id,
            span.name,
            span.start_time,
            span.end_time,
            span.duration_ms,
            span.parent_id,
            span.service,
            span.environment,
            span.status,
            json.dumps(span.attributes) if span.attributes else None,
            json.dumps(span.error) if span.error else None
        ))
        self.conn.commit()

    def close(self):
        self.conn.close()


# ============================================================================
# CORE FUNCTIONALITY
# ============================================================================

def _get_trace_id() -> Optional[str]:
    """Get current trace ID"""
    return getattr(_context, 'trace_id', None)


def _get_span_id() -> Optional[str]:
    """Get current span ID"""
    spans = getattr(_context, 'span_stack', [])
    return spans[-1].span_id if spans else None


def _set_trace_id(trace_id: str):
    """Set trace ID in context"""
    _context.trace_id = trace_id


def _push_span(span: SpanEvent):
    """Push span to context stack"""
    if not hasattr(_context, 'span_stack'):
        _context.span_stack = []
    _context.span_stack.append(span)


def _pop_span() -> Optional[SpanEvent]:
    """Pop span from context stack"""
    if not hasattr(_context, 'span_stack') or not _context.span_stack:
        return None
    return _context.span_stack.pop()


def _emit_log(level: str, message: str, attributes: Optional[dict] = None,
              error: Optional[Exception] = None):
    """Emit a log event to all backends"""
    if not config.enabled or not _backends:
        return

    error_dict = None
    if error:
        error_dict = {
            'type': type(error).__name__,
            'message': str(error),
            'traceback': tb.format_exc()
        }

    event = LogEvent(
        timestamp=datetime.utcnow().isoformat() + 'Z',
        level=level,
        message=message,
        service=config.service_name,
        environment=config.environment,
        trace_id=_get_trace_id(),
        span_id=_get_span_id(),
        attributes=attributes,
        error=error_dict
    )

    for backend in _backends:
        try:
            backend.send_log(event)
        except Exception as e:
            if config.debug:
                print(f"Backend error: {e}")


def _emit_span(span: SpanEvent):
    """Emit a span event to all backends"""
    if not config.enabled or not _backends:
        return

    for backend in _backends:
        try:
            backend.send_span(span)
        except Exception as e:
            if config.debug:
                print(f"Backend error: {e}")


# ============================================================================
# PUBLIC API - LOGGING
# ============================================================================

class Logger:
    """Logger interface"""

    @staticmethod
    def debug(message: str, **kwargs):
        """Log debug message"""
        _emit_log('DEBUG', message, kwargs)

    @staticmethod
    def info(message: str, **kwargs):
        """Log info message"""
        _emit_log('INFO', message, kwargs)

    @staticmethod
    def warning(message: str, **kwargs):
        """Log warning message"""
        _emit_log('WARNING', message, kwargs)

    @staticmethod
    def error(message: str, error: Optional[Exception] = None, **kwargs):
        """Log error message"""
        _emit_log('ERROR', message, kwargs, error)

    @staticmethod
    def critical(message: str, error: Optional[Exception] = None, **kwargs):
        """Log critical message"""
        _emit_log('CRITICAL', message, kwargs, error)


# Create global logger instance
log = Logger()


# ============================================================================
# PUBLIC API - TRACING
# ============================================================================

@contextmanager
def trace_context(name: str, **attributes):
    """
    Context manager for tracing a block of code.

    Usage:
        with trace_context("process_data", user_id=123):
            # your code here
            pass
    """
    trace_id = _get_trace_id()
    if not trace_id:
        trace_id = str(uuid.uuid4())
        _set_trace_id(trace_id)

    parent_span = _get_span_id()
    span = SpanEvent(
        span_id=str(uuid.uuid4())[:16],
        trace_id=trace_id,
        name=name,
        start_time=time.time(),
        parent_id=parent_span,
        service=config.service_name,
        environment=config.environment,
        attributes=attributes or {}
    )

    _push_span(span)

    try:
        yield span
        span.status = 'ok'
    except Exception as e:
        span.status = 'error'
        span.error = {
            'type': type(e).__name__,
            'message': str(e),
            'traceback': tb.format_exc()
        }
        raise
    finally:
        span.end_time = time.time()
        span.duration_ms = (span.end_time - span.start_time) * 1000
        _pop_span()
        _emit_span(span)


def trace(func: Optional[Callable] = None, *, name: Optional[str] = None,
          attributes: Optional[dict] = None):
    """
    Decorator for tracing functions.

    Usage:
        @trace
        def my_function(x, y):
            return x + y

        @trace(name="custom_name", attributes={"key": "value"})
        def another_function():
            pass
    """
    def decorator(f):
        span_name = name or f"{f.__module__}.{f.__qualname__}"

        @functools.wraps(f)
        def sync_wrapper(*args, **kwargs):
            attrs = (attributes or {}).copy()

            # Add function info
            attrs['function'] = f.__name__
            attrs['module'] = f.__module__

            # Add arguments if debug mode
            if config.debug:
                sig = inspect.signature(f)
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                attrs['arguments'] = {k: str(v) for k, v in bound.arguments.items()}

            with trace_context(span_name, **attrs):
                return f(*args, **kwargs)

        @functools.wraps(f)
        async def async_wrapper(*args, **kwargs):
            attrs = (attributes or {}).copy()
            attrs['function'] = f.__name__
            attrs['module'] = f.__module__

            if config.debug:
                sig = inspect.signature(f)
                bound = sig.bind(*args, **kwargs)
                bound.apply_defaults()
                attrs['arguments'] = {k: str(v) for k, v in bound.arguments.items()}

            with trace_context(span_name, **attrs):
                return await f(*args, **kwargs)

        if inspect.iscoroutinefunction(f):
            return async_wrapper
        return sync_wrapper

    if func is None:
        return decorator
    return decorator(func)


def start_trace(name: str, **attributes) -> str:
    """
    Manually start a trace. Returns trace_id.

    Usage:
        trace_id = start_trace("my_operation", user_id=123)
    """
    trace_id = str(uuid.uuid4())
    _set_trace_id(trace_id)
    log.info(f"Started trace: {name}", trace_id=trace_id, **attributes)
    return trace_id


def end_trace():
    """End the current trace"""
    trace_id = _get_trace_id()
    if trace_id:
        log.info("Ended trace", trace_id=trace_id)
        _context.trace_id = None
        _context.span_stack = []


# ============================================================================
# SETUP & INITIALIZATION
# ============================================================================

def setup(
    service_name: Optional[str] = None,
    environment: Optional[str] = None,
    backends: Optional[list[Union[str, Backend]]] = None,
    enabled: bool = True,
    debug: bool = False,
    sample_rate: float = 1.0,
    **backend_kwargs
):
    """
    Setup observability. Call this once at app startup.

    Args:
        service_name: Name of your service
        environment: Environment (dev, staging, prod)
        backends: List of backends - can be strings or Backend instances
            Strings: "console", "file", "file:path/to/logs",
                    "http://api.example.com", "postgres://...", "sqlite:///app.db"
        enabled: Enable/disable observability
        debug: Enable debug mode
        sample_rate: Sampling rate (0.0 to 1.0)
        **backend_kwargs: Additional backend configuration

    Examples:
        # Simple console logging
        setup(service_name="my-app", backends=["console"])

        # File + HTTP
        setup(
            service_name="my-app",
            backends=[
                "file:logs",
                "http://my-api.com/observability"
            ],
            api_key="secret123"
        )

        # Database
        setup(
            service_name="my-app",
            backends=["sqlite:///observability.db"]
        )
    """
    global _backends, _initialized

    if service_name:
        config.service_name = service_name
    if environment:
        config.environment = environment

    config.enabled = enabled
    config.debug = debug
    config.sample_rate = sample_rate

    # Close existing backends
    for backend in _backends:
        with suppress(BaseException):
            backend.close()

    _backends.clear()

    # Setup backends
    if backends:
        for backend_config in backends:
            if isinstance(backend_config, Backend):
                _backends.append(backend_config)
            elif isinstance(backend_config, str):
                backend = _create_backend(backend_config, backend_kwargs)
                if backend:
                    _backends.append(backend)

    # Default to console if no backends
    if not _backends:
        _backends.append(ConsoleBackend())

    _initialized = True
    log.info(f"Observability initialized for {config.service_name}",
             backends=[b.__class__.__name__ for b in _backends])


def _create_backend(config_str: str, kwargs: dict) -> Optional[Backend]:
    """Create backend from configuration string"""
    try:
        if config_str == "console":
            return ConsoleBackend()

        elif config_str == "file" or config_str.startswith("file:"):
            path = config_str.split(":", 1)[1] if ":" in config_str else "logs"
            return FileBackend(path)

        elif config_str.startswith("http://") or config_str.startswith("https://"):
            api_key = kwargs.get('api_key')
            return HTTPBackend(config_str, api_key)

        elif "postgresql" in config_str or "postgres" in config_str or "mysql" in config_str or "sqlite" in config_str:
            return DatabaseBackend(config_str)

    except Exception as e:
        if config.debug:
            print(f"Failed to create backend '{config_str}': {e}")

    return None


def flush():
    """Flush all backends"""
    for backend in _backends:
        with suppress(BaseException):
            backend.flush()


def shutdown():
    """Shutdown observability - call on app exit"""
    flush()
    for backend in _backends:
        with suppress(BaseException):
            backend.close()
    _backends.clear()


# Register shutdown handler
atexit.register(shutdown)


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def add_attribute(key: str, value: Any):
    """Add attribute to current span"""
    spans = getattr(_context, 'span_stack', [])
    if spans:
        if spans[-1].attributes is None:
            spans[-1].attributes = {}
        spans[-1].attributes[key] = value


def record_exception(error: Exception):
    """Record an exception in current span"""
    log.error(f"Exception: {error!s}", error=error)


def get_trace_id() -> Optional[str]:
    """Get current trace ID"""
    return _get_trace_id()


def get_span_id() -> Optional[str]:
    """Get current span ID"""
    return _get_span_id()


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'Backend',
    'ConsoleBackend',
    'DatabaseBackend',
    'FileBackend',
    'HTTPBackend',
    'Logger',
    'add_attribute',
    'end_trace',
    'flush',
    'get_span_id',
    'get_trace_id',
    'log',
    'record_exception',
    'setup',
    'shutdown',
    'start_trace',
    'trace',
    'trace_context',
]
