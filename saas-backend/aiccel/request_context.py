# aiccel/request_context.py
"""
Request Context Module
======================

Provides request-scoped context for correlation ID tracking across the framework.
This enables distributed tracing and log correlation in production environments.

Usage:
    from aiccel.request_context import RequestContext, get_request_id

    # Start a new request context
    with RequestContext() as ctx:
        agent.run("query")  # All logs will include ctx.request_id

    # Or manually
    ctx = RequestContext.create()
    try:
        ...
    finally:
        ctx.clear()

This follows Google's distributed tracing patterns and is compatible with
OpenTelemetry trace propagation.
"""

import contextvars
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


# Thread-local and async-safe context storage
_request_context: contextvars.ContextVar['RequestContext'] = contextvars.ContextVar(
    'aiccel_request_context',
    default=None
)


@dataclass
class RequestContext:
    """
    Request-scoped context for tracking requests across the framework.

    Attributes:
        request_id: Unique identifier for this request (UUID)
        parent_id: Parent request ID for nested operations
        trace_id: Optional OpenTelemetry-compatible trace ID
        span_id: Optional OpenTelemetry-compatible span ID
        metadata: Additional context data
        created_at: Timestamp when context was created

    Example:
        with RequestContext() as ctx:
            print(f"Processing request {ctx.request_id}")
            agent.run("Hello")  # All operations inherit this context
    """
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_id: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    _token: Optional[contextvars.Token] = field(default=None, repr=False)

    def __enter__(self) -> 'RequestContext':
        """Enter context manager and set as current context."""
        self._token = _request_context.set(self)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager and restore previous context."""
        if self._token is not None:
            _request_context.reset(self._token)
            self._token = None

    @classmethod
    def create(
        cls,
        request_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        **metadata
    ) -> 'RequestContext':
        """
        Create and activate a new request context.

        Args:
            request_id: Custom request ID (auto-generated if not provided)
            parent_id: Parent request ID for nested contexts
            trace_id: OpenTelemetry trace ID
            **metadata: Additional context data

        Returns:
            New RequestContext instance (already activated)
        """
        ctx = cls(
            request_id=request_id or str(uuid.uuid4()),
            parent_id=parent_id,
            trace_id=trace_id,
            metadata=metadata
        )
        ctx._token = _request_context.set(ctx)
        return ctx

    def clear(self) -> None:
        """Clear this context (must be called if not using context manager)."""
        if self._token is not None:
            _request_context.reset(self._token)
            self._token = None

    def child(self, **metadata) -> 'RequestContext':
        """
        Create a child context for nested operations.

        The child inherits trace_id but gets its own request_id.
        """
        return RequestContext(
            parent_id=self.request_id,
            trace_id=self.trace_id,
            metadata={**self.metadata, **metadata}
        )

    @property
    def short_id(self) -> str:
        """Return shortened request ID for logging (first 8 chars)."""
        return self.request_id[:8]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "request_id": self.request_id,
            "parent_id": self.parent_id,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
        }


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def get_current_context() -> Optional[RequestContext]:
    """Get the current request context, if any."""
    return _request_context.get()


def get_request_id() -> Optional[str]:
    """Get the current request ID, if in a request context."""
    ctx = _request_context.get()
    return ctx.request_id if ctx else None


def get_short_request_id() -> str:
    """Get shortened request ID for logging, or 'no-ctx' if not in context."""
    ctx = _request_context.get()
    return ctx.short_id if ctx else "no-ctx"


def ensure_context() -> RequestContext:
    """
    Ensure a request context exists, creating one if necessary.

    Returns:
        Current or newly created RequestContext
    """
    ctx = _request_context.get()
    if ctx is None:
        ctx = RequestContext.create()
    return ctx


@contextmanager
def request_scope(
    request_id: Optional[str] = None,
    **metadata
):
    """
    Context manager for request-scoped operations.

    Usage:
        with request_scope(user_id="123") as ctx:
            result = agent.run(query)
    """
    ctx = RequestContext.create(request_id=request_id, **metadata)
    try:
        yield ctx
    finally:
        ctx.clear()


# =============================================================================
# LOGGING INTEGRATION
# =============================================================================

class RequestContextFilter:
    """
    Logging filter that adds request context to log records.

    Usage:
        import logging
        handler = logging.StreamHandler()
        handler.addFilter(RequestContextFilter())

        # Now logs include request_id automatically
        logger.info("Processing...")  # [req-a1b2c3d4] Processing...
    """

    def filter(self, record) -> bool:
        """Add request context fields to log record."""
        ctx = get_current_context()
        if ctx:
            record.request_id = ctx.short_id
            record.trace_id = ctx.trace_id or ""
            record.parent_id = ctx.parent_id or ""
        else:
            record.request_id = "no-ctx"
            record.trace_id = ""
            record.parent_id = ""
        return True


# =============================================================================
# DECORATOR
# =============================================================================

def with_request_context(func):
    """
    Decorator that ensures function runs within a request context.

    If no context exists, creates one for the duration of the call.

    Usage:
        @with_request_context
        def process_query(query: str):
            # request_id is now available
            ...
    """
    import asyncio
    import functools

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        ctx = get_current_context()
        if ctx:
            return func(*args, **kwargs)
        with RequestContext():
            return func(*args, **kwargs)

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        ctx = get_current_context()
        if ctx:
            return await func(*args, **kwargs)
        with RequestContext():
            return await func(*args, **kwargs)

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "RequestContext",
    "RequestContextFilter",
    "ensure_context",
    "get_current_context",
    "get_request_id",
    "get_short_request_id",
    "request_scope",
    "with_request_context",
]
