# aiccel/tools/__init__.py
"""
AICCEL Tools System (Unified)
==============================

This is the single, unified tool system for AICCEL v3.3+.

Quick Start:
    from aiccel.tools import BaseTool, ToolResult, ParameterSchema

    class MyTool(BaseTool):
        def __init__(self):
            super().__init__(
                name="my_tool",
                description="Does something useful",
                parameters=[
                    ParameterSchema(name="query", type=ParameterType.STRING, required=True)
                ]
            )

        def _execute(self, args):
            return f"Result for {args['query']}"

Available Classes:
    - BaseTool: Base class for creating tools
    - ToolResult: Result of tool execution
    - ToolSchema: Complete tool schema
    - ParameterSchema: Parameter definition
    - ToolRegistry: Register and manage tools

Built-in Tools:
    - SearchTool: Web search via SerpAPI
    - WeatherTool: Weather lookup via OpenWeatherMap
    - CalculatorTool: Mathematical calculations
    - DateTimeTool: Date/time utilities
"""

# =============================================================================
# CORE EXPORTS - Primary Tool System
# =============================================================================

from .base import (
    BaseTool,
    ParameterSchema,
    # Data Structures
    ParameterType,
    ToolConfigurationError,
    # Exceptions
    ToolError,
    ToolExecutionError,
    # Protocol and Base
    ToolProtocol,
    ToolResult,
    ToolSchema,
    ToolValidationError,
    # Validator
    ToolValidator,
)

# Registry
from .registry import ToolRegistry


# Built-in tools
try:
    from .builtin import (
        CalculatorTool,
        DateTimeTool,
        DummyTool,
        SearchTool,
        WeatherTool,
    )
except ImportError:
    # Builtin tools may depend on optional packages
    SearchTool = None
    WeatherTool = None
    CalculatorTool = None
    DateTimeTool = None
    DummyTool = None


# =============================================================================
# BACKWARDS COMPATIBILITY ALIASES
# =============================================================================

# Legacy aliases for migration
Tool = BaseTool
AsyncTool = BaseTool  # Async handled by base class
FunctionTool = BaseTool  # Use BaseTool with executor


def tool(name=None, description=None, parameters=None):
    """
    Decorator to create a tool from a function.

    Usage:
        @tool(name="search", description="Search the web")
        def search(query: str) -> str:
            return f"Results for {query}"
    """
    def decorator(func):
        from .base import ParameterSchema, ParameterType

        tool_name = name or func.__name__
        tool_desc = description or func.__doc__ or "No description"

        return BaseTool(
            name=tool_name,
            description=tool_desc,
            parameters=parameters or [],
            executor=lambda args: func(**args)
        )
    return decorator


# Legacy wrapper function
def convert_legacy_tool(legacy_tool):
    """Convert old-style tool to new BaseTool format."""
    return BaseTool(
        name=getattr(legacy_tool, 'name', 'unknown'),
        description=getattr(legacy_tool, 'description', ''),
        executor=lambda args: legacy_tool.execute(args) if hasattr(legacy_tool, 'execute') else str(args)
    )


LegacyToolWrapper = convert_legacy_tool  # Alias


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "AsyncTool",  # Alias
    "BaseTool",
    "CalculatorTool",
    "DateTimeTool",
    "DummyTool",
    "FunctionTool",  # Alias
    # Legacy
    "LegacyToolWrapper",
    "ParameterSchema",
    # Data Structures
    "ParameterType",
    # Built-in Tools
    "SearchTool",
    "Tool",  # Alias
    "ToolConfigurationError",
    # Exceptions
    "ToolError",
    "ToolExecutionError",
    # Base Classes
    "ToolProtocol",
    # Registry
    "ToolRegistry",
    "ToolResult",
    "ToolSchema",
    "ToolValidationError",
    # Validator
    "ToolValidator",
    "WeatherTool",
    "convert_legacy_tool",
    # Decorator
    "tool",
]
