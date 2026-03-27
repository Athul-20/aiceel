# aiccel/agent/core.py
"""
Agent Core
==========

Main Agent class - clean, focused implementation.
Uses composition with PromptBuilder, ToolExecutor, and Orchestrator.
"""

import asyncio
import logging
import random
from typing import Any, Optional

from ..constants import Limits
from ..conversation_memory import ConversationMemory
from ..exceptions import AgentException, ValidationException
from ..logger import AILogger
from ..tools import Tool, ToolRegistry
from .config import AgentConfig, ExecutionContext, ExecutionMode
from .orchestrator import ExecutionOrchestrator
from .prompt_builder import PromptBuilder
from .tool_executor import AgentToolExecutor


logger = logging.getLogger(__name__)


class Agent:
    """
    Production-ready AI Agent.

    Features:
    - Clean modular architecture
    - Full backward compatibility
    - Comprehensive error handling
    - Async/sync support
    - Memory management
    - Tool execution with caching

    Example:
        provider = OpenAIProvider(api_key="...")
        agent = Agent(
            provider=provider,
            tools=[SearchTool()],
            name="Assistant",
            instructions="You are a helpful assistant."
        )
        result = agent.run("What is the weather?")
    """

    def __init__(
        self,
        provider: Any,
        tools: Optional[list[Tool]] = None,
        name: str = "Agent",
        description: str = "AI Agent",
        instructions: str = "You are a helpful AI assistant. Provide accurate and concise answers.",
        memory_type: str = "buffer",
        max_memory_turns: int = Limits.MAX_MEMORY_TURNS,
        max_memory_tokens: int = Limits.MAX_MEMORY_TOKENS,
        strict_tool_usage: bool = False,
        thinking_enabled: bool = False,
        verbose: bool = False,
        log_file: Optional[str] = None,
        timeout: float = Limits.DEFAULT_TIMEOUT,
        fallback_providers: Optional[list[Any]] = None
    ) -> None:
        """
        Initialize agent.

        Args:
            provider: LLM provider instance
            tools: List of tools available to the agent
            name: Agent name for identification
            description: Agent description
            instructions: System instructions for the agent
            memory_type: Type of memory ("buffer", "summary", "window")
            max_memory_turns: Maximum conversation turns to remember
            max_memory_tokens: Maximum tokens in memory context
            strict_tool_usage: If True, agent must use tools when available
            thinking_enabled: If True, agent performs reasoning before answering
            verbose: Enable verbose logging
            log_file: Optional path to log file
            timeout: Request timeout in seconds
            fallback_providers: Optional list of fallback LLM providers
        """
        # Build configuration
        self.config = AgentConfig(
            name=name,
            description=description,
            instructions=instructions,
            memory_type=memory_type,
            max_memory_turns=max_memory_turns,
            max_memory_tokens=max_memory_tokens,
            strict_tool_usage=strict_tool_usage,
            thinking_enabled=thinking_enabled,
            verbose=verbose,
            log_file=log_file,
            timeout=timeout
        )

        # Validate configuration
        self.config.validate()

        # Store provider
        self.llm_provider = provider
        self.fallback_providers = fallback_providers or []

        # Initialize logger
        self.agent_logger = AILogger(
            name=name,
            verbose=verbose,
            log_file=log_file
        )

        # Initialize tool registry
        self.tool_registry = ToolRegistry(llm_provider=provider)
        if tools:
            for tool in tools:
                self.tool_registry.register(tool)

        # Initialize memory
        self.memory = ConversationMemory(
            memory_type=memory_type,
            max_turns=max_memory_turns,
            max_tokens=max_memory_tokens,
            llm_provider=provider
        )

        # Initialize components
        self.prompt_builder = PromptBuilder(self.config, self.tool_registry)

        self.tool_executor = AgentToolExecutor(
            tool_registry=self.tool_registry,
            llm_provider=provider,
            agent_logger=self.agent_logger,
            strict_mode=strict_tool_usage
        )

        self.orchestrator = ExecutionOrchestrator(
            llm_provider=provider,
            tool_executor=self.tool_executor,
            prompt_builder=self.prompt_builder,
            memory=self.memory,
            agent_logger=self.agent_logger,
            config=self.config,
            fallback_providers=self.fallback_providers
        )

        # Stats tracking
        self._request_count = 0
        self._error_count = 0
        self._total_execution_time = 0.0

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    def set_verbose(self, verbose: bool = True) -> "Agent":
        """
        Set verbose mode.

        Args:
            verbose: Enable verbose logging

        Returns:
            Self for chaining
        """
        self.config.verbose = verbose
        if self.agent_logger:
            self.agent_logger.verbose = verbose
        return self

    def run(self, query: str) -> dict[str, Any]:
        """
        Run agent with query.

        Args:
            query: User query string

        Returns:
            Dict with response, thinking, tools_used, tool_outputs, execution_time
        """
        if not query or not query.strip():
            raise ValidationException("query", "Query cannot be empty", query)

        self._request_count += 1
        # Start trace and get ID from logger
        trace_id = self.agent_logger.trace_start("agent_run", {"query": query})

        try:
            # Build execution context
            context = self._build_context(query, trace_id)

            # Execute query
            response = self.orchestrator.execute_query(query, context)

            self._total_execution_time += response.execution_time
            self.agent_logger.trace_end(trace_id, response.to_dict())

            return response.to_dict()

        except Exception as e:
            self._error_count += 1
            self.agent_logger.trace_error(trace_id, e, str(e))
            raise AgentException(str(e), {"query": query, "trace_id": trace_id})

    async def run_async(self, query: str) -> dict[str, Any]:
        """
        Run agent with query asynchronously.

        Args:
            query: User query string

        Returns:
            Dict with response, thinking, tools_used, tool_outputs, execution_time
        """
        if not query or not query.strip():
            raise ValidationException("query", "Query cannot be empty", query)

        self._request_count += 1
        # Start trace and get ID from logger
        trace_id = self.agent_logger.trace_start("agent_run", {"query": query})

        try:
            context = self._build_context(query, trace_id)
            response = await self.orchestrator.execute_query_async(query, context)

            self._total_execution_time += response.execution_time
            self.agent_logger.trace_end(trace_id, response.to_dict())

            return response.to_dict()

        except Exception as e:
            self._error_count += 1
            self.agent_logger.trace_error(trace_id, e, str(e))
            raise AgentException(str(e), {"query": query, "trace_id": trace_id})

    def call(self, prompt: str, **kwargs) -> str:
        """
        Make simple LLM call without tools.

        Args:
            prompt: Prompt to send to LLM
            **kwargs: Additional arguments for LLM

        Returns:
            LLM response string
        """
        return self.llm_provider.generate(prompt, **kwargs)

    async def call_async(self, prompt: str, **kwargs) -> str:
        """Make simple async LLM call"""
        if hasattr(self.llm_provider, 'generate_async'):
            return await self.llm_provider.generate_async(prompt, **kwargs)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.llm_provider.generate(prompt, **kwargs)
        )

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """
        Make chat call with messages.

        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional arguments for LLM

        Returns:
            LLM response string
        """
        return self.llm_provider.chat(messages, **kwargs)

    async def chat_async(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Make async chat call"""
        if hasattr(self.llm_provider, 'chat_async'):
            return await self.llm_provider.chat_async(messages, **kwargs)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.llm_provider.chat(messages, **kwargs)
        )

    # ========================================================================
    # TOOL MANAGEMENT
    # ========================================================================

    def with_tool(self, tool: Tool) -> "Agent":
        """
        Add a tool to the agent.

        Args:
            tool: Tool to add

        Returns:
            Self for chaining
        """
        self.tool_registry.register(tool)
        return self

    def with_tools(self, tools: list[Tool]) -> "Agent":
        """
        Add multiple tools to the agent.

        Args:
            tools: List of tools to add

        Returns:
            Self for chaining
        """
        for tool in tools:
            self.tool_registry.register(tool)
        return self

    @property
    def tools(self) -> list[Tool]:
        """Get list of registered tools"""
        return self.tool_registry.get_all()

    # ========================================================================
    # MEMORY MANAGEMENT
    # ========================================================================

    def clear_memory(self) -> "Agent":
        """
        Clear conversation memory.

        Returns:
            Self for chaining
        """
        if self.memory:
            self.memory.clear()
        return self

    def get_history(self) -> list[dict[str, Any]]:
        """Get conversation history"""
        if self.memory:
            return self.memory.get_history()
        return []

    # ========================================================================
    # STATS & INFO
    # ========================================================================

    def get_stats(self) -> dict[str, Any]:
        """Get agent statistics"""
        return {
            "name": self.config.name,
            "description": self.config.description,
            "request_count": self._request_count,
            "error_count": self._error_count,
            "total_execution_time": self._total_execution_time,
            "average_execution_time": (
                self._total_execution_time / self._request_count
                if self._request_count > 0 else 0.0
            ),
            "tools_count": len(self.tools),
            "tool_names": [t.name for t in self.tools],
            "memory_type": self.config.memory_type,
            "memory_size": len(self.get_history())
        }

    def __repr__(self) -> str:
        return (
            f"Agent("
            f"name='{self.config.name}', "
            f"tools={len(self.tools)}, "
            f"requests={self._request_count}"
            f")"
        )

    # ========================================================================
    # PRIVATE METHODS
    # ========================================================================

    def _build_context(self, query: str, trace_id: int) -> ExecutionContext:
        """Build execution context for query"""
        has_tools = bool(self.tool_registry.get_all())
        relevant_tools = []

        if has_tools:
            relevant_tools = self.tool_executor.find_relevant_tools(query)

        # Determine execution mode
        if not has_tools:
            execution_mode = ExecutionMode.NO_TOOLS
        elif self.config.strict_tool_usage:
            execution_mode = ExecutionMode.STRICT_TOOLS
        elif self.config.thinking_enabled:
            execution_mode = ExecutionMode.THINKING
        else:
            execution_mode = ExecutionMode.NORMAL

        return ExecutionContext(
            query=query,
            trace_id=trace_id,
            has_tools=has_tools,
            relevant_tools=relevant_tools,
            execution_mode=execution_mode
        )

    def _generate_trace_id(self) -> int:
        """Generate unique trace ID"""
        return random.randint(100000, 999999)
