# aiccel/agent/orchestrator.py
"""
Execution Orchestrator
======================

Orchestrates the execution flow of the agent.
Handles thinking, tool execution, and response synthesis.
"""

import asyncio
import logging
from typing import Any, Optional

from .config import AgentConfig, AgentResponse, ExecutionContext, ToolCall
from .prompt_builder import PromptBuilder
from .tool_executor import AgentToolExecutor


logger = logging.getLogger(__name__)


class ExecutionOrchestrator:
    """
    Orchestrates the execution flow of the agent.

    Handles:
    - Thinking phase (optional)
    - Tool execution with fallbacks
    - Response synthesis
    - Memory updates
    """

    def __init__(
        self,
        llm_provider: Any,
        tool_executor: AgentToolExecutor,
        prompt_builder: PromptBuilder,
        memory: Any,
        agent_logger: Optional[Any],
        config: AgentConfig,
        fallback_providers: Optional[list[Any]] = None
    ) -> None:
        """
        Initialize orchestrator.

        Args:
            llm_provider: Primary LLM provider
            tool_executor: Tool executor instance
            prompt_builder: Prompt builder instance
            memory: Conversation memory instance
            agent_logger: Logger instance
            config: Agent configuration
            fallback_providers: Optional list of fallback providers
        """
        self.llm_provider = llm_provider
        self.tool_executor = tool_executor
        self.prompt_builder = prompt_builder
        self.memory = memory
        self.logger = agent_logger
        self.config = config
        self.fallback_providers = fallback_providers or []

    def execute_query(self, query: str, context: ExecutionContext) -> AgentResponse:
        """
        Execute query with full orchestration.

        Args:
            query: User query
            context: Execution context

        Returns:
            AgentResponse with results
        """
        # Step 1: Thinking phase (if enabled)
        thinking = None
        if self.config.thinking_enabled:
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
            tools_used=[(r.tool_name, r.args) for r in tool_outputs],
            tool_outputs=[(r.tool_name, r.args, r.output) for r in tool_outputs],
            execution_time=context.get_duration(),
            metadata={
                "has_tools": context.has_tools,
                "relevant_tools": [t.name for t in context.relevant_tools],
                "execution_mode": context.execution_mode.value
            }
        )

        # Step 5: Update memory
        self._update_memory(query, response)

        return response

    async def execute_query_async(
        self,
        query: str,
        context: ExecutionContext
    ) -> AgentResponse:
        """Execute query asynchronously"""
        # Step 1: Thinking phase
        thinking = None
        if self.config.thinking_enabled:
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
            tools_used=[(r.tool_name, r.args) for r in tool_outputs],
            tool_outputs=[(r.tool_name, r.args, r.output) for r in tool_outputs],
            execution_time=context.get_duration(),
            metadata={
                "has_tools": context.has_tools,
                "relevant_tools": [t.name for t in context.relevant_tools],
                "execution_mode": context.execution_mode.value
            }
        )

        # Step 5: Update memory
        self._update_memory(query, response)

        return response

    def _execute_thinking_phase(self, query: str, context: ExecutionContext) -> str:
        """Execute thinking phase"""
        thinking_prompt = self.prompt_builder.build_thinking_prompt(query, context.has_tools)

        try:
            thinking = self._call_llm(thinking_prompt)
            self._log_trace(context.trace_id, "thinking_complete", {
                "thinking": thinking[:200] if thinking else ""
            })
            return thinking
        except Exception as e:
            self._log_error(f"Thinking phase failed: {e}")
            return "Thinking phase failed due to error."

    async def _execute_thinking_phase_async(
        self,
        query: str,
        context: ExecutionContext
    ) -> str:
        """Execute thinking phase asynchronously"""
        thinking_prompt = self.prompt_builder.build_thinking_prompt(query, context.has_tools)

        try:
            thinking = await self._call_llm_async(thinking_prompt)
            self._log_trace(context.trace_id, "thinking_complete", {
                "thinking": thinking[:200] if thinking else ""
            })
            return thinking
        except Exception as e:
            self._log_error(f"Thinking phase failed: {e}")
            return "Thinking phase failed due to error."

    def _generate_initial_response(
        self,
        query: str,
        context: ExecutionContext,
        thinking: Optional[str] = None
    ) -> str:
        """Generate initial LLM response"""
        # Get memory context
        memory_context = ""
        if self.memory:
            memory_context = self.memory.get_context(self.config.max_memory_turns)

        # Build main prompt
        prompt = self.prompt_builder.build_main_prompt(
            query, context.relevant_tools, memory_context
        )

        # If thinking was provided, append it
        if thinking:
            prompt += f"\n\nPrevious thinking:\n{thinking}\n\nNow provide your response:"

        return self._call_llm(prompt)

    async def _generate_initial_response_async(
        self,
        query: str,
        context: ExecutionContext,
        thinking: Optional[str] = None
    ) -> str:
        """Generate initial LLM response asynchronously"""
        memory_context = ""
        if self.memory:
            memory_context = self.memory.get_context(self.config.max_memory_turns)

        prompt = self.prompt_builder.build_main_prompt(
            query, context.relevant_tools, memory_context
        )

        if thinking:
            prompt += f"\n\nPrevious thinking:\n{thinking}\n\nNow provide your response:"

        return await self._call_llm_async(prompt)

    def _execute_tools_flow(
        self,
        query: str,
        llm_response: str,
        context: ExecutionContext
    ) -> tuple[str, list[Any]]:
        """Execute tools flow with intelligent selection fallback"""
        from .config import ToolCallResult

        # Parse tool calls from response
        tool_calls = self.tool_executor.parse_tool_calls(llm_response, query)

        # INTELLIGENT TOOL SELECTION FALLBACK
        # If no tools parsed but we have relevant tools, attempt direct selection
        if not tool_calls and context.has_tools and context.relevant_tools:
            self._log_info("No tools parsed from response, attempting direct selection")
            tool_calls = self._attempt_direct_tool_selection(query, context)

        if not tool_calls:
            # No tools to execute, return LLM response directly
            return llm_response, []

        # Execute all tools
        tool_results: list[ToolCallResult] = []

        for tool_call in tool_calls:
            if self.tool_executor.should_skip_tool(tool_call.name):
                continue

            try:
                result = self.tool_executor.execute_tool(
                    tool_call.name,
                    tool_call.args,
                    context.trace_id,
                    query
                )
                tool_results.append(result)
            except Exception as e:
                self._log_error(f"Tool execution failed: {e}")
                # Create error result
                tool_results.append(ToolCallResult(
                    tool_name=tool_call.name,
                    args=tool_call.args,
                    output=f"Error: {e!s}",
                    success=False,
                    error=str(e)
                ))

        if not tool_results:
            return llm_response, []

        # Synthesize results
        tool_tuples = [(r.tool_name, r.args, r.output) for r in tool_results]
        synthesis_prompt = self.prompt_builder.build_synthesis_prompt(query, tool_tuples)

        final_response = self._call_llm(synthesis_prompt)

        return final_response, tool_results

    def _attempt_direct_tool_selection(
        self,
        query: str,
        context: ExecutionContext
    ) -> list[ToolCall]:
        """
        Attempt direct tool selection when initial parsing fails.
        This is a key feature for intelligent tool usage.
        """
        tools = context.relevant_tools if context.relevant_tools else self.tool_executor.tool_registry.get_all()
        if not tools:
            return []

        # Build a direct prompt that explicitly asks for tool selection
        direct_prompt = self.prompt_builder.build_direct_tool_prompt(query, tools)
        self._log_trace(context.trace_id, "direct_tool_selection", {
            "query_preview": query[:100],
            "tools_available": [t.name for t in tools]
        })

        try:
            response = self._call_llm(direct_prompt)
            tool_calls = self.tool_executor.parse_tool_calls(response, query)

            if tool_calls:
                self._log_info(f"Direct selection found tools: {[tc.name for tc in tool_calls]}")
            else:
                self._log_info("Direct tool selection yielded no results")

            return tool_calls

        except Exception as e:
            self._log_error(f"Direct tool selection failed: {e}")
            return []

    async def _execute_tools_flow_async(
        self,
        query: str,
        llm_response: str,
        context: ExecutionContext
    ) -> tuple[str, list[Any]]:
        """Execute tools flow asynchronously with intelligent selection fallback"""
        from .config import ToolCallResult

        tool_calls = self.tool_executor.parse_tool_calls(llm_response, query)

        # INTELLIGENT TOOL SELECTION FALLBACK (async)
        if not tool_calls and context.has_tools and context.relevant_tools:
            self._log_info("No tools parsed (async), attempting direct selection")
            tool_calls = await self._attempt_direct_tool_selection_async(query, context)

        if not tool_calls:
            return llm_response, []

        # Execute tools concurrently
        tool_results: list[ToolCallResult] = []

        async def execute_tool_async(tool_call: ToolCall) -> Optional[ToolCallResult]:
            if self.tool_executor.should_skip_tool(tool_call.name):
                return None

            try:
                # Run sync tool execution in thread pool
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: self.tool_executor.execute_tool(
                        tool_call.name,
                        tool_call.args,
                        context.trace_id,
                        query
                    )
                )
                return result
            except Exception as e:
                self._log_error(f"Tool execution failed: {e}")
                return ToolCallResult(
                    tool_name=tool_call.name,
                    args=tool_call.args,
                    output=f"Error: {e!s}",
                    success=False,
                    error=str(e)
                )

        tasks = [execute_tool_async(tc) for tc in tool_calls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, ToolCallResult):
                tool_results.append(result)

        if not tool_results:
            return llm_response, []

        # Synthesize results
        tool_tuples = [(r.tool_name, r.args, r.output) for r in tool_results]
        synthesis_prompt = self.prompt_builder.build_synthesis_prompt(query, tool_tuples)

        final_response = await self._call_llm_async(synthesis_prompt)

        return final_response, tool_results

    async def _attempt_direct_tool_selection_async(
        self,
        query: str,
        context: ExecutionContext
    ) -> list[ToolCall]:
        """Attempt direct tool selection asynchronously"""
        tools = context.relevant_tools if context.relevant_tools else self.tool_executor.tool_registry.get_all()
        if not tools:
            return []

        direct_prompt = self.prompt_builder.build_direct_tool_prompt(query, tools)
        self._log_trace(context.trace_id, "direct_tool_selection_async", {
            "query_preview": query[:100],
            "tools_available": [t.name for t in tools]
        })

        try:
            response = await self._call_llm_async(direct_prompt)
            tool_calls = self.tool_executor.parse_tool_calls(response, query)

            if tool_calls:
                self._log_info(f"Direct selection (async) found: {[tc.name for tc in tool_calls]}")
            else:
                self._log_info("Direct tool selection (async) yielded no results")

            return tool_calls

        except Exception as e:
            self._log_error(f"Direct tool selection (async) failed: {e}")
            return []

    def _call_llm(self, prompt: str, **kwargs) -> str:
        """Call LLM with fallback support"""
        providers = [self.llm_provider, *self.fallback_providers]

        for provider in providers:
            try:
                return provider.generate(prompt, **kwargs)
            except Exception as e:
                self._log_warning(f"Provider {provider.__class__.__name__} failed: {e}")
                continue

        raise RuntimeError("All LLM providers failed")

    async def _call_llm_async(self, prompt: str, **kwargs) -> str:
        """Call LLM asynchronously with fallback support"""
        providers = [self.llm_provider, *self.fallback_providers]

        for provider in providers:
            try:
                if hasattr(provider, 'generate_async'):
                    return await provider.generate_async(prompt, **kwargs)
                else:
                    # Fallback to sync in thread pool
                    loop = asyncio.get_event_loop()
                    return await loop.run_in_executor(
                        None,
                        lambda: provider.generate(prompt, **kwargs)
                    )
            except Exception as e:
                self._log_warning(f"Provider {provider.__class__.__name__} failed: {e}")
                continue

        raise RuntimeError("All LLM providers failed")

    def _update_memory(self, query: str, response: AgentResponse) -> None:
        """Update conversation memory"""
        if not self.memory:
            return

        tool_used = response.tools_used[0][0] if response.tools_used else None
        tool_output = response.tool_outputs[0][2] if response.tool_outputs else None

        self.memory.add_turn(
            query=query,
            response=response.response,
            tool_used=tool_used,
            tool_output=tool_output
        )

    # Logging helpers
    def _log_trace(self, trace_id: int, step: str, data: dict[str, Any]) -> None:
        if self.logger and hasattr(self.logger, 'trace_step'):
            self.logger.trace_step(trace_id, step, data)
        else:
            logger.debug(f"[{trace_id}] {step}: {data}")

    def _log_warning(self, msg: str) -> None:
        if self.logger:
            self.logger.warning(msg)
        else:
            logger.warning(msg)

    def _log_error(self, msg: str) -> None:
        if self.logger:
            self.logger.error(msg)
        else:
            logger.error(msg)
