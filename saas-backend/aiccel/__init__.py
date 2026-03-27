# aiccel/__init__.py
"""
AICCEL - AI Agent Acceleration Framework
=========================================

A production-grade Python framework for building secure, lightweight AI agents.

Features:
    - Multiple LLM providers (OpenAI, Gemini, Groq)
    - Intelligent tool selection with validation
    - Multi-agent collaboration and routing
    - Conversation memory (buffer, summary, window)
    - Privacy-preserving entity masking
    - Secure code execution sandbox
    - Full async support
    - Comprehensive observability

Quick Start:
    >>> from aiccel import Agent, OpenAIProvider
    >>> provider = OpenAIProvider(api_key="...")
    >>> agent = Agent(provider=provider, name="Assistant")
    >>> result = agent.run("Hello, world!")
    >>> print(result["response"])

Documentation:
    https://github.com/AromalTR/aiccel

License:
    MIT
"""

from __future__ import annotations

from typing import TYPE_CHECKING


# Version following semantic versioning
__version__ = "3.5.0"
__author__ = "AROMAL TR"
__email__ = "aromaltr2000@gmail.com"


# =============================================================================
# TYPE CHECKING IMPORTS (for IDE support without runtime cost)
# =============================================================================

if TYPE_CHECKING:
    from .agent import Agent, AgentConfig, AgentResponse, ExecutionContext, ExecutionMode, create_agent
    from .conversation_memory import ConversationMemory
    from .embeddings import EmbeddingProvider, OpenAIEmbeddingProvider
    from .exceptions import (
        AgentError,
        AiccelError,
        ProviderError,
        ToolError,
        ValidationError,
    )
    from .security import (
        SecurityPolicy,
        RedactionPolicy,
        PromptInjectionGuard,
        SecurityAuditLogger,
        SecurityPipeline,
        create_security_pipeline,
    )
    from .logger import AILogger
    from .manager import AgentManager
    from .pandora import Pandora
    from .privacy import EntityMasker
    from .providers import GeminiProvider, GroqProvider, LLMProvider, OpenAIProvider
    from .sandbox import SandboxExecutor
    from .tools import BaseTool, Tool, ToolRegistry


# =============================================================================
# LAZY IMPORTS (for fast startup and robust error handling)
# =============================================================================

def __getattr__(name: str):
    """
    Lazy import handler for top-level attributes.

    This allows AICCEL to start up quickly by only importing
    modules when they're actually used.
    """

    # -------------------------------------------------------------------------
    # AGENTS
    # -------------------------------------------------------------------------
    if name == "Agent":
        from .agent import Agent
        return Agent
    if name == "create_agent":
        from .agent import create_agent
        return create_agent
    if name == "AgentConfig":
        from .agent import AgentConfig
        return AgentConfig
    if name == "AgentResponse":
        from .agent import AgentResponse
        return AgentResponse
    if name == "ToolCallResult":
        from .agent import ToolCallResult
        return ToolCallResult
    if name == "ExecutionContext":
        from .agent import ExecutionContext
        return ExecutionContext
    if name == "ExecutionMode":
        from .agent import ExecutionMode
        return ExecutionMode
    if name == "AgentManager":
        from .manager import AgentManager
        return AgentManager
    if name == "ConversationMemory":
        from .conversation_memory import ConversationMemory
        return ConversationMemory
    if name == "SecurityPolicy":
        from .security import SecurityPolicy
        return SecurityPolicy
    if name == "RedactionPolicy":
        from .security import RedactionPolicy
        return RedactionPolicy
    if name == "PromptInjectionGuard":
        from .security import PromptInjectionGuard
        return PromptInjectionGuard
    if name == "SecurityAuditLogger":
        from .security import SecurityAuditLogger
        return SecurityAuditLogger
    if name == "SecurityPipeline":
        from .security import SecurityPipeline
        return SecurityPipeline
    if name == "create_security_pipeline":
        from .security import create_security_pipeline
        return create_security_pipeline

    # -------------------------------------------------------------------------
    # PROVIDERS
    # -------------------------------------------------------------------------
    if name == "LLMProvider":
        from .providers import LLMProvider
        return LLMProvider
    if name == "OpenAIProvider":
        from .providers import OpenAIProvider
        return OpenAIProvider
    if name == "GeminiProvider":
        from .providers import GeminiProvider
        return GeminiProvider
    if name == "GroqProvider":
        from .providers import GroqProvider
        return GroqProvider
    if name == "BaseProvider":
        from .providers_base import BaseProvider
        return BaseProvider

    # -------------------------------------------------------------------------
    # EMBEDDINGS
    # -------------------------------------------------------------------------
    if name == "EmbeddingProvider":
        from .embeddings import EmbeddingProvider
        return EmbeddingProvider
    if name == "OpenAIEmbeddingProvider":
        from .embeddings import OpenAIEmbeddingProvider
        return OpenAIEmbeddingProvider

    # -------------------------------------------------------------------------
    # TOOLS
    # -------------------------------------------------------------------------
    if name == "Tool":
        from .tools import Tool
        return Tool
    if name == "BaseTool":
        from .tools import BaseTool
        return BaseTool
    if name == "ToolResult":
        from .tools import ToolResult
        return ToolResult
    if name == "ToolSchema":
        from .tools import ToolSchema
        return ToolSchema
    if name == "ParameterSchema":
        from .tools import ParameterSchema
        return ParameterSchema
    if name == "ParameterType":
        from .tools import ParameterType
        return ParameterType
    if name == "SearchTool":
        from .tools import SearchTool
        return SearchTool
    if name == "WeatherTool":
        from .tools import WeatherTool
        return WeatherTool
    if name == "CalculatorTool":
        from .tools import CalculatorTool
        return CalculatorTool
    if name == "DateTimeTool":
        from .tools import DateTimeTool
        return DateTimeTool
    if name == "ToolRegistry":
        from .tools import ToolRegistry
        return ToolRegistry
    if name == "PDFRAGTool":
        from .pdf_rag_tool import PDFRAGTool
        return PDFRAGTool

    # -------------------------------------------------------------------------
    # SECURITY & PRIVACY
    # -------------------------------------------------------------------------
    if name == "EntityMasker":
        from .privacy import EntityMasker
        return EntityMasker
    if name == "Pandora":
        from .pandora import Pandora
        return Pandora
    if name == "SandboxExecutor":
        from .sandbox import SandboxExecutor
        return SandboxExecutor
    if name == "SandboxConfig":
        from .sandbox import SandboxConfig
        return SandboxConfig
    if name == "execute_sandboxed":
        from .sandbox import execute_sandboxed
        return execute_sandboxed

    # -------------------------------------------------------------------------
    # OBSERVABILITY
    # -------------------------------------------------------------------------
    if name == "AILogger":
        from .logger import AILogger
        return AILogger
    if name == "get_logger":
        from .logger import get_logger
        return get_logger
    if name == "create_logger":
        from .logger import create_logger
        return create_logger
    if name == "init_tracing":
        from .tracing import init_tracing
        return init_tracing

    # -------------------------------------------------------------------------
    # EXCEPTIONS (all exceptions are accessible via this pattern)
    # -------------------------------------------------------------------------
    if name.endswith("Error") or name.endswith("Exception"):
        from . import exceptions
        if hasattr(exceptions, name):
            return getattr(exceptions, name)

    # -------------------------------------------------------------------------
    # CONSTANTS
    # -------------------------------------------------------------------------
    if name in ("Limits", "ToolTags", "HTTP", "Timeouts", "Retries", "Cache"):
        from . import constants
        return getattr(constants, name)

    # -------------------------------------------------------------------------
    # ERROR HANDLING
    # -------------------------------------------------------------------------
    if name == "ErrorContext":
        from .exceptions import ErrorContext
        return ErrorContext
    if name == "ErrorHandler":
        from .exceptions import ErrorHandler
        return ErrorHandler

    # Not found
    raise AttributeError(f"module 'aiccel' has no attribute '{name}'")


# =============================================================================
# PUBLIC API
# =============================================================================

__all__ = [
    # Observability
    "AILogger",
    # Core - Agents
    "Agent",
    "create_agent",
    "AgentConfig",
    "AgentManager",
    "AgentResponse",
    "BaseProvider",
    "BaseTool",
    "CalculatorTool",
    "ConversationMemory",
    "DateTimeTool",
    # Core - Embeddings
    "EmbeddingProvider",
    # Security & Privacy
    "EntityMasker",
    "SecurityPolicy",
    "RedactionPolicy",
    "PromptInjectionGuard",
    "SecurityAuditLogger",
    "SecurityPipeline",
    "create_security_pipeline",
    # Error Handling
    "ErrorContext",
    "ErrorHandler",
    "ExecutionContext",
    "ExecutionMode",
    "GeminiProvider",
    "GroqProvider",
    # Core - Providers
    "LLMProvider",
    "OpenAIEmbeddingProvider",
    "OpenAIProvider",
    "PDFRAGTool",
    "Pandora",
    "ParameterSchema",
    "ParameterType",
    "SandboxConfig",
    "SandboxExecutor",
    "SearchTool",
    # Core - Tools
    "Tool",
    "ToolCallResult",
    "ToolRegistry",
    "ToolResult",
    "ToolSchema",
    "WeatherTool",
    "__author__",
    "__email__",
    # Metadata
    "__version__",
    "create_logger",
    "execute_sandboxed",
    "get_logger",
    "init_tracing",
]
