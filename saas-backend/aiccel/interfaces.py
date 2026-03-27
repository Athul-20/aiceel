# aiccel/interfaces.py
"""
AICCEL Interfaces (Protocols)
=============================

Runtime-checkable Protocol interfaces for the AICCEL framework.
These define the contracts that implementations must follow.

Usage:
    from aiccel.interfaces import Tool, LLMProvider, Memory

    class MyTool:
        name = "my_tool"
        description = "Does something"

        def execute(self, args: Dict[str, Any]) -> ToolResult:
            ...

    # Type check
    assert isinstance(MyTool(), Tool)
"""

from dataclasses import dataclass, field
from typing import Any, Optional, Protocol, Union, runtime_checkable

# Import exceptions from canonical source
from .exceptions import (
    AgentError,
    AiccelError,
    MemoryError,
    ToolExecutionError,
)


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ToolResult:
    """
    Standardized tool execution result.

    Attributes:
        success: Whether execution succeeded
        data: Result data (any type)
        error: Error message if failed
        metadata: Additional metadata
        execution_time: Time taken to execute (seconds)
    """
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0

    def __str__(self) -> str:
        return str(self.data) if self.success else f"Error: {self.error}"

    @classmethod
    def ok(cls, data: Any, execution_time: float = 0.0, metadata: Optional[dict[str, Any]] = None, **kwargs) -> 'ToolResult':
        """Create a successful result."""
        meta = metadata or {}
        meta.update(kwargs)
        return cls(success=True, data=data, execution_time=execution_time, metadata=meta)

    @classmethod
    def fail(cls, error: str, execution_time: float = 0.0, metadata: Optional[dict[str, Any]] = None, **kwargs) -> 'ToolResult':
        """Create a failed result."""
        meta = metadata or {}
        meta.update(kwargs)
        return cls(success=False, error=error, execution_time=execution_time, metadata=meta)





# ============================================================================
# PROTOCOL INTERFACES
# ============================================================================

@runtime_checkable
class LLMProvider(Protocol):
    """
    Interface for LLM providers.

    Implementations must provide both sync and async methods.
    """
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text from a prompt."""
        ...

    async def generate_async(self, prompt: str, **kwargs) -> str:
        """Generate text from a prompt (async)."""
        ...

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Chat completion with message history."""
        ...

    async def chat_async(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Chat completion with message history (async)."""
        ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Interface for embedding providers."""

    def embed(self, texts: Union[str, list[str]]) -> list[list[float]]:
        """Generate embeddings for texts."""
        ...

    def get_dimension(self) -> int:
        """Get the embedding dimension."""
        ...


@runtime_checkable
class Tool(Protocol):
    """
    Interface for tools.

    Tools must have a name, description, and implement execute methods.
    """
    name: str
    description: str

    def execute(self, args: dict[str, Any]) -> ToolResult:
        """Execute the tool with given arguments."""
        ...

    async def execute_async(self, args: dict[str, Any]) -> ToolResult:
        """Execute the tool with given arguments (async)."""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Convert tool schema to dictionary for LLM function calling."""
        ...


@runtime_checkable
class Memory(Protocol):
    """Interface for conversation memory management."""

    def add_turn(self, query: str, response: str, tool_used: Optional[str] = None,
                tool_output: Optional[str] = None) -> None:
        """Add a conversation turn to memory."""
        ...

    def get_context(self, max_context_turns: Optional[int] = None) -> str:
        """Get formatted context string for LLM."""
        ...

    def clear(self) -> None:
        """Clear all memory."""
        ...

    def get_history(self) -> list[dict[str, Any]]:
        """Get full conversation history."""
        ...


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    'AgentError',
    # Re-exported exceptions (for backward compatibility)
    'AiccelError',
    'EmbeddingProvider',
    # Protocols
    'LLMProvider',
    'Memory',
    'MemoryError',
    'Tool',
    'ToolExecutionError',
    # Data classes
    'ToolResult',
]
