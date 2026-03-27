# aiccel/errors/__init__.py
"""
Backward Compatibility Module
=============================

This module re-exports all exceptions from aiccel.exceptions.
For new code, prefer importing directly from aiccel.exceptions.

Usage (deprecated):
    from aiccel.errors import ToolExecutionError

Preferred:
    from aiccel.exceptions import ToolExecutionError
"""

# Re-export everything from the canonical exceptions module
from ..exceptions import (
    # Agent
    AgentError,
    AgentException,
    # Base
    AiccelError,
    AICCLException,
    APIError,
    AuthenticationError,
    ConfigurationError,
    ContextLengthError,
    DecryptionError,
    EncryptionError,
    ErrorContext,
    # Handler
    ErrorHandler,
    ExecutionError,
    GuardrailError,
    MCPClientError,
    # MCP
    MCPError,
    MemoryError,
    MemoryException,
    MemoryFullError,
    MiddlewareError,
    ModelNotFoundError,
    ParseError,
    # Pipeline
    PipelineError,
    ProviderAuthError,
    # Provider
    ProviderError,
    ProviderException,
    ProviderRateLimitError,
    ProviderTimeoutError,
    RateLimitError,
    # Security
    SecurityError,
    ToolConfigurationError,
    # Tool
    ToolError,
    ToolException,
    ToolExecutionError,
    ToolNotFoundError,
    ToolTimeoutError,
    ToolValidationError,
    TracingException,
    ValidationError,
    ValidationException,
    is_retryable,
    # Utilities
    wrap_error,
)


__all__ = [
    'AICCLException',
    'APIError',
    # Agent
    'AgentError',
    'AgentException',
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
    'MemoryException',
    'MemoryFullError',
    'MiddlewareError',
    'ModelNotFoundError',
    'ParseError',
    # Pipeline
    'PipelineError',
    'ProviderAuthError',
    # Provider
    'ProviderError',
    'ProviderException',
    'ProviderRateLimitError',
    'ProviderTimeoutError',
    'RateLimitError',
    # Security
    'SecurityError',
    'ToolConfigurationError',
    # Tool
    'ToolError',
    'ToolException',
    'ToolExecutionError',
    'ToolNotFoundError',
    'ToolTimeoutError',
    'ToolValidationError',
    'TracingException',
    'ValidationError',
    'ValidationException',
    'is_retryable',
    # Utilities
    'wrap_error',
]
