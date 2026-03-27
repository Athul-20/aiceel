# aiccel/integrations/openai_functions.py
"""
OpenAI Functions Integration
=============================

Support for OpenAI function calling format.
"""

import json
from typing import TYPE_CHECKING, Any, Optional


if TYPE_CHECKING:
    from ..tools import Tool


class OpenAIFunctionsAdapter:
    """
    Convert AICCEL tools to OpenAI function calling format.

    Usage:
        adapter = OpenAIFunctionsAdapter(tools=[search_tool, weather_tool])
        functions = adapter.get_functions()

        # Use with OpenAI client
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[...],
            functions=functions
        )

        # Execute tool calls
        results = adapter.execute_calls(response.function_call)
    """

    def __init__(self, tools: Optional[list['Tool']] = None):
        self.tools = {tool.name: tool for tool in (tools or [])}

    def add_tool(self, tool: 'Tool') -> 'OpenAIFunctionsAdapter':
        """Add a tool."""
        self.tools[tool.name] = tool
        return self

    def get_functions(self) -> list[dict[str, Any]]:
        """Get tools in OpenAI function format."""
        functions = []

        for tool in self.tools.values():
            func_def = {
                "name": tool.name,
                "description": tool.description,
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }

            # Get parameters
            params = getattr(tool, 'parameters', {})
            if isinstance(params, dict):
                for param_name, param_info in params.items():
                    func_def["parameters"]["properties"][param_name] = {
                        "type": param_info.get("type", "string"),
                        "description": param_info.get("description", "")
                    }
                    if param_info.get("required", True):
                        func_def["parameters"]["required"].append(param_name)

            functions.append(func_def)

        return functions

    def get_tools_format(self) -> list[dict[str, Any]]:
        """Get tools in new OpenAI tools format."""
        return [
            {"type": "function", "function": func}
            for func in self.get_functions()
        ]

    def execute_call(
        self,
        function_call: dict[str, Any]
    ) -> Any:
        """
        Execute a single function call.

        Args:
            function_call: OpenAI function_call object with name/arguments
        """
        name = function_call.get("name")
        args_str = function_call.get("arguments", "{}")

        if name not in self.tools:
            raise ValueError(f"Unknown function: {name}")

        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            args = {}

        tool = self.tools[name]
        return tool.execute(**args)

    async def execute_call_async(
        self,
        function_call: dict[str, Any]
    ) -> Any:
        """Execute a function call asynchronously."""
        name = function_call.get("name")
        args_str = function_call.get("arguments", "{}")

        if name not in self.tools:
            raise ValueError(f"Unknown function: {name}")

        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            args = {}

        tool = self.tools[name]

        if hasattr(tool, 'execute_async'):
            return await tool.execute_async(**args)
        return tool.execute(**args)

    def execute_tool_calls(
        self,
        tool_calls: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Execute multiple tool calls.

        Args:
            tool_calls: List of OpenAI tool_call objects

        Returns:
            List of results
        """
        results = []

        for tc in tool_calls:
            func = tc.get("function", tc)
            result = self.execute_call(func)

            results.append({
                "tool_call_id": tc.get("id", ""),
                "role": "tool",
                "content": str(result)
            })

        return results
