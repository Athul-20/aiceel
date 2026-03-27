# aiccel/core/interfaces.py
"""
Core Interfaces
===============

Abstract interfaces for the AIccel framework.
Provides contracts that implementations must follow.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class LLMProviderInterface(Protocol):
    """Interface for LLM providers"""

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate text from prompt"""
        ...

    async def generate_async(self, prompt: str, **kwargs) -> str:
        """Generate text asynchronously"""
        ...

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Chat completion"""
        ...

    async def chat_async(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Chat completion asynchronously"""
        ...


@runtime_checkable
class ToolInterface(Protocol):
    """Interface for tools"""

    name: str
    description: str

    def execute(self, args: dict[str, Any]) -> str:
        """Execute the tool"""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation"""
        ...


@runtime_checkable
class MemoryInterface(Protocol):
    """Interface for memory management"""

    def add_turn(
        self,
        query: str,
        response: str,
        tool_used: Optional[str] = None,
        tool_output: Optional[str] = None
    ) -> None:
        """Add a turn to memory"""
        ...

    def get_context(self, max_context_turns: Optional[int] = None) -> str:
        """Get memory context as string"""
        ...

    def clear(self) -> None:
        """Clear memory"""
        ...

    def get_history(self) -> list[dict[str, Any]]:
        """Get full history"""
        ...


class AgentInterface(ABC):
    """
    Abstract interface for Agent implementations.

    Defines the contract that all Agent implementations must follow.
    """

    @abstractmethod
    def run(self, query: str) -> dict[str, Any]:
        """
        Run agent with query.

        Args:
            query: User query

        Returns:
            Dict with response, thinking, tools_used, tool_outputs
        """
        pass

    @abstractmethod
    async def run_async(self, query: str) -> dict[str, Any]:
        """Run agent asynchronously"""
        pass

    @abstractmethod
    def call(self, prompt: str, **kwargs) -> str:
        """Make simple LLM call without tools"""
        pass

    @abstractmethod
    async def call_async(self, prompt: str, **kwargs) -> str:
        """Make simple async LLM call"""
        pass

    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Make chat call"""
        pass

    @abstractmethod
    async def chat_async(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Make async chat call"""
        pass

    @abstractmethod
    def with_tool(self, tool: ToolInterface) -> "AgentInterface":
        """Add a tool to the agent"""
        pass

    @abstractmethod
    def with_tools(self, tools: list[ToolInterface]) -> "AgentInterface":
        """Add multiple tools"""
        pass

    @abstractmethod
    def clear_memory(self) -> "AgentInterface":
        """Clear conversation memory"""
        pass

    @abstractmethod
    def get_stats(self) -> dict[str, Any]:
        """Get agent statistics"""
        pass


class ExecutorInterface(ABC):
    """Interface for execution orchestrators"""

    @abstractmethod
    def execute(self, query: str, context: Any) -> Any:
        """Execute a query"""
        pass

    @abstractmethod
    async def execute_async(self, query: str, context: Any) -> Any:
        """Execute a query asynchronously"""
        pass
