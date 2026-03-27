# aiccel/execution/prompt_builder.py
"""
Prompt Builder
==============

Centralized prompt building with caching.
Extracted from agent.py for better modularity.
"""

import logging
from typing import Any

import orjson
from cachetools import TTLCache


logger = logging.getLogger(__name__)


class PromptBuilder:
    """
    Centralized prompt building with caching.
    Separates prompt logic from execution logic.
    """

    # Class-level cache for static prompts
    _prompt_cache = TTLCache(maxsize=100, ttl=3600)

    # Tool tags
    TOOL_START = "[TOOL]"
    TOOL_END = "[/TOOL]"
    NO_TOOL_START = "[NO_TOOL]"
    NO_TOOL_END = "[/NO_TOOL]"

    def __init__(self, config, tool_registry, logger_instance=None):
        """
        Initialize prompt builder.

        Args:
            config: Agent configuration
            tool_registry: Tool registry
            logger_instance: Optional logger instance
        """
        self.config = config
        self.tool_registry = tool_registry
        self.logger = logger_instance or logger

    def build_main_prompt(
        self,
        query: str,
        relevant_tools: list,
        memory_context: str
    ) -> str:
        """
        Build main execution prompt with tools and context.

        Args:
            query: User query
            relevant_tools: List of relevant tools
            memory_context: Conversation history

        Returns:
            Complete prompt string
        """
        cache_key = self._get_prompt_cache_key(relevant_tools)

        if cache_key in self._prompt_cache:
            static_parts = self._prompt_cache[cache_key]
        else:
            static_parts = self._build_static_parts(relevant_tools)
            self._prompt_cache[cache_key] = static_parts

        return self._assemble_prompt(query, static_parts, memory_context, relevant_tools)

    def build_thinking_prompt(self, query: str, has_tools: bool) -> str:
        """Build prompt for thinking phase"""
        tool_info = self._get_tool_summary() if has_tools else "None"

        return (
            f"Instructions: {self.config.instructions}\n\n"
            f"Think step-by-step about how to answer this query: {query}\n\n"
            f"Available tools: {tool_info}\n\n"
            "Consider:\n"
            "1. What information is needed to answer this query?\n"
            "2. Can the available tools help gather this information?\n"
            "3. If multiple tools are needed, in what order should they be used?\n"
            "4. What is the most efficient approach?\n\n"
            "Provide your reasoning:"
        )

    def build_direct_tool_prompt(self, query: str, relevant_tools: list) -> str:
        """Build prompt for direct tool selection"""
        tool_descriptions = self._format_tool_descriptions(relevant_tools, with_examples=True)

        return (
            f"Instructions: {self.config.instructions}\n\n"
            f"Query: {query}\n\n"
            f"This query requires using one or more tools. Select ALL appropriate tools from:\n"
            f"{tool_descriptions}\n\n"
            "Output ALL necessary tool calls, each in the format:\n"
            f'{self.TOOL_START}{{"name":"tool_name","args":{{"param":"value"}}}}{self.TOOL_END}\n\n'
            "If multiple tools are needed, include multiple tags, one per tool.\n"
            "Response:"
        )

    def build_synthesis_prompt(
        self,
        query: str,
        tool_outputs: list[tuple[str, dict[str, Any], str]]
    ) -> str:
        """Build prompt for synthesizing tool outputs"""
        output_sections = []

        for tool_name, tool_args, tool_output in tool_outputs:
            output_sections.append(
                f"Tool: {tool_name}\n"
                f"Arguments: {tool_args}\n"
                f"Output:\n{tool_output}\n"
            )

        synthesis_instructions = (
            " You MUST NOT use any general knowledge beyond the tool outputs."
            if self.config.strict_tool_usage
            else " You may supplement with your knowledge if the tool outputs are insufficient."
        )

        return (
            f"Instructions: {self.config.instructions}\n\n"
            f'Original query: "{query}"\n\n'
            "Tool outputs:\n" + "\n".join(output_sections) + "\n\n"
            "Based on the tool outputs above, formulate a comprehensive answer to the original query."
            f"{synthesis_instructions}\n\n"
            "Integrate information from all tools and provide a clear, concise response.\n\n"
            "Response:"
        )

    def _build_static_parts(self, relevant_tools: list) -> dict[str, str]:
        """Build static parts of prompt (cached)"""
        has_tools = bool(self.tool_registry.get_all())

        parts = {
            "base": f"Instructions: {self.config.instructions}\n\n",
            "tools": "",
            "tool_usage": ""
        }

        if has_tools:
            all_tools = self.tool_registry.get_all()
            parts["tools"] = self._format_tool_descriptions(all_tools)
            parts["tool_usage"] = self._build_tool_usage_instructions(relevant_tools)
        else:
            parts["tools"] = "No tools are available.\n"
            parts["tool_usage"] = (
                "Answer the query directly using your knowledge."
                if not self.config.strict_tool_usage
                else f"{self.NO_TOOL_START}No tools available. Cannot answer.{self.NO_TOOL_END}"
            )

        return parts

    def _build_tool_usage_instructions(self, relevant_tools: list) -> str:
        """Build instructions for tool usage"""
        base_instructions = (
            "Tool usage guidelines:\n"
            "1. Analyze if any tools can help answer the query\n"
            f'2. Use the EXACT format: {self.TOOL_START}{{"name":"tool_name","args":{{"param":"value"}}}}{self.TOOL_END}\n'
            "3. Include ALL necessary tools if multiple are relevant\n"
            "4. ALWAYS prefer specific tools (e.g. get_weather, get_stock_price) over generic tools (e.g. search) if available.\n"
        )

        if self.config.strict_tool_usage:
            base_instructions += (
                "4. You MUST use tools if available - do NOT answer without tools\n"
                f"5. If no appropriate tool exists, output: {self.NO_TOOL_START}Cannot answer without appropriate tools{self.NO_TOOL_END}\n"
            )
        else:
            base_instructions += (
                "4. If no tool is needed, provide a direct response\n"
                "5. If tools fail, explain what went wrong\n"
            )

        if relevant_tools:
            tool_names = ", ".join(t.name for t in relevant_tools)
            base_instructions += f"\nRelevant tools for this query: {tool_names}\n"

        return base_instructions

    def _assemble_prompt(
        self,
        query: str,
        static_parts: dict[str, str],
        memory_context: str,
        relevant_tools: list
    ) -> str:
        """Assemble final prompt from parts"""
        max_length = getattr(self.config, 'max_prompt_length', 8000)

        parts = [static_parts["base"]]

        if memory_context:
            parts.append(f"{memory_context}\n\n")

        parts.append(f"Current Query: {query[:max_length]}\n\n")

        if static_parts["tools"]:
            parts.append(f"Available tools:\n{static_parts['tools']}\n\n")

        parts.append(static_parts["tool_usage"])

        return "".join(parts)

    def _format_tool_descriptions(
        self,
        tools: list,
        with_examples: bool = False
    ) -> str:
        """Format tool descriptions"""
        descriptions = []

        for tool in tools:
            desc = f"- {tool.name}: {tool.description}"

            if with_examples and hasattr(tool, 'example_usages') and tool.example_usages:
                example = tool.example_usages[0]
                desc += f"\n  Example: {self.TOOL_START}{orjson.dumps(example).decode('utf-8')}{self.TOOL_END}"

            descriptions.append(desc)

        return "\n".join(descriptions)

    def _get_tool_summary(self) -> str:
        """Get summary of available tools"""
        tools = self.tool_registry.get_all()
        if not tools:
            return "None"
        return ", ".join(t.name for t in tools)

    def _get_prompt_cache_key(self, relevant_tools: list) -> str:
        """Generate cache key for prompt"""
        tool_key = tuple(sorted(t.name for t in self.tool_registry.get_all()))
        relevant_key = tuple(sorted(t.name for t in relevant_tools))
        return f"{tool_key}:{relevant_key}:{self.config.strict_tool_usage}"
