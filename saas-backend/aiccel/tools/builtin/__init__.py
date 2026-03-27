# aiccel/tools/builtin/__init__.py
"""
Built-in Tools for AICCEL
=========================

Ready-to-use tools that can be added to any agent.
"""

# Search tools
# Calculator tool (simple implementation)
from ..base import BaseTool, ParameterSchema, ParameterType, ToolResult
from .search import SearchProvider, SearchTool, SerperSearchProvider, TavilySearchProvider

# Weather tools
from .weather import OpenWeatherProvider, WeatherProvider, WeatherTool


class CalculatorTool(BaseTool):
    """
    Mathematical calculator tool.

    Evaluates mathematical expressions safely.

    Usage:
        calc = CalculatorTool()
        result = calc.execute({"expression": "2 + 2 * 3"})
    """

    def __init__(self):
        super().__init__(
            name="calculator",
            description="Evaluate mathematical expressions. Supports +, -, *, /, (, ), and basic math functions.",
            parameters=[
                ParameterSchema(
                    name="expression",
                    type=ParameterType.STRING,
                    description="Mathematical expression to evaluate (e.g., '2 + 2 * 3')",
                    required=True
                )
            ]
        )

    def _execute(self, args):
        import math
        expression = args.get("expression", "")

        # Safe evaluation - only allow math operations
        allowed_names = {
            "abs": abs, "round": round, "min": min, "max": max,
            "sum": sum, "pow": pow,
            "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos,
            "tan": math.tan, "log": math.log, "log10": math.log10,
            "pi": math.pi, "e": math.e
        }

        # Clean expression (remove anything not allowed)
        import re
        if not re.match(r'^[\d\s\+\-\*\/\(\)\.\,\w]+$', expression):
            raise ValueError(f"Invalid characters in expression: {expression}")

        try:
            # Evaluate with restricted namespace
            result = eval(expression, {"__builtins__": {}}, allowed_names)
            return {"result": result, "expression": expression}
        except Exception as e:
            raise ValueError(f"Failed to evaluate '{expression}': {e}")


class DateTimeTool(BaseTool):
    """
    Date and time utility tool.

    Get current date/time or parse/format dates.

    Usage:
        dt = DateTimeTool()
        result = dt.execute({"action": "now"})
    """

    def __init__(self):
        super().__init__(
            name="datetime",
            description="Get current date/time or perform date calculations.",
            parameters=[
                ParameterSchema(
                    name="action",
                    type=ParameterType.STRING,
                    description="Action to perform: 'now', 'today', 'utc', 'parse', 'format'",
                    required=True,
                    enum=["now", "today", "utc", "parse", "format", "add_days"]
                ),
                ParameterSchema(
                    name="value",
                    type=ParameterType.STRING,
                    description="Optional value for parse/format/add operations",
                    required=False
                ),
                ParameterSchema(
                    name="days",
                    type=ParameterType.INTEGER,
                    description="Number of days to add (for add_days action)",
                    required=False
                )
            ]
        )

    def _execute(self, args):
        from datetime import datetime, timedelta, timezone

        action = args.get("action", "now")
        value = args.get("value")
        days = args.get("days", 0)

        if action == "now":
            now = datetime.now()
            return {
                "datetime": now.isoformat(),
                "timestamp": now.timestamp(),
                "formatted": now.strftime("%Y-%m-%d %H:%M:%S")
            }

        elif action == "today":
            today = datetime.now().date()
            return {
                "date": today.isoformat(),
                "formatted": today.strftime("%B %d, %Y"),
                "weekday": today.strftime("%A")
            }

        elif action == "utc":
            utc_now = datetime.now(timezone.utc)
            return {
                "datetime": utc_now.isoformat(),
                "timestamp": utc_now.timestamp()
            }

        elif action == "add_days":
            base = datetime.now()
            if value:
                base = datetime.fromisoformat(value)
            result = base + timedelta(days=days)
            return {
                "datetime": result.isoformat(),
                "formatted": result.strftime("%Y-%m-%d %H:%M:%S")
            }

        elif action == "parse" and value:
            # Try common formats
            formats = [
                "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d",
                "%d-%m-%Y", "%d/%m/%Y", "%B %d, %Y"
            ]
            for fmt in formats:
                try:
                    parsed = datetime.strptime(value, fmt)
                    return {
                        "datetime": parsed.isoformat(),
                        "timestamp": parsed.timestamp()
                    }
                except ValueError:
                    continue
            raise ValueError(f"Could not parse date: {value}")

        else:
            raise ValueError(f"Unknown action: {action}")


class DummyTool(BaseTool):
    """
    Dummy tool for testing purposes.

    Simply echoes back the input.
    """

    def __init__(self):
        super().__init__(
            name="dummy",
            description="A dummy tool for testing that echoes input.",
            parameters=[
                ParameterSchema(
                    name="input",
                    type=ParameterType.STRING,
                    description="Input to echo back",
                    required=True
                )
            ]
        )

    def _execute(self, args):
        return {"echo": args.get("input", ""), "status": "ok"}


__all__ = [
    # Calculator
    "CalculatorTool",
    # DateTime
    "DateTimeTool",
    # Testing
    "DummyTool",
    "OpenWeatherProvider",
    "SearchProvider",
    # Search
    "SearchTool",
    "SerperSearchProvider",
    "TavilySearchProvider",
    "WeatherProvider",
    # Weather
    "WeatherTool",
]
