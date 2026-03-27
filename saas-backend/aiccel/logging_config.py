# aiccel/logging_config.py
"""
Production Logging with Smooth Minimal Animations
==================================================

Clean, minimal logging with:
- Smooth animated spinners for long operations
- Color-coded output
- Progress indicators
- No clutter, just essential info
"""

import json
import logging
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional


# Prevent duplicate handler registration
_configured = False

# Animation frames for spinners
SPINNER_FRAMES = ['◐', '◓', '◑', '◒']
SPINNER_SIMPLE = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
DOTS = ['   ', '.  ', '.. ', '...']


class Colors:
    """ANSI color codes for terminal output."""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

    # Soft, modern palette
    BLUE = '\033[38;5;75m'      # Info - soft blue
    GREEN = '\033[38;5;114m'    # Success - soft green
    YELLOW = '\033[38;5;221m'   # Warning - amber
    RED = '\033[38;5;204m'      # Error - soft red
    GRAY = '\033[38;5;245m'     # Debug - gray
    CYAN = '\033[38;5;80m'      # Trace - cyan
    PURPLE = '\033[38;5;141m'   # Special - purple

    # Background colors for status
    BG_GREEN = '\033[48;5;22m'
    BG_RED = '\033[48;5;52m'
    BG_BLUE = '\033[48;5;24m'


class Spinner:
    """Minimal animated spinner for long operations."""

    def __init__(self, message: str = "", style: str = "dots"):
        self.message = message
        self.frames = SPINNER_SIMPLE if style == "spinner" else DOTS
        self.running = False
        self.thread = None
        self.start_time = None
        self._use_animation = sys.stdout.isatty()

    def _animate(self):
        idx = 0
        while self.running:
            if self._use_animation:
                elapsed = time.time() - self.start_time
                frame = self.frames[idx % len(self.frames)]
                sys.stdout.write(f'\r{Colors.CYAN}{frame}{Colors.RESET} {self.message} {Colors.DIM}({elapsed:.1f}s){Colors.RESET}')
                sys.stdout.flush()
            idx += 1
            time.sleep(0.1)

    def start(self):
        self.running = True
        self.start_time = time.time()
        if self._use_animation:
            self.thread = threading.Thread(target=self._animate, daemon=True)
            self.thread.start()

    def stop(self, success: bool = True):
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.2)
        if self._use_animation:
            elapsed = time.time() - self.start_time
            icon = f'{Colors.GREEN}✓{Colors.RESET}' if success else f'{Colors.RED}✗{Colors.RESET}'
            sys.stdout.write(f'\r{icon} {self.message} {Colors.DIM}({elapsed:.1f}s){Colors.RESET}\n')
            sys.stdout.flush()


class CleanFormatter(logging.Formatter):
    """Clean formatter with smooth colors and minimal design."""

    LEVEL_STYLES = {
        'DEBUG': (Colors.GRAY, '·'),
        'INFO': (Colors.BLUE, '›'),
        'WARNING': (Colors.YELLOW, '!'),
        'ERROR': (Colors.RED, '✗'),
        'CRITICAL': (Colors.RED + Colors.BOLD, '✗'),
    }

    def __init__(self, use_colors: bool = True, show_time: bool = True):
        self.use_colors = use_colors and sys.stdout.isatty()
        self.show_time = show_time
        super().__init__()

    def format(self, record: logging.LogRecord) -> str:
        # Get style for level
        color, icon = self.LEVEL_STYLES.get(record.levelname, (Colors.RESET, '›'))

        # Short timestamp
        ts = datetime.fromtimestamp(record.created).strftime('%H:%M:%S')

        # Clean module name
        name = record.name.split('.')[-1] if '.' in record.name else record.name
        name = name[:12].ljust(12)

        # Message
        msg = record.getMessage()

        if self.use_colors:
            if self.show_time:
                line = f"{Colors.DIM}{ts}{Colors.RESET} {color}{icon}{Colors.RESET} {Colors.BOLD}{name}{Colors.RESET} {msg}"
            else:
                line = f"{color}{icon}{Colors.RESET} {Colors.BOLD}{name}{Colors.RESET} {msg}"
        elif self.show_time:
            line = f"{ts} {icon} {name} {msg}"
        else:
            line = f"{icon} {name} {msg}"

        return line


class StructuredFormatter(logging.Formatter):
    """JSON structured logging for production."""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "t": datetime.fromtimestamp(record.created).isoformat(),
            "l": record.levelname[0],
            "m": record.name.split('.')[-1],
            "msg": record.getMessage()
        }, separators=(',', ':'))


def configure_logging(
    level: int = logging.INFO,
    structured: bool = False,
    show_time: bool = True,
    use_colors: bool = True,
    log_file: Optional[str] = None,
    quiet_external: bool = True,
    quiet_internal: bool = False
) -> None:
    """
    Configure clean, animated logging.

    Args:
        level: Logging level (INFO recommended)
        structured: Use JSON structured logging
        show_time: Show timestamps
        use_colors: Enable color output
        log_file: Optional file path
        quiet_external: Silence third-party loggers
        quiet_internal: Silence internal modules (crypto, etc.)
    """
    global _configured

    # Get loggers
    root = logging.getLogger()
    aiccel = logging.getLogger("aiccel")

    # Clear handlers
    root.handlers.clear()
    aiccel.handlers.clear()

    # Set levels
    aiccel.setLevel(level)

    # Choose formatter
    if structured:
        formatter = StructuredFormatter()
    else:
        formatter = CleanFormatter(use_colors=use_colors, show_time=show_time)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    aiccel.addHandler(console)

    # File handler
    if log_file:
        fh = logging.FileHandler(log_file, encoding='utf-8')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(StructuredFormatter())
        aiccel.addHandler(fh)

    # No propagation
    aiccel.propagate = False

    # Silence external
    if quiet_external:
        for name in ["httpx", "httpcore", "urllib3", "openai", "chromadb",
                     "google", "tenacity", "requests", "charset_normalizer",
                     "PIL", "asyncio"]:
            logging.getLogger(name).setLevel(logging.WARNING)
            logging.getLogger(name).propagate = False

    # Silence internal
    if quiet_internal:
        for name in ["aiccel.crypto", "aiccel.encryption", "aiccel.privacy"]:
            logging.getLogger(name).setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Get a logger for an aiccel module."""
    if not name.startswith("aiccel."):
        name = f"aiccel.{name}"
    if not _configured:
        configure_logging()
    return logging.getLogger(name)


@contextmanager
def spinner(message: str, style: str = "dots"):
    """
    Context manager for showing a spinner during long operations.

    Usage:
        with spinner("Processing query"):
            result = do_something_slow()
    """
    s = Spinner(message, style)
    s.start()
    try:
        yield s
        s.stop(success=True)
    except Exception:
        s.stop(success=False)
        raise


def status(message: str, status_type: str = "info"):
    """
    Print a status message with icon.

    Args:
        message: Status message
        status_type: One of 'info', 'success', 'warning', 'error', 'start', 'end'
    """
    icons = {
        'info': f'{Colors.BLUE}›{Colors.RESET}',
        'success': f'{Colors.GREEN}✓{Colors.RESET}',
        'warning': f'{Colors.YELLOW}!{Colors.RESET}',
        'error': f'{Colors.RED}✗{Colors.RESET}',
        'start': f'{Colors.CYAN}▶{Colors.RESET}',
        'end': f'{Colors.GREEN}■{Colors.RESET}',
    }
    icon = icons.get(status_type, icons['info'])
    print(f"{icon} {message}")


class AgentLogger:
    """
    Clean agent logger with smooth animations.

    Features:
    - Animated spinners for long operations
    - Clean trace output
    - Minimal overhead
    """

    __slots__ = (
        '_logger',
        '_spinners',
        '_trace_counter',
        '_use_animation',
        'max_traces',
        'name',
        'traces',
        'verbose',
    )

    def __init__(self, name: str, verbose: bool = False, log_file: Optional[str] = None, structured_logging: bool = False):
        if log_file:
            configure_logging(log_file=log_file, structured=structured_logging)

        self.name = name
        self._logger = get_logger(name)
        self.traces: dict[int, dict[str, Any]] = {}
        self.verbose = verbose
        self._trace_counter = 0
        self.max_traces = 100
        self._spinners: dict[int, Spinner] = {}
        self._use_animation = sys.stdout.isatty() and verbose

    # Core logging
    def debug(self, msg: str, **kwargs): self._logger.debug(msg)
    def info(self, msg: str, **kwargs): self._logger.info(msg)
    def warning(self, msg: str, **kwargs): self._logger.warning(msg)
    def error(self, msg: str, exc_info: bool = False, **kwargs):
        self._logger.error(msg, exc_info=exc_info)
    def critical(self, msg: str, exc_info: bool = True, **kwargs):
        self._logger.critical(msg, exc_info=exc_info)

    # Tracing with animations
    def trace_start(self, action: str, inputs: Optional[dict[str, Any]] = None) -> int:
        """Start a trace with optional spinner animation."""
        trace_id = self._trace_counter
        self._trace_counter += 1

        self.traces[trace_id] = {
            "action": action,
            "start": datetime.now(),
            "steps": [],
            "inputs": inputs
        }

        # Show start with preview
        if self.verbose and inputs:
            preview = str(inputs.get('query', inputs.get('prompt', '')))[:50]
            self._logger.info(f"[{trace_id}] {Colors.CYAN}▶{Colors.RESET} {action} | {preview}...")

        # Limit traces
        if len(self.traces) > self.max_traces:
            oldest = min(self.traces.keys())
            del self.traces[oldest]

        return trace_id

    def trace_step(self, trace_id: int, step: str, details: Optional[dict[str, Any]] = None):
        """Log a trace step."""
        if trace_id not in self.traces:
            return

        self.traces[trace_id]["steps"].append({
            "name": step,
            "time": datetime.now(),
            "details": details
        })

        if self.verbose:
            self._logger.debug(f"  {Colors.DIM}└─{Colors.RESET} {step}")

    def trace_error(self, trace_id: int, error: Optional[BaseException], context: str):
        """Log a trace error."""
        if trace_id not in self.traces:
            return

        self.traces[trace_id].setdefault("errors", []).append({
            "context": context,
            "type": type(error).__name__ if error else "Unknown",
            "message": str(error) if error else context
        })

        err_msg = str(error)[:80] if error else context
        self._logger.error(f"[{trace_id}] {context}: {err_msg}")

    def trace_end(self, trace_id: int, outputs: Optional[dict[str, Any]] = None) -> Optional[float]:
        """End a trace with duration."""
        if trace_id not in self.traces:
            return None

        trace = self.traces[trace_id]
        duration_ms = (datetime.now() - trace["start"]).total_seconds() * 1000

        trace["end"] = datetime.now()
        trace["duration_ms"] = duration_ms
        trace["outputs"] = outputs

        if self.verbose:
            # Format duration nicely
            dur_str = f"{duration_ms:.0f}ms" if duration_ms < 1000 else f"{duration_ms / 1000:.1f}s"

            self._logger.info(f"[{trace_id}] {Colors.GREEN}■{Colors.RESET} {trace['action']} {Colors.DIM}({dur_str}){Colors.RESET}")

        return duration_ms

    # Compatibility
    def log(self, msg: str, **kwargs): self.info(msg)
    def get_trace(self, trace_id: int): return self.traces.get(trace_id)
    def get_traces(self): return self.traces.copy()


# Backward compatibility
AILogger = AgentLogger


# Auto-configure
def _auto_configure():
    if not _configured:
        configure_logging(
            level=logging.INFO,
            use_colors=True,
            quiet_external=True,
            quiet_internal=True
        )

_auto_configure()
