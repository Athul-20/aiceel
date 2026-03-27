# aiccel/core/__init__.py
"""
AIccel Core Module
==================

Core abstractions, protocols, and data structures.
Following SOLID principles with clean interfaces.
"""

from .config import AgentConfig, ExecutionContext, ExecutionMode
from .interfaces import AgentInterface
from .plugin import AgentPlugin, PluginHook, PluginManager

# New protocols - industry-standard abstractions
from .protocols import (
    BaseLLMProvider,
    BaseMemory,
    BaseTool,
    Context,
    LLMProtocol,
    MemoryProtocol,
    Message,
    Middleware,
    PluginProtocol,
    ToolCall,
    ToolProtocol,
    ToolResult,
    ToolResultStatus,
)
from .response import AgentResponse


__all__ = [
    # Config
    "AgentConfig",
    "AgentInterface",
    # Plugins
    "AgentPlugin",
    "AgentResponse",
    # Base classes (new)
    "BaseLLMProvider",
    "BaseMemory",
    "BaseTool",
    "Context",
    "ExecutionContext",
    "ExecutionMode",
    # Protocols (new)
    "LLMProtocol",
    "MemoryProtocol",
    # Data structures (new)
    "Message",
    "Middleware",
    "PluginHook",
    "PluginManager",
    "PluginProtocol",
    "ToolCall",
    "ToolProtocol",
    "ToolResult",
    "ToolResultStatus",
]
