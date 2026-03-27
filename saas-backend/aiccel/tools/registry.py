# aiccel/tools_v2/registry.py
"""
Tool Registry - Improved Tool Management
=========================================

Provides a central registry for tool management with:
- Schema-based validation
- Plugin discovery
- MCP integration
- No hardcoded tool validation
"""

import json
import logging
import re
from typing import Any, Optional, Union

from .base import (
    BaseTool,
    ToolProtocol,
    ToolResult,
    ToolSchema,
    ToolValidator,
)


logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Central registry for managing tools.

    Features:
    - Register tools by instance or schema
    - Schema-based validation (no hardcoded tool names)
    - LLM-based tool selection
    - MCP server integration

    Usage:
        registry = ToolRegistry()

        # Register tools
        registry.register(search_tool)
        registry.register(weather_tool)

        # Or register from MCP server
        registry.register_mcp_tools(mcp_adapter.get_tools())

        # Find relevant tools
        tools = registry.find_relevant_tools("What's the weather?")

        # Execute tool
        result = registry.execute("get_weather", {"location": "NYC"})
    """

    def __init__(self, llm_provider = None):
        self._tools: dict[str, ToolProtocol] = {}
        self._validator = ToolValidator()
        self.llm_provider = llm_provider

    def register(self, tool: Union[ToolProtocol, BaseTool]) -> "ToolRegistry":
        """
        Register a tool.

        Args:
            tool: Tool instance to register

        Returns:
            Self for chaining
        """
        name = tool.name

        if name in self._tools:
            logger.warning(f"Overwriting existing tool: {name}")

        self._tools[name] = tool

        # Set LLM provider if available
        if self.llm_provider and hasattr(tool, "set_llm_provider"):
            tool.set_llm_provider(self.llm_provider)

        logger.debug(f"Registered tool: {name}")
        return self

    def register_all(self, tools: list[ToolProtocol]) -> "ToolRegistry":
        """
        Register multiple tools.

        Args:
            tools: List of tool instances

        Returns:
            Self for chaining
        """
        for tool in tools:
            self.register(tool)
        return self

    def unregister(self, name: str) -> bool:
        """
        Unregister a tool.

        Args:
            name: Tool name

        Returns:
            True if tool was removed, False if not found
        """
        if name in self._tools:
            del self._tools[name]
            logger.debug(f"Unregistered tool: {name}")
            return True
        return False

    def get(self, name: str) -> Optional[ToolProtocol]:
        """
        Get tool by name with intelligent fuzzy matching.

        Args:
            name: Tool name

        Returns:
            Tool instance or None
        """
        if not name:
            return None

        name_lower = name.lower()

        # 1. Exact match
        if name_lower in self._tools:
            return self._tools[name_lower]

        # 2. Fuzzy match
        # Handle cases where LLM output 'weather' but tool is 'get_weather'
        candidates = []
        for tool_name, tool in self._tools.items():
            # Check if requested name part of tool name (weather -> get_weather)
            if name_lower in tool_name or tool_name in name_lower:
                candidates.append(tool)

        if len(candidates) == 1:
            logger.info(f"Intelligently matched tool '{name}' to '{candidates[0].name}'")
            return candidates[0]

        return None

    def get_all(self) -> list[ToolProtocol]:
        """Get all registered tools"""
        return list(self._tools.values())

    def has(self, name: str) -> bool:
        """Check if tool exists"""
        return name.lower() in self._tools if name else False

    @property
    def names(self) -> list[str]:
        """Get all tool names"""
        return list(self._tools.keys())

    @property
    def count(self) -> int:
        """Get number of registered tools"""
        return len(self._tools)

    def validate(self, name: str, args: dict[str, Any]) -> tuple[bool, list[str]]:
        """
        Validate arguments for a tool using its schema.

        No hardcoded validation - uses tool's schema.

        Args:
            name: Tool name
            args: Arguments to validate

        Returns:
            Tuple of (is_valid, error_messages)
        """
        tool = self.get(name)
        if not tool:
            return False, [f"Tool not found: {name}"]

        return self._validator.validate(tool.schema, args)

    def execute(
        self,
        name: str,
        args: dict[str, Any],
        validate: bool = True
    ) -> ToolResult:
        """
        Execute a tool by name.

        Args:
            name: Tool name
            args: Tool arguments
            validate: Whether to validate before execution

        Returns:
            ToolResult with execution result
        """
        tool = self.get(name)
        if not tool:
            return ToolResult.fail(f"Tool not found: {name}")

        if validate:
            is_valid, errors = self.validate(name, args)
            if not is_valid:
                return ToolResult.fail(f"Validation failed: {'; '.join(errors)}")

        return tool.execute(args)

    async def execute_async(
        self,
        name: str,
        args: dict[str, Any],
        validate: bool = True
    ) -> ToolResult:
        """
        Execute a tool asynchronously.

        Args:
            name: Tool name
            args: Tool arguments
            validate: Whether to validate before execution

        Returns:
            ToolResult with execution result
        """
        tool = self.get(name)
        if not tool:
            return ToolResult.fail(f"Tool not found: {name}")

        if validate:
            is_valid, errors = self.validate(name, args)
            if not is_valid:
                return ToolResult.fail(f"Validation failed: {'; '.join(errors)}")

        return await tool.execute_async(args)

    def find_relevant_tools(self, query: str) -> list[ToolProtocol]:
        """
        Find tools relevant to a query.

        Uses LLM if available, otherwise uses keyword matching.

        Args:
            query: User query

        Returns:
            List of relevant tools
        """
        if not query or not query.strip():
            return []

        if not self._tools:
            return []

        if self.llm_provider:
            return self._find_tools_with_llm(query)
        else:
            return self._find_tools_with_keywords(query)

    def _find_tools_with_llm(self, query: str) -> list[ToolProtocol]:
        """Find tools using LLM"""
        tool_descriptions = self.get_tool_descriptions()

        prompt = (
            f"Query: {query}\n\n"
            f"Available tools:\n{tool_descriptions}\n\n"
            "Select ALL tools that are relevant for this query.\n"
            "If the query has multiple parts, include tools for ALL parts.\n"
            "Return a JSON array of tool names:\n"
            "[\"tool1\", \"tool2\"]\n\n"
            "Return only the JSON array, no other text."
        )

        try:
            response = self.llm_provider.generate(prompt)
            tool_names = self._parse_tool_names(response)

            relevant = [self._tools[name] for name in tool_names if name in self._tools]
            logger.debug(f"LLM selected tools: {[t.name for t in relevant]}")
            return relevant

        except Exception as e:
            logger.error(f"LLM tool selection failed: {e}")
            return self._find_tools_with_keywords(query)

    def _find_tools_with_keywords(self, query: str) -> list[ToolProtocol]:
        """Find tools using keyword matching"""
        query_lower = query.lower()
        scored_tools = []

        for tool in self._tools.values():
            score = 0

            # Check tool name
            if tool.name in query_lower:
                score += 2

            # Check description words
            desc_words = tool.description.lower().split()
            for word in desc_words[:20]:  # First 20 words
                if len(word) > 3 and word in query_lower:
                    score += 0.5

            # Check schema tags if available
            if hasattr(tool, "schema") and hasattr(tool.schema, "tags"):
                for tag in tool.schema.tags:
                    if tag.lower() in query_lower:
                        score += 1

            if score > 0:
                scored_tools.append((tool, score))

        # Sort by score and return
        scored_tools.sort(key=lambda x: x[1], reverse=True)
        return [t for t, _ in scored_tools]

    def _parse_tool_names(self, response: str) -> list[str]:
        """Parse tool names from LLM response"""
        if not response:
            return []

        # Clean response
        cleaned = response.strip()
        cleaned = re.sub(r'^```(?:json)?\n?', '', cleaned)
        cleaned = re.sub(r'\n?```$', '', cleaned)
        cleaned = cleaned.strip()

        # Try JSON parsing
        try:
            names = json.loads(cleaned)
            if isinstance(names, list):
                return [str(n) for n in names if isinstance(n, str)]
        except json.JSONDecodeError:
            pass

        # Try regex extraction
        match = re.search(r'\[(?:["\'][^"\']*["\'](?:,\s*)?)*\]', cleaned)
        if match:
            try:
                names = json.loads(match.group(0))
                if isinstance(names, list):
                    return [str(n) for n in names if isinstance(n, str)]
            except json.JSONDecodeError:
                pass

        # Extract quoted strings
        quoted = re.findall(r'["\']([^"\']+)["\']', cleaned)
        return [q for q in quoted if q in self._tools]

    def get_tool_descriptions(self) -> str:
        """Get formatted descriptions of all tools"""
        if not self._tools:
            return "No tools available."

        parts = []
        for name, tool in self._tools.items():
            parts.append(f"- {name}: {tool.description}")

        return "\n".join(parts)

    def get_tool_specs(self) -> list[dict[str, Any]]:
        """Get specification dictionaries for all tools"""
        return [tool.to_dict() for tool in self._tools.values()]

    def get_schemas(self) -> dict[str, ToolSchema]:
        """Get all tool schemas"""
        return {name: tool.schema for name, tool in self._tools.items()}

    def to_openai_functions(self) -> list[dict[str, Any]]:
        """Convert tools to OpenAI function calling format"""
        functions = []
        for tool in self._tools.values():
            schema = tool.to_dict()
            functions.append({
                "type": "function",
                "function": {
                    "name": schema["name"],
                    "description": schema["description"],
                    "parameters": schema["parameters"]
                }
            })
        return functions

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return self.has(name)

    def __iter__(self):
        return iter(self._tools.values())


# Backward compatibility alias
Registry = ToolRegistry
