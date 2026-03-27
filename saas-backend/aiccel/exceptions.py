# aiccel/exceptions.py
"""
AICCEL Exception Hierarchy
==========================

Unified exception hierarchy for the entire AICCEL framework.
This is the **SINGLE SOURCE OF TRUTH** for all exceptions.

Features:
- Rich context with structured details
- Error codes for API responses
- HTTP status codes for REST APIs
- Chaining and debugging support
- Centralized error handling

Usage:
    from aiccel.exceptions import ToolExecutionError, AiccelError

    try:
        result = tool.execute(args)
    except ToolExecutionError as e:
        logger.error(f"Tool failed: {e}", extra=e.to_dict())
"""

import traceback
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional


# ============================================================================
# ERROR CONTEXT
# ============================================================================

@dataclass
class ErrorContext:
    """
    Rich context for errors.

    Provides structured information for debugging and logging.
    """
    component: str = ""
    operation: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    trace_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "operation": self.operation,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "trace_id": self.trace_id,
        }


# ============================================================================
# BASE EXCEPTION
# ============================================================================

class AiccelError(Exception):
    """
    Base exception for all AICCEL errors.

    Features:
    - Rich context with ErrorContext
    - Error codes for categorization
    - HTTP status codes for API responses
    - Exception chaining with cause
    - Structured logging support via to_dict()

    Example:
        raise AiccelError(
            "Operation failed",
            component="Agent",
            operation="run",
            trace_id="abc123"
        )
    """

    error_code: str = "AICCEL_ERROR"
    http_status: int = 500

    def __init__(
        self,
        message: str,
        context: Optional[ErrorContext] = None,
        cause: Optional[Exception] = None,
        **kwargs
    ):
        self.message = message
        self.context = context or ErrorContext(**{k: v for k, v in kwargs.items()
                                                   if k in ('component', 'operation', 'details', 'trace_id')})
        # Store extra kwargs in details
        extra_kwargs = {k: v for k, v in kwargs.items()
                       if k not in ('component', 'operation', 'details', 'trace_id', 'timestamp')}
        if extra_kwargs:
            self.context.details.update(extra_kwargs)

        self.cause = cause
        self._traceback = traceback.format_exc() if cause else None
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/API responses."""
        return {
            "error_code": self.error_code,
            "http_status": self.http_status,
            "message": self.message,
            "context": self.context.to_dict() if self.context else None,
            "cause": str(self.cause) if self.cause else None,
        }

    def with_context(self, **kwargs) -> 'AiccelError':
        """Add context and return self for chaining."""
        for key, value in kwargs.items():
            if hasattr(self.context, key):
                setattr(self.context, key, value)
            else:
                self.context.details[key] = value
        return self

    def __str__(self) -> str:
        msg = f"[{self.error_code}] {self.message}"
        if self.context and self.context.component:
            msg = f"{self.context.component}: {msg}"
        return msg


# Legacy alias for backward compatibility
AICCLException = AiccelError


# ============================================================================
# PROVIDER ERRORS
# ============================================================================

class ProviderError(AiccelError):
    """Base for LLM provider errors."""
    error_code = "PROVIDER_ERROR"


class ProviderException(ProviderError):
    """Legacy alias for ProviderError."""
    pass


class APIError(ProviderError):
    """API call failed."""
    error_code = "API_ERROR"
    http_status = 502


class RateLimitError(ProviderError):
    """Rate limit exceeded."""
    error_code = "RATE_LIMIT"
    http_status = 429


class ProviderRateLimitError(RateLimitError):
    """Legacy alias with provider info."""

    def __init__(self, provider: str, retry_after: Optional[int] = None, **kwargs):
        message = f"Rate limit exceeded for {provider}"
        if retry_after:
            message += f", retry after {retry_after}s"
        super().__init__(message, **kwargs)
        self.provider = provider
        self.retry_after = retry_after
        self.context.details.update({"provider": provider, "retry_after": retry_after})


class AuthenticationError(ProviderError):
    """Authentication failed."""
    error_code = "AUTH_ERROR"
    http_status = 401


class ProviderAuthError(AuthenticationError):
    """Legacy alias with provider info."""

    def __init__(self, provider: str, message: str = "Authentication failed", **kwargs):
        super().__init__(message, **kwargs)
        self.provider = provider
        self.context.details["provider"] = provider


class ModelNotFoundError(ProviderError):
    """Model not found or unavailable."""
    error_code = "MODEL_NOT_FOUND"
    http_status = 404


class ContextLengthError(ProviderError):
    """Context length exceeded."""
    error_code = "CONTEXT_LENGTH"
    http_status = 400


class ProviderTimeoutError(ProviderError):
    """Request timed out."""
    error_code = "PROVIDER_TIMEOUT"
    http_status = 504

    def __init__(self, provider: str, timeout: float, **kwargs):
        message = f"Request to {provider} timed out after {timeout}s"
        super().__init__(message, **kwargs)
        self.provider = provider
        self.timeout = timeout
        self.context.details.update({"provider": provider, "timeout": timeout})


# ============================================================================
# TOOL ERRORS
# ============================================================================

class ToolError(AiccelError):
    """Base for tool errors."""
    error_code = "TOOL_ERROR"


class ToolException(ToolError):
    """Legacy alias for ToolError."""
    pass


class ToolNotFoundError(ToolError):
    """Tool not found in registry."""
    error_code = "TOOL_NOT_FOUND"
    http_status = 404

    def __init__(self, tool_name: str, available_tools: Optional[list[str]] = None, **kwargs):
        message = f"Tool '{tool_name}' not found"
        if available_tools:
            message += f". Available: {', '.join(available_tools[:5])}"
            if len(available_tools) > 5:
                message += f" and {len(available_tools) - 5} more"
        super().__init__(message, **kwargs)
        self.tool_name = tool_name
        self.available_tools = available_tools or []
        self.context.details.update({
            "tool_name": tool_name,
            "available_tools": available_tools
        })


class ToolExecutionError(ToolError):
    """Tool execution failed."""
    error_code = "TOOL_EXECUTION"
    http_status = 500

    def __init__(self, tool_name: str = "", message: str = "Tool execution failed",
                 original_error: Optional[Exception] = None, **kwargs):
        if tool_name:
            message = f"Tool '{tool_name}' failed: {message}"
        super().__init__(message, cause=original_error, **kwargs)
        self.tool_name = tool_name
        self.original_error = original_error
        self.context.details.update({
            "tool_name": tool_name,
            "original_error": str(original_error) if original_error else None
        })


class ToolValidationError(ToolError):
    """Tool input/output validation failed."""
    error_code = "TOOL_VALIDATION"
    http_status = 400

    def __init__(self, tool_name: str = "", parameter: str = "",
                 message: str = "Validation failed", **kwargs):
        full_message = message
        if tool_name and parameter:
            full_message = f"Tool '{tool_name}' parameter '{parameter}': {message}"
        elif tool_name:
            full_message = f"Tool '{tool_name}': {message}"
        super().__init__(full_message, **kwargs)
        self.tool_name = tool_name
        self.parameter = parameter
        self.context.details.update({
            "tool_name": tool_name,
            "parameter": parameter
        })


class ToolTimeoutError(ToolError):
    """Tool execution timed out."""
    error_code = "TOOL_TIMEOUT"
    http_status = 504


class ToolConfigurationError(ToolError):
    """Tool is misconfigured."""
    error_code = "TOOL_CONFIG"
    http_status = 500


# ============================================================================
# AGENT ERRORS
# ============================================================================

class AgentError(AiccelError):
    """Base for agent errors."""
    error_code = "AGENT_ERROR"


class AgentException(AgentError):
    """Legacy alias for AgentError."""
    pass


class ConfigurationError(AgentError):
    """Agent configuration invalid."""
    error_code = "CONFIG_ERROR"
    http_status = 400

    def __init__(self, parameter: str = "", message: str = "Configuration invalid",
                 expected: Any = None, actual: Any = None, **kwargs):
        if parameter:
            message = f"Configuration error for '{parameter}': {message}"
        super().__init__(message, **kwargs)
        self.parameter = parameter
        self.expected = expected
        self.actual = actual
        self.context.details.update({
            "parameter": parameter,
            "expected": expected,
            "actual": actual
        })


class ExecutionError(AgentError):
    """Agent execution failed."""
    error_code = "EXECUTION_ERROR"
    http_status = 500


class ParseError(AgentError):
    """Failed to parse LLM response."""
    error_code = "PARSE_ERROR"
    http_status = 500


class MemoryError(AgentError):
    """Memory operation failed."""
    error_code = "MEMORY_ERROR"
    http_status = 500


class MemoryException(MemoryError):
    """Legacy alias for MemoryError."""
    pass


class MemoryFullError(MemoryError):
    """Memory limit exceeded."""
    error_code = "MEMORY_FULL"

    def __init__(self, current_size: int, max_size: int, **kwargs):
        message = f"Memory limit exceeded: {current_size}/{max_size}"
        super().__init__(message, **kwargs)
        self.current_size = current_size
        self.max_size = max_size
        self.context.details.update({
            "current_size": current_size,
            "max_size": max_size
        })


# ============================================================================
# SECURITY ERRORS
# ============================================================================

class SecurityError(AiccelError):
    """Base for security errors."""
    error_code = "SECURITY_ERROR"
    http_status = 403


class EncryptionError(SecurityError):
    """Encryption/decryption failed."""
    error_code = "ENCRYPTION_ERROR"


class DecryptionError(SecurityError):
    """Decryption failed."""
    error_code = "DECRYPTION_ERROR"


class ValidationError(AiccelError):
    """Input validation failed."""
    error_code = "VALIDATION_ERROR"
    http_status = 400

    def __init__(self, field: str = "", message: str = "Validation failed",
                 value: Any = None, **kwargs):
        if field:
            message = f"Field '{field}': {message}"
        super().__init__(message, **kwargs)
        self.field = field
        self.value = value
        self.context.details.update({"field": field, "value": value})


class ValidationException(ValidationError):
    """Legacy alias for ValidationError."""
    pass


class GuardrailError(SecurityError):
    """Guardrail check failed."""
    error_code = "GUARDRAIL_ERROR"


class TracingException(AiccelError):
    """Raised when tracing operations fail."""
    error_code = "TRACING_ERROR"


# ============================================================================
# PIPELINE ERRORS
# ============================================================================

class PipelineError(AiccelError):
    """Base for pipeline errors."""
    error_code = "PIPELINE_ERROR"


class MiddlewareError(PipelineError):
    """Middleware execution failed."""
    error_code = "MIDDLEWARE_ERROR"


# ============================================================================
# MCP ERRORS
# ============================================================================

class MCPError(AiccelError):
    """Base for MCP protocol errors."""
    error_code = "MCP_ERROR"


class MCPClientError(MCPError):
    """MCP client error."""
    error_code = "MCP_CLIENT_ERROR"


# ============================================================================
# ERROR HANDLER
# ============================================================================

class ErrorHandler:
    """
    Centralized error handling with registration pattern.

    Usage:
        handler = ErrorHandler()
        handler.register(RateLimitError, lambda e: retry_with_backoff())

        try:
            result = await agent.run(query)
        except Exception as e:
            handler.handle(e)
    """

    def __init__(self):
        self._handlers: dict[type[Exception], Callable] = {}
        self._default_handler: Optional[Callable] = None

    def register(
        self,
        error_type: type[Exception],
        handler: Callable
    ) -> 'ErrorHandler':
        """Register handler for error type."""
        self._handlers[error_type] = handler
        return self

    def set_default(self, handler: Callable) -> 'ErrorHandler':
        """Set default handler for unregistered errors."""
        self._default_handler = handler
        return self

    def handle(self, error: Exception) -> Any:
        """Handle an error."""
        for error_type, handler in self._handlers.items():
            if isinstance(error, error_type):
                return handler(error)

        if self._default_handler:
            return self._default_handler(error)

        raise error

    def wrap(self, func: Callable) -> Callable:
        """Decorator to wrap function with error handling."""
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                return self.handle(e)
        return wrapper


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def wrap_error(
    error: Exception,
    error_class: type[AiccelError] = AiccelError,
    **context
) -> AiccelError:
    """Wrap a generic exception in an AiccelError."""
    if isinstance(error, AiccelError):
        return error.with_context(**context)

    return error_class(
        message=str(error),
        cause=error,
        **context
    )


def is_retryable(error: Exception) -> bool:
    """Check if error is retryable."""
    retryable_codes = ["RATE_LIMIT", "API_ERROR", "TOOL_TIMEOUT", "PROVIDER_TIMEOUT"]
    if isinstance(error, AiccelError):
        return error.error_code in retryable_codes
    return False


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'AICCLException',  # Legacy alias
    'APIError',
    # Agent
    'AgentError',
    'AgentException',  # Legacy alias
    # Base
    'AiccelError',
    'AuthenticationError',
    'ConfigurationError',
    'ContextLengthError',
    'DecryptionError',
    'EncryptionError',
    'ErrorContext',
    # Handler
    'ErrorHandler',
    'ExecutionError',
    'GuardrailError',
    'MCPClientError',
    # MCP
    'MCPError',
    'MemoryError',
    'MemoryException',  # Legacy alias
    'MemoryFullError',
    'MiddlewareError',
    'ModelNotFoundError',
    'ParseError',
    # Pipeline
    'PipelineError',
    'ProviderAuthError',
    # Provider
    'ProviderError',
    'ProviderException',  # Legacy alias
    'ProviderRateLimitError',
    'ProviderTimeoutError',
    'RateLimitError',
    # Security
    'SecurityError',
    'ToolConfigurationError',
    # Tool
    'ToolError',
    'ToolException',  # Legacy alias
    'ToolExecutionError',
    'ToolNotFoundError',
    'ToolTimeoutError',
    'ToolValidationError',
    'TracingException',
    'ValidationError',
    'ValidationException',  # Legacy alias
    'is_retryable',
    # Utilities
    'wrap_error',
]
