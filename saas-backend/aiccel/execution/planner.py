# aiccel/execution/planner.py
"""
Execution Planner
================

Isolated logic for planning the execution of a query.
Decouples prompt building and strategy selection from the main orchestrator.
"""

import logging
from typing import Any, Optional


logger = logging.getLogger(__name__)

class ExecutionPlanner:
    """
    Handles the planning phase of agent execution.
    Determines if thinking is needed, which tools to use, and builds prompts.
    """

    def __init__(self, prompt_builder, tool_executor):
        self.prompt_builder = prompt_builder
        self.tool_executor = tool_executor

    def plan_thinking(self, query: str, context: Any) -> str:
        """Builds the thinking prompt."""
        return self.prompt_builder.build_thinking_prompt(query, context.has_tools)

    def plan_initial_response(self, query: str, context: Any, memory: Any, thinking: Optional[str]) -> list[dict[str, str]]:
        """Builds the message list for the initial LLM call."""
        memory_context = memory.get_context(max_context_turns=5)
        prompt = self.prompt_builder.build_main_prompt(query, context.relevant_tools, memory_context)

        messages = [{"role": "user", "content": prompt}]

        if thinking:
            messages.append({"role": "assistant", "content": f"Thinking: {thinking}"})
            messages.append({
                "role": "user",
                "content": "Now provide your final answer, using tools as specified."
            })

        return messages

    def parse_tools(self, llm_response: str, query: str) -> list[tuple[str, dict[str, Any]]]:
        """Parses tool calls from LLM response."""
        return self.tool_executor.parse_tool_usage(llm_response, query)

    def plan_direct_tool_selection(self, query: str, context: Any) -> str:
        """Builds a prompt for direct tool selection if parsing fails."""
        tools = context.relevant_tools if context.relevant_tools else self.tool_executor.tool_registry.get_all()
        return self.prompt_builder.build_direct_tool_prompt(query, tools)

    def plan_synthesis(self, query: str, tool_outputs: list[tuple[str, dict[str, Any], str]]) -> str:
        """Builds the synthesis prompt."""
        return self.prompt_builder.build_synthesis_prompt(query, tool_outputs)
