# aiccel/agent/prompt_builder.py
"""
Prompt Builder
==============

Centralized prompt building with caching.
Separates prompt logic from execution logic.
"""

from typing import Any

import orjson
from cachetools import TTLCache

from ..constants import Cache, Limits, ToolTags
from .config import AgentConfig


class PromptBuilder:
    """
    Centralized prompt building with caching.
    Separates prompt logic from execution logic.
    """

    # Class-level cache for static prompts
    _prompt_cache: TTLCache = TTLCache(maxsize=Cache.DEFAULT_MAX_SIZE, ttl=Cache.DEFAULT_TTL)

    def __init__(self, config: AgentConfig, tool_registry: Any) -> None:
        """
        Initialize prompt builder.

        Args:
            config: Agent configuration
            tool_registry: Tool registry instance
        """
        self.config = config
        self.tool_registry = tool_registry

    def build_main_prompt(
        self,
        query: str,
        relevant_tools: list[Any],
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

    def build_direct_tool_prompt(self, query: str, relevant_tools: list[Any]) -> str:
        """Build prompt for direct tool selection"""
        tool_descriptions = self._format_tool_descriptions(relevant_tools, with_examples=True)

        return (
            f"Instructions: {self.config.instructions}\n\n"
            f"Query: {query}\n\n"
            f"This query requires using one or more tools. Select ALL appropriate tools from:\n"
            f"{tool_descriptions}\n\n"
            "Output ALL necessary tool calls, each in the format:\n"
            f'{ToolTags.TOOL_START}{{"name":"tool_name","args":{{"param":"value"}}}}{ToolTags.TOOL_END}\n\n'
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

    def _build_static_parts(self, relevant_tools: list[Any]) -> dict[str, str]:
        """Build static parts of prompt (cached)"""
        has_tools = bool(self.tool_registry.get_all()) if self.tool_registry else False

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
                else f"{ToolTags.NO_TOOL_START}No tools available. Cannot answer.{ToolTags.NO_TOOL_END}"
            )

        return parts

    def _build_tool_usage_instructions(self, relevant_tools: list[Any]) -> str:
        """Build instructions for tool usage"""
        # Build concrete examples for each available tool
        tool_examples = []
        if relevant_tools:
            for tool in relevant_tools[:3]:  # Limit to 3 examples
                if tool.name == "get_weather":
                    tool_examples.append(f'{ToolTags.TOOL_START}{{"name":"get_weather","args":{{"location":"New York"}}}}{ToolTags.TOOL_END}')
                elif tool.name == "search":
                    tool_examples.append(f'{ToolTags.TOOL_START}{{"name":"search","args":{{"query":"your search query"}}}}{ToolTags.TOOL_END}')
                else:
                    tool_examples.append(f'{ToolTags.TOOL_START}{{"name":"{tool.name}","args":{{}}}}{ToolTags.TOOL_END}')

        examples_str = "\n".join(tool_examples) if tool_examples else f'{ToolTags.TOOL_START}{{"name":"tool_name","args":{{"param":"value"}}}}{ToolTags.TOOL_END}'

        base_instructions = (
            "CRITICAL: Tool usage format instructions:\n"
            f'When you need to use a tool, you MUST output EXACTLY this format (including the square brackets):\n'
            f'{ToolTags.TOOL_START}{{"name":"TOOL_NAME","args":{{"PARAM":"VALUE"}}}}{ToolTags.TOOL_END}\n\n'
            f'EXAMPLES:\n{examples_str}\n\n'
            "RULES:\n"
            f"1. The tool call MUST be wrapped exactly in {ToolTags.TOOL_START} and {ToolTags.TOOL_END} tags\n"
            "2. Inside the tags, use valid JSON with \"name\" and \"args\" keys\n"
            "3. MULTI-INTENT QUERIES: If the query asks for multiple things (e.g., 'weather in NY and who won the game'), you MUST use MULTIPLE tools.\n"
            "   - Call the first tool: [TOOL]{...}[/TOOL]\n"
            "   - Then call the second tool: [TOOL]{...}[/TOOL]\n"
            "   - Do NOT stop after just one tool if others are needed.\n"
            "4. After the tool tags, you may add your explanation or response\n"
        )

        if self.config.strict_tool_usage:
            base_instructions += (
                f"4. You MUST use tools when available - do NOT answer without tools\n"
                f"5. If no appropriate tool exists, output: {ToolTags.NO_TOOL_START}Cannot answer without appropriate tools{ToolTags.NO_TOOL_END}\n"
            )
        else:
            base_instructions += (
                "4. If no tool is needed for a simple question, just provide a direct answer without tool tags\n"
                "5. If tools fail, explain what went wrong\n"
            )

        if relevant_tools:
            tool_names = ", ".join(t.name for t in relevant_tools)
            base_instructions += f"\nAvailable tools for this query: {tool_names}\n"

        return base_instructions

    def _assemble_prompt(
        self,
        query: str,
        static_parts: dict[str, str],
        memory_context: str,
        relevant_tools: list[Any]
    ) -> str:
        """Assemble final prompt from parts"""
        parts = [static_parts["base"]]

        if memory_context:
            parts.append(f"{memory_context}\n\n")

        # Truncate query if too long
        truncated_query = query[:Limits.MAX_PROMPT_LENGTH]
        parts.append(f"Current Query: {truncated_query}\n\n")

        if static_parts["tools"]:
            parts.append(f"Available tools:\n{static_parts['tools']}\n\n")

        parts.append(static_parts["tool_usage"])

        return "".join(parts)

    def _format_tool_descriptions(
        self,
        tools: list[Any],
        with_examples: bool = False
    ) -> str:
        """Format tool descriptions"""
        descriptions = []

        for tool in tools:
            desc = f"- {tool.name}: {tool.description}"

            if with_examples and hasattr(tool, 'example_usages') and tool.example_usages:
                example = tool.example_usages[0]
                try:
                    example_json = orjson.dumps(example).decode('utf-8')
                    desc += f"\n  Example: {ToolTags.TOOL_START}{example_json}{ToolTags.TOOL_END}"
                except Exception:
                    pass

            descriptions.append(desc)

        return "\n".join(descriptions)

    def _get_tool_summary(self) -> str:
        """Get summary of available tools"""
        if not self.tool_registry:
            return "None"
        tools = self.tool_registry.get_all()
        if not tools:
            return "None"
        return ", ".join(t.name for t in tools)

    def _get_prompt_cache_key(self, relevant_tools: list[Any]) -> str:
        """Generate cache key for prompt"""
        all_tools = self.tool_registry.get_all() if self.tool_registry else []
        tool_key = tuple(sorted(t.name for t in all_tools))
        relevant_key = tuple(sorted(t.name for t in relevant_tools))
        return f"{tool_key}:{relevant_key}:{self.config.strict_tool_usage}"

    def clear_cache(self) -> None:
        """Clear the prompt cache"""
        self._prompt_cache.clear()
