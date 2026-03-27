# aiccel/execution/orchestrator.py
"""
Execution Orchestrator
======================

Orchestrates the full agent execution flow.
Handles thinking, tool execution, and response synthesis.
Extracted from agent.py for better modularity.
"""

import asyncio
import logging
from typing import Any, Optional

from tenacity import stop_after_attempt, wait_exponential

from ..exceptions import ProviderException


logger = logging.getLogger(__name__)


class ExecutionOrchestrator:
    """
    Orchestrates the execution flow of the agent.
    Handles thinking, tool execution, and response synthesis.

    Now supports plugin hooks for extensibility.
    """

    def __init__(
        self,
        llm_provider,
        tool_executor,
        prompt_builder,
        memory,
        agent_logger=None,
        config=None,
        fallback_providers: Optional[list] = None,
        plugin_manager=None,
        planner=None
    ):
        """
        Initialize orchestrator.

        Args:
            llm_provider: Primary LLM provider
            tool_executor: Tool executor instance
            prompt_builder: Prompt builder instance
            memory: Conversation memory
            agent_logger: Logger instance
            config: Agent configuration
            fallback_providers: Fallback LLM providers
            plugin_manager: Plugin manager for hooks
            planner: Optional custom planner
        """
        self.llm_provider = llm_provider
        self.tool_executor = tool_executor
        self.prompt_builder = prompt_builder
        self.memory = memory
        self.logger = agent_logger or logger
        self.config = config
        self.fallback_providers = fallback_providers or []
        self.plugin_manager = plugin_manager

        # Initialize Planner if not provided
        if planner:
            self.planner = planner
        else:
            from .planner import ExecutionPlanner
            self.planner = ExecutionPlanner(prompt_builder, tool_executor)

    def execute_query(self, query: str, context) -> "AgentResponse":
        """
        Execute query with full orchestration.

        Args:
            query: User query
            context: Execution context

        Returns:
            AgentResponse with results
        """
        from ..core.plugin import PluginHook
        from ..core.response import AgentResponse

        # Plugin hook: before execute
        if self.plugin_manager:
            modified_query = self.plugin_manager.execute_hook(
                PluginHook.BEFORE_EXECUTE, query, context
            )
            if modified_query:
                query = modified_query

        try:
            # Step 1: Thinking phase (if enabled)
            thinking = None
            if self.config and self.config.thinking_enabled:
                thinking = self._execute_thinking_phase(query, context)

            # Step 2: Generate initial LLM response
            llm_response = self._generate_initial_response(query, context, thinking)

            # Step 3: Parse and execute tools
            final_response, tool_outputs = self._execute_tools_flow(
                query, llm_response, context
            )

            # Step 4: Build response
            response = AgentResponse(
                response=final_response,
                thinking=thinking,
                tools_used=[(name, args) for name, args, _ in tool_outputs],
                tool_outputs=tool_outputs,
                execution_time=context.get_duration(),
                metadata={
                    "has_tools": context.has_tools,
                    "relevant_tools": [t.name for t in context.relevant_tools],
                    "execution_mode": context.execution_mode.value
                }
            )

            # Step 5: Update memory
            self._update_memory(query, response)

            # Plugin hook: after execute
            if self.plugin_manager:
                modified_response = self.plugin_manager.execute_hook(
                    PluginHook.AFTER_EXECUTE, response, context
                )
                if modified_response:
                    response = modified_response

            return response

        except Exception as e:
            # Plugin hook: on error
            if self.plugin_manager:
                from ..core.plugin import PluginHook
                suppress = self.plugin_manager.execute_hook(
                    PluginHook.ON_ERROR, e, context
                )
                if suppress:
                    return AgentResponse.error(str(e), context.get_duration())
            raise

    async def execute_query_async(self, query: str, context) -> "AgentResponse":
        """Execute query asynchronously"""
        from ..core.plugin import PluginHook
        from ..core.response import AgentResponse

        # Plugin hook: before execute
        if self.plugin_manager:
            modified_query = self.plugin_manager.execute_hook(
                PluginHook.BEFORE_EXECUTE, query, context
            )
            if modified_query:
                query = modified_query

        try:
            # Step 1: Thinking phase
            thinking = None
            if self.config and self.config.thinking_enabled:
                thinking = await self._execute_thinking_phase_async(query, context)

            # Step 2: Generate initial response
            llm_response = await self._generate_initial_response_async(query, context, thinking)

            # Step 3: Execute tools
            final_response, tool_outputs = await self._execute_tools_flow_async(
                query, llm_response, context
            )

            # Step 4: Build response
            response = AgentResponse(
                response=final_response,
                thinking=thinking,
                tools_used=[(name, args) for name, args, _ in tool_outputs],
                tool_outputs=tool_outputs,
                execution_time=context.get_duration(),
                metadata={
                    "has_tools": context.has_tools,
                    "relevant_tools": [t.name for t in context.relevant_tools],
                    "execution_mode": context.execution_mode.value
                }
            )

            # Step 5: Update memory
            self._update_memory(query, response)

            # Plugin hook: after execute
            if self.plugin_manager:
                modified_response = self.plugin_manager.execute_hook(
                    PluginHook.AFTER_EXECUTE, response, context
                )
                if modified_response:
                    response = modified_response

            return response

        except Exception as e:
            if self.plugin_manager:
                from ..core.plugin import PluginHook
                suppress = self.plugin_manager.execute_hook(
                    PluginHook.ON_ERROR, e, context
                )
                if suppress:
                    return AgentResponse.error(str(e), context.get_duration())
            raise

    def _execute_thinking_phase(self, query: str, context) -> str:
        """Execute thinking phase using Planner."""
        thinking_prompt = self.planner.plan_thinking(query, context)

        try:
            return self._call_llm(thinking_prompt)
        except Exception as e:
            self.logger.error(f"Thinking phase failed: {e}")
            return "Thinking phase failed."

    async def _execute_thinking_phase_async(self, query: str, context) -> str:
        """Execute thinking phase asynchronously using Planner."""
        thinking_prompt = self.planner.plan_thinking(query, context)

        try:
            return await self._call_llm_async(thinking_prompt)
        except Exception as e:
            self.logger.error(f"Async thinking phase failed: {e}")
            return "Thinking phase failed."

    def _generate_initial_response(
        self,
        query: str,
        context,
        thinking: Optional[str]
    ) -> str:
        """Generate initial LLM response using Planner strategy."""
        messages = self.planner.plan_initial_response(query, context, self.memory, thinking)
        return self._call_llm_chat(messages)

    async def _generate_initial_response_async(
        self,
        query: str,
        context,
        thinking: Optional[str]
    ) -> str:
        """Generate initial LLM response asynchronously using Planner."""
        messages = self.planner.plan_initial_response(query, context, self.memory, thinking)
        return await self._call_llm_chat_async(messages)

    def _execute_tools_flow(
        self,
        query: str,
        llm_response: str,
        context
    ) -> tuple[str, list[tuple[str, dict[str, Any], str]]]:
        """Execute the full tool flow: parse, execute, synthesize."""
        # Handle no tools scenario
        if not context.has_tools:
            if self.config and self.config.strict_tool_usage:
                return "No tools available to answer this query.", []
            return llm_response, []

        # Parse tool calls from response via Planner
        tool_calls = self.planner.parse_tools(llm_response, query)

        # If no tools parsed in strict mode, try direct selection
        if not tool_calls and self.config and self.config.strict_tool_usage:
            tool_calls = self._attempt_direct_tool_selection(query, context)

        # Execute tools
        tool_outputs = []
        if tool_calls:
            tool_outputs = self._execute_tool_calls(tool_calls, context)

            # Synthesize response from tool outputs
            if tool_outputs:
                final_response = self._synthesize_response(query, tool_outputs, context)
                return final_response, tool_outputs

        # Handle no tools used in strict mode
        if self.config and self.config.strict_tool_usage and not tool_outputs:
            return (
                "I am configured to use specific tools, but could not identify or "
                "successfully use appropriate tools for your query.",
                []
            )

        # Default to LLM response
        return llm_response, []

    async def _execute_tools_flow_async(
        self,
        query: str,
        llm_response: str,
        context
    ) -> tuple[str, list[tuple[str, dict[str, Any], str]]]:
        """Execute tool flow asynchronously"""
        if not context.has_tools:
            if self.config and self.config.strict_tool_usage:
                return "No tools available to answer this query.", []
            return llm_response, []

        tool_calls = self.planner.parse_tools(llm_response, query)

        if not tool_calls and self.config and self.config.strict_tool_usage:
            tool_calls = await self._attempt_direct_tool_selection_async(query, context)

        tool_outputs = []
        if tool_calls:
            tool_outputs = await self._execute_tool_calls_async(tool_calls, context)

            if tool_outputs:
                final_response = await self._synthesize_response_async(
                    query, tool_outputs, context
                )
                return final_response, tool_outputs

        if self.config and self.config.strict_tool_usage and not tool_outputs:
            return (
                "I am configured to use specific tools, but could not identify or "
                "successfully use appropriate tools for your query.",
                []
            )

        return llm_response, []

    def _execute_tool_calls(
        self,
        tool_calls: list[tuple[str, dict[str, Any]]],
        context
    ) -> list[tuple[str, dict[str, Any], str]]:
        """Execute multiple tool calls"""
        tool_outputs = []

        for tool_name, tool_args in tool_calls:
            if self.tool_executor.should_skip_tool(tool_name):
                error_output = f"Tool {tool_name} temporarily disabled due to failures"
                tool_outputs.append((tool_name, tool_args, error_output))
                continue

            output, success = self.tool_executor.execute_tool_with_cache(
                tool_name, tool_args, context.trace_id
            )
            tool_outputs.append((tool_name, tool_args, output))

            if not success and self.config and self.config.strict_tool_usage:
                break

        return tool_outputs

    async def _execute_tool_calls_async(
        self,
        tool_calls: list[tuple[str, dict[str, Any]]],
        context
    ) -> list[tuple[str, dict[str, Any], str]]:
        """Execute multiple tool calls asynchronously"""
        tool_outputs = []

        for tool_name, tool_args in tool_calls:
            if self.tool_executor.should_skip_tool(tool_name):
                error_output = f"Tool {tool_name} temporarily disabled due to failures"
                tool_outputs.append((tool_name, tool_args, error_output))
                continue

            loop = asyncio.get_running_loop()
            output, success = await loop.run_in_executor(
                None,
                self.tool_executor.execute_tool_with_cache,
                tool_name,
                tool_args,
                context.trace_id
            )
            tool_outputs.append((tool_name, tool_args, output))

            if not success and self.config and self.config.strict_tool_usage:
                break

        return tool_outputs

    def _attempt_direct_tool_selection(
        self,
        query: str,
        context
    ) -> list[tuple[str, dict[str, Any]]]:
        direct_prompt = self.planner.plan_direct_tool_selection(query, context)

        try:
            response = self._call_llm(direct_prompt)
            return self.planner.parse_tools(response, query)
        except Exception:
            return []

    async def _attempt_direct_tool_selection_async(
        self,
        query: str,
        context
    ) -> list[tuple[str, dict[str, Any]]]:
        direct_prompt = self.planner.plan_direct_tool_selection(query, context)

        try:
            response = await self._call_llm_async(direct_prompt)
            return self.planner.parse_tools(response, query)
        except Exception:
            return []

    def _synthesize_response(
        self,
        query: str,
        tool_outputs: list[tuple[str, dict[str, Any], str]],
        context
    ) -> str:
        """Synthesize final response using Planner strategy."""
        synthesis_prompt = self.planner.plan_synthesis(query, tool_outputs)

        try:
            return self._call_llm(synthesis_prompt)
        except Exception:
            outputs = [f"{name}: {output[:200]}" for name, _, output in tool_outputs]
            return "\n\n".join(outputs)

    async def _synthesize_response_async(
        self,
        query: str,
        tool_outputs: list[tuple[str, dict[str, Any], str]],
        context
    ) -> str:
        """Synthesize final response asynchronously using Planner."""
        synthesis_prompt = self.planner.plan_synthesis(query, tool_outputs)

        try:
            return await self._call_llm_async(synthesis_prompt)
        except Exception:
            outputs = [f"{name}: {output[:200]}" for name, _, output in tool_outputs]
            return "\n\n".join(outputs)

    def _update_memory(self, query: str, response) -> None:
        """Update conversation memory"""
        from ..core.plugin import PluginHook

        # Plugin hook: before memory update
        if self.plugin_manager:
            result = self.plugin_manager.execute_hook(
                PluginHook.BEFORE_MEMORY_UPDATE, query, response.response
            )
            if result:
                query, response_text = result
            else:
                response_text = response.response
        else:
            response_text = response.response

        tool_names = ", ".join([name for name, _ in response.tools_used]) if response.tools_used else None
        tool_outputs_str = "\n".join([
            str(output) for _, _, output in response.tool_outputs
        ]) if response.tool_outputs else None

        self.memory.add_turn(
            query=query,
            response=response_text,
            tool_used=tool_names,
            tool_output=tool_outputs_str
        )

        # Plugin hook: after memory update
        if self.plugin_manager:
            self.plugin_manager.execute_hook(
                PluginHook.AFTER_MEMORY_UPDATE, query, response_text
            )

    def _call_llm(self, prompt: str, **kwargs) -> str:
        """Call LLM with retry and fallback logic"""
        from tenacity import Retrying

        providers = [self.llm_provider, *self.fallback_providers]
        last_error = None

        for provider in providers:
            try:
                # Retry each provider 3 times with exponential backoff
                for attempt in Retrying(
                    stop=stop_after_attempt(3),
                    wait=wait_exponential(multiplier=1, min=2, max=10),
                    reraise=True
                ):
                    with attempt:
                        return provider.generate(prompt, **kwargs)
            except Exception as e:
                last_error = e
                # Continue to next provider
                continue

        raise ProviderException(
            "All providers failed",
            context={"last_error": str(last_error)}
        )

    async def _call_llm_async(self, prompt: str, **kwargs) -> str:
        """Call LLM asynchronously with retry and fallback"""
        from tenacity import AsyncRetrying

        providers = [self.llm_provider, *self.fallback_providers]
        last_error = None

        for provider in providers:
            try:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(3),
                    wait=wait_exponential(multiplier=1, min=2, max=10),
                    reraise=True
                ):
                    with attempt:
                        return await provider.generate_async(prompt, **kwargs)
            except Exception as e:
                last_error = e
                continue

        raise ProviderException(
            "All async providers failed",
            context={"last_error": str(last_error)}
        )

    def _call_llm_chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Call LLM chat with fallback"""
        from tenacity import Retrying

        providers = [self.llm_provider, *self.fallback_providers]
        last_error = None

        for provider in providers:
            try:
                for attempt in Retrying(
                    stop=stop_after_attempt(3),
                    wait=wait_exponential(multiplier=1, min=2, max=10),
                    reraise=True
                ):
                    with attempt:
                        return provider.chat(messages, **kwargs)
            except Exception as e:
                last_error = e
                continue

        raise ProviderException(
            "All chat providers failed",
            context={"last_error": str(last_error)}
        )

    async def _call_llm_chat_async(
        self,
        messages: list[dict[str, str]],
        **kwargs
    ) -> str:
        """Call LLM chat asynchronously with fallback"""
        from tenacity import AsyncRetrying

        providers = [self.llm_provider, *self.fallback_providers]
        last_error = None

        for provider in providers:
            try:
                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(3),
                    wait=wait_exponential(multiplier=1, min=2, max=10),
                    reraise=True
                ):
                    with attempt:
                        return await provider.chat_async(messages, **kwargs)
            except Exception as e:
                last_error = e
                continue

        raise ProviderException(
            "All async chat providers failed",
            context={"last_error": str(last_error)}
        )
