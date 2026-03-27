# aiccel/agent/tool_executor.py
"""
Tool Executor
=============

Handles tool selection, validation, and execution with caching.
"""

import logging
import re
from typing import Any, Callable, Optional

import orjson
from cachetools import TTLCache

from ..constants import Cache, ErrorMessages, Limits, ToolTags
from ..exceptions import ToolExecutionError, ToolNotFoundError
from .config import ToolCall, ToolCallResult


logger = logging.getLogger(__name__)


class AgentToolExecutor:
    """
    Handles tool selection, validation, and execution.

    Features:
    - Circuit breaker for failing tools
    - Local and shared caching
    - Automatic argument fixing
    - Multiple parsing fallback patterns
    """

    def __init__(
        self,
        tool_registry: Any,
        llm_provider: Any,
        agent_logger: Optional[Any] = None,
        strict_mode: bool = False,
        max_cache_size: int = Cache.DEFAULT_MAX_SIZE,
        cache_ttl: int = Cache.DEFAULT_TTL,
        max_failures: int = Limits.MAX_TOOL_RETRIES
    ) -> None:
        """
        Initialize tool executor.

        Args:
            tool_registry: Registry containing available tools
            llm_provider: LLM provider for tool selection
            agent_logger: Logger instance
            strict_mode: Whether to require tool usage
            max_cache_size: Maximum cache size
            cache_ttl: Cache TTL in seconds
            max_failures: Max failures before circuit breaker trips
        """
        self.tool_registry = tool_registry
        self.llm_provider = llm_provider
        self.logger = agent_logger
        self.strict_mode = strict_mode
        self.max_tool_failures = max_failures

        # Circuit breaker for failing tools
        self.tool_failure_count: dict[str, int] = {}

        # Tool execution cache
        self.tool_cache: TTLCache = TTLCache(maxsize=max_cache_size, ttl=cache_ttl)

        # Shared cache access (set by AgentManager if available)
        self._get_from_shared_cache: Optional[Callable[[str], Optional[str]]] = None
        self._set_in_shared_cache: Optional[Callable[[str, str], None]] = None

    def find_relevant_tools(self, query: str) -> list[Any]:
        """Find tools relevant to the query"""
        if not query or not query.strip():
            self._log_warning("Empty query provided for tool selection")
            return []

        return self.tool_registry.find_relevant_tools(query)

    def should_skip_tool(self, tool_name: str) -> bool:
        """Check if tool should be skipped due to repeated failures"""
        failure_count = self.tool_failure_count.get(tool_name, 0)
        if failure_count >= self.max_tool_failures:
            self._log_warning(
                f"Tool {tool_name} circuit breaker open (failures: {failure_count})"
            )
            return True
        return False

    def record_tool_failure(self, tool_name: str) -> None:
        """Record a tool failure"""
        self.tool_failure_count[tool_name] = self.tool_failure_count.get(tool_name, 0) + 1
        self._log_debug(f"Tool {tool_name} failure count: {self.tool_failure_count[tool_name]}")

    def record_tool_success(self, tool_name: str) -> None:
        """Reset failure count on success"""
        if tool_name in self.tool_failure_count:
            del self.tool_failure_count[tool_name]
            self._log_debug(f"Tool {tool_name} failure count reset")

    def generate_cache_key(self, tool_name: str, tool_args: dict[str, Any]) -> str:
        """Generate consistent cache key for tool execution"""
        try:
            args_json = orjson.dumps(tool_args, option=orjson.OPT_SORT_KEYS).decode('utf-8')
            return f"{tool_name}:{args_json}"
        except Exception as e:
            self._log_warning(f"Failed to generate cache key: {e}")
            return f"{tool_name}:{tool_args!s}"

    def execute_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        trace_id: int = 0,
        original_query: str = ""
    ) -> ToolCallResult:
        """
        Execute tool with caching support.

        Args:
            tool_name: Name of the tool
            tool_args: Tool arguments
            trace_id: Trace ID for logging
            original_query: Original query for context

        Returns:
            ToolCallResult with execution details
        """
        import time
        start_time = time.time()

        # Generate cache key
        cache_key = self.generate_cache_key(tool_name, tool_args)

        # Try shared cache first
        if self._get_from_shared_cache:
            cached_output = self._get_from_shared_cache(cache_key)
            if cached_output is not None:
                self._log_trace(trace_id, "shared_cache_hit", {"tool": tool_name})
                self.record_tool_success(tool_name)
                return ToolCallResult(
                    tool_name=tool_name,
                    args=tool_args,
                    output=cached_output,
                    success=True,
                    execution_time=time.time() - start_time
                )

        # Try local cache
        if cache_key in self.tool_cache:
            cached_output = self.tool_cache[cache_key]
            self._log_trace(trace_id, "local_cache_hit", {"tool": tool_name})
            self.record_tool_success(tool_name)
            return ToolCallResult(
                tool_name=tool_name,
                args=tool_args,
                output=cached_output,
                success=True,
                execution_time=time.time() - start_time
            )

        # Get tool from registry
        tool = self.tool_registry.get(tool_name)
        if not tool:
            error_msg = ErrorMessages.TOOL_NOT_FOUND.format(tool_name=tool_name)
            self._log_error(error_msg)
            raise ToolNotFoundError(tool_name, list(self.tool_registry.tools.keys()))

        self._log_trace(trace_id, "execute_tool_start", {"tool": tool_name, "args": tool_args})

        # Auto-fill common missing parameters
        fixed_args = self._fix_tool_args(tool_name, tool_args, original_query)

        try:
            # Execute tool (returns aiccel.interfaces.ToolResult)
            tool_result = tool.execute(fixed_args)

            # Convert result to string for Agent/LLM consumption
            output_str = str(tool_result)

            # Check for failure in result
            if not tool_result.success:
                self.record_tool_failure(tool_name)
                return ToolCallResult(
                    tool_name=tool_name,
                    args=fixed_args,
                    output=output_str,
                    success=False,
                    execution_time=time.time() - start_time,
                    error=tool_result.error
                )

            # Success - handling
            self.record_tool_success(tool_name)

            # Use data string for caching
            self.tool_cache[cache_key] = output_str

            if self._set_in_shared_cache:
                self._set_in_shared_cache(cache_key, output_str)

            self._log_trace(trace_id, "execute_tool_complete", {
                "tool": tool_name,
                "output_preview": output_str[:100]
            })

            return ToolCallResult(
                tool_name=tool_name,
                args=fixed_args,
                output=output_str,
                success=True,
                execution_time=time.time() - start_time
            )

        except Exception as e:
            self.record_tool_failure(tool_name)
            error_msg = f"Error executing tool {tool_name}: {e!s}"
            self._log_error(error_msg)
            raise ToolExecutionError(tool_name, error_msg, e)

    def parse_tool_calls(
        self,
        response: str,
        original_query: str = ""
    ) -> list[ToolCall]:
        """
        Parse tool usage from LLM response with strict validation.

        Args:
            response: LLM response text
            original_query: Original query for context

        Returns:
            List of ToolCall objects
        """
        tool_calls: list[ToolCall] = []

        # Step 1: Check for NO_TOOL tag
        no_tool_pattern = rf'\{ToolTags.NO_TOOL_START}(.*?)\{ToolTags.NO_TOOL_END}'
        no_tool_match = re.search(no_tool_pattern, response, re.DOTALL)
        if no_tool_match:
            self._log_info("Parsed [NO_TOOL] tag")
            return []

        # Step 2: Parse [TOOL] tags (primary format)
        tool_pattern = rf'\{ToolTags.TOOL_START}(.*?)\{ToolTags.TOOL_END}'
        matches = re.findall(tool_pattern, response, re.DOTALL)

        for match in matches:
            tool_call = self._parse_single_tool_call(match, original_query)
            if tool_call:
                tool_calls.append(tool_call)

        # Step 3: If primary parsing failed, try alternate patterns
        if not tool_calls:
            self._log_info("Primary [TOOL] parsing found nothing, trying alternate patterns")
            tool_calls = self._parse_alternate_patterns(response, original_query)

        # Step 4: If still no results, try to detect tool names directly in response
        if not tool_calls:
            tool_calls = self._detect_implicit_tool_calls(response, original_query)

        return tool_calls

    def _detect_implicit_tool_calls(
        self,
        response: str,
        original_query: str
    ) -> list[ToolCall]:
        """
        Detect tool calls when LLM mentions tool name but doesn't use proper format.
        This is a last-resort recovery mechanism.
        """
        tool_calls: list[ToolCall] = []

        # Get all registered tool names
        registered_tools = {t.name.lower(): t.name for t in self.tool_registry.get_all()}

        response_lower = response.lower()

        for tool_name_lower, tool_name in registered_tools.items():
            # Check if tool name appears in response with some form of calling pattern
            patterns = [
                rf'\[{tool_name_lower}\s*\{{(.*?)\}}\s*\]',  # [tool_name{...}]
                rf'{tool_name_lower}\s*\(\s*\{{(.*?)\}}\s*\)',  # tool_name({...})
                rf'use\s+{tool_name_lower}.*?\{{(.*?)\}}',  # use tool_name...{...}
                rf'call\s+{tool_name_lower}.*?\{{(.*?)\}}',  # call tool_name...{...}
            ]

            for pattern in patterns:
                match = re.search(pattern, response_lower, re.DOTALL | re.IGNORECASE)
                if match:
                    try:
                        args_str = match.group(1)
                        # Try to parse as JSON args
                        try:
                            args = orjson.loads('{' + args_str + '}')
                        except:
                            # Attempt to extract key-value pairs
                            args = self._extract_args_from_string(args_str, original_query)

                        if self._validate_tool_args(tool_name, args):
                            tool_calls.append(ToolCall(name=tool_name, args=args))
                            self._log_info(f"Detected implicit tool call: {tool_name}")
                            break
                    except Exception as e:
                        self._log_debug(f"Failed to parse implicit tool call: {e}")
                        continue

        # If we found tool mentions but couldn't parse args, use query as default
        if not tool_calls:
            for tool_name_lower, tool_name in registered_tools.items():
                if tool_name_lower in response_lower:
                    # Check if this seems like a tool invocation context
                    invocation_hints = ['use', 'call', 'invoke', 'execute', '[', '{']
                    if any(hint in response_lower for hint in invocation_hints):
                        fixed_args = self._fix_tool_args(tool_name, {}, original_query)
                        if fixed_args:
                            tool_calls.append(ToolCall(name=tool_name, args=fixed_args))
                            self._log_info(f"Auto-constructed tool call for {tool_name} from query")
                            break

        return tool_calls

    def _extract_args_from_string(self, args_str: str, original_query: str) -> dict:
        """Extract arguments from a malformed string"""
        args = {}

        # Try common patterns
        # "query": "something" or query="something"
        query_match = re.search(r'["\']?query["\']?\s*[:=]\s*["\']([^"\']+)["\']', args_str, re.IGNORECASE)
        if query_match:
            args['query'] = query_match.group(1)

        # "location": "somewhere"
        location_match = re.search(r'["\']?location["\']?\s*[:=]\s*["\']([^"\']+)["\']', args_str, re.IGNORECASE)
        if location_match:
            args['location'] = location_match.group(1)

        # If no args found, use original query
        if not args and original_query:
            args['query'] = original_query

        return args

    def _parse_single_tool_call(
        self,
        match: str,
        original_query: str
    ) -> Optional[ToolCall]:
        """Parse a single tool call from matched text"""
        try:
            tool_json = match.strip()

            # Validate JSON structure
            if not tool_json.startswith('{') or not tool_json.endswith('}'):
                self._log_warning(f"Invalid JSON structure: {tool_json[:50]}")
                return None

            # Parse JSON
            try:
                tool_data = orjson.loads(tool_json)
            except orjson.JSONDecodeError as e:
                self._log_warning(f"JSON parsing failed: {e}, content: {match[:100]}")
                return None

            # Validate structure
            if not self._validate_tool_call(tool_data):
                self._log_warning(f"Tool call validation failed: {tool_data}")
                return None

            tool_name = tool_data.get("name")
            tool_args = tool_data.get("args", {})

            # Validate tool exists
            if not self.tool_registry.get(tool_name):
                self._log_warning(f"Tool '{tool_name}' not found, skipping")
                return None

            # Validate and fix arguments
            if not self._validate_tool_args(tool_name, tool_args):
                self._log_warning(f"Invalid arguments for '{tool_name}': {tool_args}")
                tool_args = self._fix_tool_args(tool_name, tool_args, original_query)

            self._log_debug(f"Parsed tool call: {tool_name} with args: {tool_args}")

            return ToolCall(name=tool_name, args=tool_args, raw_json=tool_json)

        except Exception as e:
            self._log_error(f"Error parsing tool: {e}")
            return None

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
        """Validate tool arguments against tool schema"""
        tool = self.tool_registry.get(tool_name)
        if not tool:
            return False

        # Check if tool has schema validation
        if hasattr(tool, 'validate_args'):
            return tool.validate_args(args)

        # Fallback validation for known tools
        if tool_name == "search":
            return any(key in args for key in ["query", "q", "search", "text"])

        if tool_name == "get_weather":
            return any(key in args for key in ["location", "city", "place"])

        if tool_name == "pdf_rag":
            return "query" in args or len(args) == 0

        return isinstance(args, dict)

    def _fix_tool_args(
        self,
        tool_name: str,
        args: dict[str, Any],
        original_query: str = ""
    ) -> dict[str, Any]:
        """Attempt to fix common tool argument issues"""
        fixed_args = args.copy()

        # Fix pdf_rag missing query
        if tool_name == "pdf_rag" and "query" not in fixed_args and original_query:
            fixed_args["query"] = original_query
            self._log_info(f"Auto-fixed pdf_rag query: {original_query[:50]}")

        # Fix search tool missing query
        if tool_name == "search" and not any(key in fixed_args for key in ["query", "q"]):
            if original_query:
                fixed_args["query"] = original_query
                self._log_info(f"Auto-fixed search query: {original_query[:50]}")

        # Fix weather tool missing location
        if tool_name == "get_weather" and not any(key in fixed_args for key in ["location", "city"]):
            location_match = re.search(
                r'weather.*?(?:in|at|for)\s+([A-Za-z\s,]+)',
                original_query,
                re.IGNORECASE
            )
            if location_match:
                fixed_args["location"] = location_match.group(1).strip()
                self._log_info(f"Auto-extracted location: {fixed_args['location']}")

        return fixed_args

    def _parse_alternate_patterns(
        self,
        response: str,
        original_query: str
    ) -> list[ToolCall]:
        """Parse alternate tool call patterns"""
        tool_calls: list[ToolCall] = []

        alt_patterns = [
            r'```json\n\s*{\s*"name":\s*"([^"]+)",\s*"args":\s*({.*?})\s*}\s*```',
            r'Tool:\s*([a-z_]+).*?Args:.*?({.*?})',
            r'\[([a-zA-Z0-9_-]+)(\{.*?\})\]',  # [tool_name{...}]
            r'([a-zA-Z0-9_-]+)\(({.*?})\)',     # tool_name({...})
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
                            # Handle nested "args" if LLM outputted {"name": "...", "args": {...}} inside the pattern
                            if isinstance(tool_args, dict) and "args" in tool_args and isinstance(tool_args["args"], dict):
                                tool_args = tool_args["args"]
                        except Exception:
                            tool_args = {"query": args_str.strip('" ')}

                        # Validate and fix args
                        if not self._validate_tool_args(tool_name, tool_args):
                            tool_args = self._fix_tool_args(tool_name, tool_args, original_query)

                        if self._validate_tool_args(tool_name, tool_args):
                            tool_calls.append(ToolCall(name=tool_name, args=tool_args))
                            self._log_info(f"Parsed tool from alternate pattern: {tool_name}")

                except Exception as e:
                    self._log_warning(f"Failed to parse alternate pattern: {e}")
                    continue

        # If still no tool calls, try a very broad JSON search
        if not tool_calls:
            json_matches = re.findall(r'({.*?"name":\s*"[^"]+".*?})', response, re.DOTALL)
            for json_str in json_matches:
                try:
                    tool_data = orjson.loads(json_str)
                    if self._validate_tool_call(tool_data):
                        tool_name = tool_data["name"]
                        tool_args = tool_data.get("args", {})
                        if self.tool_registry.get(tool_name):
                            tool_calls.append(ToolCall(name=tool_name, args=tool_args))
                            self._log_info(f"Parsed tool from broad JSON search: {tool_name}")
                except Exception:
                    continue

        return tool_calls

    def reset_failures(self) -> None:
        """Reset all failure counters"""
        self.tool_failure_count.clear()

    def clear_cache(self) -> None:
        """Clear the tool cache"""
        self.tool_cache.clear()

    # Logging helpers to handle optional logger
    def _log_debug(self, msg: str) -> None:
        if self.logger:
            self.logger.debug(msg)
        else:
            logger.debug(msg)

    def _log_info(self, msg: str) -> None:
        if self.logger:
            self.logger.info(msg)
        else:
            logger.info(msg)

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

    def _log_trace(self, trace_id: int, step: str, data: dict[str, Any]) -> None:
        if self.logger and hasattr(self.logger, 'trace_step'):
            self.logger.trace_step(trace_id, step, data)
        else:
            logger.debug(f"[{trace_id}] {step}: {data}")
