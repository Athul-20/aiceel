# aiccel/core/protocols.py
"""
Core Protocols & Abstractions
==============================

Industry-standard abstract interfaces following SOLID principles.
All components depend on abstractions, not concretions.
"""

from abc import ABC, abstractmethod
from collections.abc import Awaitable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import (
    Any,
    Callable,
    Optional,
    Protocol,
    TypeVar,
    runtime_checkable,
)


# ============================================================================
# TYPE VARIABLES
# ============================================================================

T = TypeVar('T')
TInput = TypeVar('TInput')
TOutput = TypeVar('TOutput')


# ============================================================================
# ENUMS
# ============================================================================

class ExecutionMode(Enum):
    """Agent execution modes."""
    NORMAL = "normal"
    THINKING = "thinking"
    STRICT_TOOLS = "strict_tools"
    STREAMING = "streaming"


class ToolResultStatus(Enum):
    """Tool execution result status."""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass(frozen=True)
class Message:
    """Immutable message in conversation."""
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCall:
    """Represents a tool invocation request."""
    name: str
    arguments: dict[str, Any]
    call_id: Optional[str] = None


@dataclass
class ToolResult:
    """Result from tool execution."""
    tool_name: str
    status: ToolResultStatus
    output: Any
    error: Optional[str] = None
    duration_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status == ToolResultStatus.SUCCESS


@dataclass
class AgentResponse:
    """Structured agent response."""
    content: str
    thinking: Optional[str] = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    execution_time_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "response": self.content,
            "thinking": self.thinking,
            "tools_used": [(tc.name, tc.arguments) for tc in self.tool_calls],
            "tool_outputs": [
                (tr.tool_name, tr.output, tr.status.value)
                for tr in self.tool_results
            ],
            "execution_time": self.execution_time_ms,
            "metadata": self.metadata
        }


# ============================================================================
# PROTOCOLS (Structural Subtyping - Duck Typing with Type Safety)
# ============================================================================

@runtime_checkable
class LLMProtocol(Protocol):
    """Protocol for LLM providers - any class with these methods works."""

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate completion from prompt."""
        ...

    async def generate_async(self, prompt: str, **kwargs) -> str:
        """Async generate completion."""
        ...

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Chat completion from messages."""
        ...

    async def chat_async(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Async chat completion."""
        ...


@runtime_checkable
class ToolProtocol(Protocol):
    """Protocol for tools."""

    @property
    def name(self) -> str:
        """Tool name."""
        ...

    @property
    def description(self) -> str:
        """Tool description."""
        ...

    def execute(self, **kwargs) -> Any:
        """Execute the tool."""
        ...


@runtime_checkable
class MemoryProtocol(Protocol):
    """Protocol for conversation memory."""

    def add(self, role: str, content: str) -> None:
        """Add message to memory."""
        ...

    def get_messages(self) -> list[dict[str, str]]:
        """Get all messages."""
        ...

    def clear(self) -> None:
        """Clear memory."""
        ...


# ============================================================================
# ABSTRACT BASE CLASSES (For when you need shared implementation)
# ============================================================================

class BaseLLMProvider(ABC):
    """Abstract base for LLM providers with shared functionality."""

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """Generate completion from prompt."""
        pass

    @abstractmethod
    async def generate_async(self, prompt: str, **kwargs) -> str:
        """Async generate completion."""
        pass

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Chat completion."""
        pass

    @abstractmethod
    async def chat_async(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Async chat completion."""
        pass


class BaseTool(ABC):
    """Abstract base for tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        pass

    async def execute_async(self, **kwargs) -> Any:
        """Default async implementation - override for true async."""
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self.execute(**kwargs))

    def get_schema(self) -> dict[str, Any]:
        """Get tool schema for LLM function calling."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": getattr(self, 'parameters', {})
        }


class BaseMemory(ABC):
    """Abstract base for memory implementations."""

    @abstractmethod
    def add(self, role: str, content: str) -> None:
        pass

    @abstractmethod
    def get_messages(self) -> list[dict[str, str]]:
        pass

    @abstractmethod
    def clear(self) -> None:
        pass

    @abstractmethod
    def get_context_window(self, max_tokens: int) -> list[dict[str, str]]:
        """Get messages within token budget."""
        pass


# ============================================================================
# MIDDLEWARE PROTOCOL
# ============================================================================

@dataclass
class Context:
    """Execution context passed through middleware chain."""
    query: str
    messages: list[dict[str, str]] = field(default_factory=list)
    tools: list[ToolProtocol] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    response: Optional[AgentResponse] = None
    error: Optional[Exception] = None
    start_time: datetime = field(default_factory=datetime.now)

    @property
    def elapsed_ms(self) -> float:
        return (datetime.now() - self.start_time).total_seconds() * 1000


class Middleware(ABC):
    """
    Middleware for cross-cutting concerns.

    Follows the Chain of Responsibility pattern.
    Each middleware can:
    - Modify the context before passing to next
    - Short-circuit the chain
    - Handle errors
    - Perform cleanup after chain completes
    """

    @abstractmethod
    async def __call__(
        self,
        context: Context,
        next_middleware: Callable[[Context], Awaitable[Context]]
    ) -> Context:
        """
        Process context and call next middleware.

        Args:
            context: Current execution context
            next_middleware: Next middleware in chain

        Returns:
            Modified context
        """
        pass


# ============================================================================
# PLUGIN PROTOCOL
# ============================================================================

class PluginHook(Enum):
    """Extension points for plugins."""
    PRE_EXECUTE = "pre_execute"
    POST_EXECUTE = "post_execute"
    PRE_TOOL_CALL = "pre_tool_call"
    POST_TOOL_CALL = "post_tool_call"
    ON_ERROR = "on_error"
    ON_MEMORY_ADD = "on_memory_add"


@runtime_checkable
class PluginProtocol(Protocol):
    """Protocol for agent plugins."""

    @property
    def name(self) -> str:
        """Plugin name."""
        ...

    def on_hook(self, hook: PluginHook, context: Context) -> Optional[Context]:
        """Handle plugin hook."""
        ...


# ============================================================================
# FACTORY PROTOCOL
# ============================================================================

class ProviderFactory(Protocol):
    """Factory for creating LLM providers."""

    def create(self, provider_type: str, **kwargs) -> BaseLLMProvider:
        """Create provider instance."""
        ...


class ToolFactory(Protocol):
    """Factory for creating tools."""

    def create(self, tool_type: str, **kwargs) -> BaseTool:
        """Create tool instance."""
        ...
