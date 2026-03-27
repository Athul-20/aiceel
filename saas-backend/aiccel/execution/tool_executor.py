# aiccel/execution/tool_executor.py
"""
Tool Executor
=============

Handles tool selection, validation, and execution with caching.
Extracted from agent.py for better modularity.
"""

import logging
import re
from typing import Any, Callable, Optional

import orjson
from cachetools import TTLCache


logger = logging.getLogger(__name__)


class ToolExecutor:
    """
    Handles tool selection, validation, and execution.
    Improved from original with better error handling and caching.
    """

    # Tool tags
    TOOL_START = "[TOOL]"
    TOOL_END = "[/TOOL]"
    NO_TOOL_START = "[NO_TOOL]"
    NO_TOOL_END = "[/NO_TOOL]"

    def __init__(
        self,
        tool_registry,
        llm_provider,
        agent_logger=None,
        strict_mode: bool = False,
        max_cache_size: int = 100,
        cache_ttl: int = 300,
        max_failures: int = 3
    ):
        """
        Initialize tool executor.

        Args:
            tool_registry: Registry containing available tools
            llm_provider: LLM provider for tool selection
            agent_logger: Logger instance
            strict_mode: Whether to require tool usage
            max_cache_size: Maximum size of tool cache
            cache_ttl: Cache TTL in seconds
            max_failures: Max failures before circuit breaker opens
        """
        self.tool_registry = tool_registry
        self.llm_provider = llm_provider
        self.logger = agent_logger or logger
        self.strict_mode = strict_mode

        # Circuit breaker for failing tools
        self.tool_failure_count: dict[str, int] = {}
        self.max_tool_failures = max_failures

        # Tool execution cache
        self.tool_cache = TTLCache(maxsize=max_cache_size, ttl=cache_ttl)

        # Shared cache access (set by AgentManager if available)
        self._get_from_shared_cache: Optional[Callable] = None
        self._set_in_shared_cache: Optional[Callable] = None

        # Plugin hooks (set by agent)
        self._on_before_execute: Optional[Callable] = None
        self._on_after_execute: Optional[Callable] = None
        self._on_error: Optional[Callable] = None

    def find_relevant_tools(self, query: str) -> list:
        """Find tools relevant to the query"""
        if not query or not query.strip():
            if hasattr(self.logger, 'warning'):
                self.logger.warning("Empty query provided for tool selection")
            return []

        return self.tool_registry.find_relevant_tools(query)

    def should_skip_tool(self, tool_name: str) -> bool:
        """Check if tool should be skipped due to repeated failures"""
        failure_count = self.tool_failure_count.get(tool_name, 0)
        if failure_count >= self.max_tool_failures:
            if hasattr(self.logger, 'warning'):
                self.logger.warning(
                    f"Tool {tool_name} circuit breaker open (failures: {failure_count})"
                )
            return True
        return False

    def record_tool_failure(self, tool_name: str) -> None:
        """Record a tool failure"""
        self.tool_failure_count[tool_name] = self.tool_failure_count.get(tool_name, 0) + 1

    def record_tool_success(self, tool_name: str) -> None:
        """Reset failure count on success"""
        if tool_name in self.tool_failure_count:
            del self.tool_failure_count[tool_name]

    def generate_cache_key(self, tool_name: str, tool_args: dict[str, Any]) -> str:
        """Generate consistent cache key for tool execution"""
        try:
            args_json = orjson.dumps(tool_args, option=orjson.OPT_SORT_KEYS).decode('utf-8')
            return f"{tool_name}:{args_json}"
        except Exception:
            return f"{tool_name}:{tool_args!s}"

    def execute_tool_with_cache(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        trace_id: int = 0
    ) -> tuple[str, bool]:
        """
        Execute tool with caching support.

        Args:
            tool_name: Name of the tool
            tool_args: Tool arguments
            trace_id: Trace ID for logging

        Returns:
            Tuple of (result, success)
        """
        # Plugin hook: before execute
        if self._on_before_execute:
            modified_args = self._on_before_execute(tool_name, tool_args)
            if modified_args is not None:
                tool_args = modified_args

        # Generate cache key
        cache_key = self.generate_cache_key(tool_name, tool_args)

        # Try shared cache first
        if self._get_from_shared_cache:
            cached_result = self._get_from_shared_cache(cache_key)
            if cached_result is not None:
                self.record_tool_success(tool_name)
                return cached_result, True

        # Try local cache
        if cache_key in self.tool_cache:
            tool_output = self.tool_cache[cache_key]
            self.record_tool_success(tool_name)
            return tool_output, True

        # Execute tool
        tool = self.tool_registry.get(tool_name)
        if not tool:
            error_msg = f"Tool not found: {tool_name}"
            if hasattr(self.logger, 'error'):
                self.logger.error(error_msg)
            return error_msg, False

        # Auto-fill common missing parameters
        tool_args = self._fix_tool_args(tool_name, tool_args)

        try:
            tool_output = tool.execute(tool_args)

            # Check for errors in output
            if tool_output and isinstance(tool_output, str) and tool_output.startswith("Error"):
                self.record_tool_failure(tool_name)
                if self._on_error:
                    fallback = self._on_error(tool_name, Exception(tool_output))
                    if fallback:
                        return fallback, True
                return tool_output, False

            # Success - cache result
            self.record_tool_success(tool_name)

            # Store in local cache
            self.tool_cache[cache_key] = tool_output

            # Store in shared cache if available
            if self._set_in_shared_cache:
                self._set_in_shared_cache(cache_key, tool_output)

            # Plugin hook: after execute
            if self._on_after_execute:
                modified_output = self._on_after_execute(tool_name, tool_args, tool_output)
                if modified_output is not None:
                    tool_output = modified_output

            return tool_output, True

        except Exception as e:
            self.record_tool_failure(tool_name)
            error_msg = f"Error executing tool {tool_name}: {e!s}"
            if hasattr(self.logger, 'error'):
                self.logger.error(error_msg)

            # Plugin hook: on error
            if self._on_error:
                fallback = self._on_error(tool_name, e)
                if fallback:
                    return fallback, True

            return error_msg, False

    def parse_tool_usage(
        self,
        response: str,
        original_query: str = ""
    ) -> list[tuple[str, dict[str, Any]]]:
        """
        Parse tool usage from LLM response with strict validation.

        Args:
            response: LLM response text
            original_query: Original query for context

        Returns:
            List of (tool_name, tool_args) tuples
        """
        tool_calls = []

        # Step 1: Check for NO_TOOL tag
        no_tool_pattern = rf'\{self.NO_TOOL_START}(.*?)\{self.NO_TOOL_END}'
        no_tool_match = re.search(no_tool_pattern, response, re.DOTALL)
        if no_tool_match:
            return []

        # Step 2: Parse [TOOL] tags
        tool_pattern = rf'\{self.TOOL_START}(.*?)\{self.TOOL_END}'
        matches = re.findall(tool_pattern, response, re.DOTALL)

        for match in matches:
            try:
                tool_json = match.strip()

                # Validate JSON structure
                if not tool_json.startswith('{') or not tool_json.endswith('}'):
                    continue

                # Parse JSON
                try:
                    tool_data = orjson.loads(tool_json)
                except orjson.JSONDecodeError:
                    continue

                # Validate structure
                if not self._validate_tool_call(tool_data):
                    continue

                tool_name = tool_data.get("name")
                tool_args = tool_data.get("args", {})

                # Validate tool exists
                if not self.tool_registry.get(tool_name):
                    continue

                # Validate and fix arguments
                if not self._validate_tool_args(tool_name, tool_args):
                    tool_args = self._fix_tool_args(tool_name, tool_args, original_query)

                tool_calls.append((tool_name, tool_args))

            except Exception:
                continue

        # Step 3: Fallback patterns
        if not tool_calls and matches:
            tool_calls = self._parse_alternate_patterns(response, original_query)

        return tool_calls

    def _validate_tool_call(self, tool_data: Any) -> bool:
        """Validate tool call structure"""
        if not isinstance(tool_data, dict):
            return False
        if "name" not in tool_data:
            return False
        if not isinstance(tool_data["name"], str):
            return False
        return not ("args" in tool_data and not isinstance(tool_data["args"], dict))

    def _validate_tool_args(self, tool_name: str, args: dict[str, Any]) -> bool:
        """
        Validate tool arguments using tool's schema.
        No hardcoded tool names - uses tool's schema if available.
        """
        tool = self.tool_registry.get(tool_name)
        if not tool:
            return False

        # If tool has schema, use it for validation
        if hasattr(tool, 'schema') and hasattr(tool.schema, 'required_parameters'):
            required = tool.schema.required_parameters
            return all(param in args for param in required)

        # Fallback: check if any args provided
        return isinstance(args, dict)

    def _fix_tool_args(
        self,
        tool_name: str,
        args: dict[str, Any],
        original_query: str = ""
    ) -> dict[str, Any]:
        """Attempt to fix common tool argument issues"""
        fixed_args = args.copy()

        tool = self.tool_registry.get(tool_name)
        if not tool:
            return fixed_args

        # Get tool schema if available
        if hasattr(tool, 'schema') and hasattr(tool.schema, 'parameters'):
            # Identify missing required parameters
            missing_required = []
            for param in tool.schema.parameters:
                if param.required and param.name not in fixed_args:
                    missing_required.append(param)

            # Smart fill logic:
            # If exactly one required string parameter is missing and we have the query, use it.
            # This covers the common case where the LLM just outputs the tool name.
            if len(missing_required) == 1:
                param = missing_required[0]
                if param.type.value == "string" and original_query:
                    fixed_args[param.name] = original_query

            # Future improvement: Add more heuristics here

        return fixed_args

    def _parse_alternate_patterns(
        self,
        response: str,
        original_query: str
    ) -> list[tuple[str, dict[str, Any]]]:
        """Parse alternate tool call patterns"""
        tool_calls = []

        alt_patterns = [
            r'```json\n\s*{\s*"name":\s*"([^"]+)",\s*"args":\s*({.*?})\s*}\s*```',
            r'Tool:\s*([a-z_]+).*?Args:.*?({.*?})',
        ]

        for pattern in alt_patterns:
            alt_matches = re.findall(pattern, response, re.DOTALL)
            for alt_match in alt_matches:
                try:
                    if len(alt_match) >= 2:
                        tool_name = alt_match[0]
                        args_str = alt_match[1]

                        # Validate tool exists
                        if not self.tool_registry.get(tool_name):
                            continue

                        # Parse args
                        try:
                            tool_args = orjson.loads(args_str)
                        except Exception:
                            tool_args = {"query": args_str.strip('" ')}

                        # Validate and fix args
                        if not self._validate_tool_args(tool_name, tool_args):
                            tool_args = self._fix_tool_args(tool_name, tool_args, original_query)

                        if self._validate_tool_args(tool_name, tool_args):
                            tool_calls.append((tool_name, tool_args))

                except Exception:
                    continue

        return tool_calls

    def reset_failures(self) -> None:
        """Reset all failure counters"""
        self.tool_failure_count.clear()

    def clear_cache(self) -> None:
        """Clear the tool cache"""
        self.tool_cache.clear()
