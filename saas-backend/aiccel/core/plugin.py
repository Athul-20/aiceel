# aiccel/core/plugin.py
"""
Agent Plugin System
===================

Provides a plugin architecture for extending agent functionality.
Plugins can hook into various stages of the agent execution lifecycle.

Usage:
    from aiccel.core import AgentPlugin, PluginHook

    class LoggingPlugin(AgentPlugin):
        name = "logging"

        def on_before_execute(self, query, context):
            print(f"Executing: {query}")

        def on_after_execute(self, response, context):
            print(f"Response: {response.response[:50]}")

    agent = Agent(provider=provider)
    agent.add_plugin(LoggingPlugin())
"""

import logging
from abc import ABC
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Callable, Optional


if TYPE_CHECKING:
    from .config import ExecutionContext
    from .response import AgentResponse

logger = logging.getLogger(__name__)


class PluginHook(Enum):
    """Available plugin hooks in the agent lifecycle"""
    # Execution lifecycle
    BEFORE_EXECUTE = auto()        # Before query execution starts
    AFTER_EXECUTE = auto()         # After query execution completes
    ON_ERROR = auto()              # When an error occurs

    # Tool lifecycle
    BEFORE_TOOL_SELECT = auto()    # Before tool selection
    AFTER_TOOL_SELECT = auto()     # After tool selection
    BEFORE_TOOL_EXECUTE = auto()   # Before each tool execution
    AFTER_TOOL_EXECUTE = auto()    # After each tool execution
    ON_TOOL_ERROR = auto()         # When tool execution fails

    # LLM lifecycle
    BEFORE_LLM_CALL = auto()       # Before LLM API call
    AFTER_LLM_CALL = auto()        # After LLM API call

    # Memory lifecycle
    BEFORE_MEMORY_UPDATE = auto()  # Before memory is updated
    AFTER_MEMORY_UPDATE = auto()   # After memory is updated

    # Prompt lifecycle
    BEFORE_PROMPT_BUILD = auto()   # Before prompt is built
    AFTER_PROMPT_BUILD = auto()    # After prompt is built


@dataclass
class PluginContext:
    """Context passed to plugin hooks"""
    hook: PluginHook
    agent_name: str
    data: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default=None):
        """Get data by key"""
        return self.data.get(key, default)

    def set(self, key: str, value) -> "PluginContext":
        """Set data by key (for modifying execution)"""
        self.data[key] = value
        return self


class AgentPlugin(ABC):
    """
    Base class for agent plugins.

    Override the methods you want to hook into.
    All methods are optional - only implement what you need.

    Example:
        class MetricsPlugin(AgentPlugin):
            name = "metrics"

            def __init__(self):
                self.execution_count = 0
                self.total_time = 0.0

            def on_before_execute(self, query, context):
                context.add_metadata("start_time", time.time())

            def on_after_execute(self, response, context):
                self.execution_count += 1
                self.total_time += response.execution_time
    """

    # Plugin metadata
    name: str = "base_plugin"
    version: str = "1.0.0"
    description: str = ""
    priority: int = 100  # Lower = earlier execution

    def __init__(self):
        self.enabled = True
        self._agent = None

    def attach(self, agent) -> None:
        """Called when plugin is attached to agent"""
        self._agent = agent
        self.on_attach()

    def detach(self) -> None:
        """Called when plugin is detached from agent"""
        self.on_detach()
        self._agent = None

    # Lifecycle hooks - override as needed

    def on_attach(self) -> None:
        """Called when plugin is attached to an agent"""
        pass

    def on_detach(self) -> None:
        """Called when plugin is detached from an agent"""
        pass

    def on_before_execute(self, query: str, context: "ExecutionContext") -> Optional[str]:
        """
        Called before query execution.

        Args:
            query: The user query
            context: Execution context

        Returns:
            Modified query or None to keep original
        """
        pass

    def on_after_execute(self, response: "AgentResponse", context: "ExecutionContext") -> Optional["AgentResponse"]:
        """
        Called after query execution.

        Args:
            response: The agent response
            context: Execution context

        Returns:
            Modified response or None to keep original
        """
        pass

    def on_error(self, error: Exception, context: "ExecutionContext") -> Optional[bool]:
        """
        Called when an error occurs.

        Args:
            error: The exception that occurred
            context: Execution context

        Returns:
            True to suppress the error, False/None to propagate
        """
        pass

    def on_before_tool_select(self, query: str, available_tools: list) -> Optional[list]:
        """
        Called before tool selection.

        Args:
            query: The user query
            available_tools: List of available tools

        Returns:
            Modified tool list or None to keep original
        """
        pass

    def on_after_tool_select(self, query: str, selected_tools: list) -> Optional[list]:
        """
        Called after tool selection.

        Args:
            query: The user query
            selected_tools: List of selected tools

        Returns:
            Modified tool list or None to keep original
        """
        pass

    def on_before_tool_execute(self, tool_name: str, args: dict[str, Any]) -> Optional[dict[str, Any]]:
        """
        Called before each tool execution.

        Args:
            tool_name: Name of the tool
            args: Tool arguments

        Returns:
            Modified args or None to keep original
        """
        pass

    def on_after_tool_execute(self, tool_name: str, args: dict[str, Any], result: str) -> Optional[str]:
        """
        Called after each tool execution.

        Args:
            tool_name: Name of the tool
            args: Tool arguments
            result: Tool execution result

        Returns:
            Modified result or None to keep original
        """
        pass

    def on_tool_error(self, tool_name: str, error: Exception) -> Optional[str]:
        """
        Called when tool execution fails.

        Args:
            tool_name: Name of the tool
            error: The exception that occurred

        Returns:
            Fallback result or None to use default error handling
        """
        pass

    def on_before_llm_call(self, prompt: str, messages: Optional[list] = None) -> Optional[str]:
        """
        Called before LLM API call.

        Args:
            prompt: The prompt to send
            messages: Chat messages (if chat call)

        Returns:
            Modified prompt or None to keep original
        """
        pass

    def on_after_llm_call(self, prompt: str, response: str) -> Optional[str]:
        """
        Called after LLM API call.

        Args:
            prompt: The prompt that was sent
            response: The LLM response

        Returns:
            Modified response or None to keep original
        """
        pass

    def on_before_memory_update(self, query: str, response: str) -> Optional[tuple]:
        """
        Called before memory is updated.

        Args:
            query: The user query
            response: The response to store

        Returns:
            Tuple of (modified_query, modified_response) or None
        """
        pass

    def on_after_memory_update(self, query: str, response: str) -> None:
        """Called after memory is updated"""
        pass

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', enabled={self.enabled})"


class PluginManager:
    """
    Manages agent plugins.

    Handles plugin registration, lifecycle, and hook execution.
    """

    def __init__(self, agent_name: str = "Agent"):
        self.agent_name = agent_name
        self._plugins: dict[str, AgentPlugin] = {}
        self._hooks: dict[PluginHook, list[AgentPlugin]] = {hook: [] for hook in PluginHook}

    def add(self, plugin: AgentPlugin) -> "PluginManager":
        """
        Add a plugin.

        Args:
            plugin: Plugin instance

        Returns:
            Self for chaining
        """
        if plugin.name in self._plugins:
            logger.warning(f"Replacing existing plugin: {plugin.name}")
            self.remove(plugin.name)

        self._plugins[plugin.name] = plugin

        # Register hooks
        self._register_plugin_hooks(plugin)

        logger.debug(f"Added plugin: {plugin.name}")
        return self

    def remove(self, name: str) -> bool:
        """
        Remove a plugin by name.

        Args:
            name: Plugin name

        Returns:
            True if removed, False if not found
        """
        if name not in self._plugins:
            return False

        plugin = self._plugins.pop(name)
        plugin.detach()

        # Unregister hooks
        for hook_list in self._hooks.values():
            if plugin in hook_list:
                hook_list.remove(plugin)

        logger.debug(f"Removed plugin: {name}")
        return True

    def get(self, name: str) -> Optional[AgentPlugin]:
        """Get plugin by name"""
        return self._plugins.get(name)

    def list(self) -> list[str]:
        """List all plugin names"""
        return list(self._plugins.keys())

    def enable(self, name: str) -> bool:
        """Enable a plugin"""
        plugin = self._plugins.get(name)
        if plugin:
            plugin.enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        """Disable a plugin"""
        plugin = self._plugins.get(name)
        if plugin:
            plugin.enabled = False
            return True
        return False

    def execute_hook(self, hook: PluginHook, *args, **kwargs) -> Any:
        """
        Execute all plugins for a given hook.

        Args:
            hook: The hook to execute
            *args: Arguments to pass to plugins
            **kwargs: Keyword arguments to pass to plugins

        Returns:
            Modified result from the last plugin that returned a value
        """
        result = None
        plugins = sorted(
            [p for p in self._hooks[hook] if p.enabled],
            key=lambda p: p.priority
        )

        for plugin in plugins:
            try:
                method = self._get_hook_method(plugin, hook)
                if method:
                    plugin_result = method(*args, **kwargs)
                    if plugin_result is not None:
                        result = plugin_result
                        # Update args for next plugin if applicable
                        if len(args) > 0 and isinstance(plugin_result, type(args[0])):
                            args = (plugin_result, *args[1:])
            except Exception as e:
                logger.error(f"Plugin {plugin.name} error in {hook.name}: {e}")

        return result

    def _register_plugin_hooks(self, plugin: AgentPlugin) -> None:
        """Register a plugin's hooks"""
        hook_mapping = {
            PluginHook.BEFORE_EXECUTE: "on_before_execute",
            PluginHook.AFTER_EXECUTE: "on_after_execute",
            PluginHook.ON_ERROR: "on_error",
            PluginHook.BEFORE_TOOL_SELECT: "on_before_tool_select",
            PluginHook.AFTER_TOOL_SELECT: "on_after_tool_select",
            PluginHook.BEFORE_TOOL_EXECUTE: "on_before_tool_execute",
            PluginHook.AFTER_TOOL_EXECUTE: "on_after_tool_execute",
            PluginHook.ON_TOOL_ERROR: "on_tool_error",
            PluginHook.BEFORE_LLM_CALL: "on_before_llm_call",
            PluginHook.AFTER_LLM_CALL: "on_after_llm_call",
            PluginHook.BEFORE_MEMORY_UPDATE: "on_before_memory_update",
            PluginHook.AFTER_MEMORY_UPDATE: "on_after_memory_update",
        }

        for hook, method_name in hook_mapping.items():
            if hasattr(plugin, method_name):
                method = getattr(plugin, method_name)
                # Check if method is overridden (not base class)
                if method.__func__ is not getattr(AgentPlugin, method_name, None):
                    self._hooks[hook].append(plugin)

    def _get_hook_method(self, plugin: AgentPlugin, hook: PluginHook) -> Optional[Callable]:
        """Get the method for a hook"""
        hook_methods = {
            PluginHook.BEFORE_EXECUTE: plugin.on_before_execute,
            PluginHook.AFTER_EXECUTE: plugin.on_after_execute,
            PluginHook.ON_ERROR: plugin.on_error,
            PluginHook.BEFORE_TOOL_SELECT: plugin.on_before_tool_select,
            PluginHook.AFTER_TOOL_SELECT: plugin.on_after_tool_select,
            PluginHook.BEFORE_TOOL_EXECUTE: plugin.on_before_tool_execute,
            PluginHook.AFTER_TOOL_EXECUTE: plugin.on_after_tool_execute,
            PluginHook.ON_TOOL_ERROR: plugin.on_tool_error,
            PluginHook.BEFORE_LLM_CALL: plugin.on_before_llm_call,
            PluginHook.AFTER_LLM_CALL: plugin.on_after_llm_call,
            PluginHook.BEFORE_MEMORY_UPDATE: plugin.on_before_memory_update,
            PluginHook.AFTER_MEMORY_UPDATE: plugin.on_after_memory_update,
        }
        return hook_methods.get(hook)

    def __len__(self) -> int:
        return len(self._plugins)

    def __contains__(self, name: str) -> bool:
        return name in self._plugins

    def __iter__(self):
        return iter(self._plugins.values())


# ============================================================================
# BUILT-IN PLUGINS
# ============================================================================

class LoggingPlugin(AgentPlugin):
    """Plugin that logs all agent activity"""

    name = "logging"
    description = "Logs all agent activity for debugging"

    def __init__(self, log_level: int = logging.DEBUG):
        super().__init__()
        self.log_level = log_level
        self.logger = logging.getLogger(f"aiccel.plugin.{self.name}")

    def on_before_execute(self, query, context):
        self.logger.log(self.log_level, f"[{context.trace_id}] Executing: {query[:100]}")

    def on_after_execute(self, response, context):
        self.logger.log(
            self.log_level,
            f"[{context.trace_id}] Completed in {response.execution_time:.2f}s, "
            f"tools: {response.tool_names}"
        )

    def on_error(self, error, context):
        self.logger.error(f"[{context.trace_id}] Error: {error}")

    def on_before_tool_execute(self, tool_name, args):
        self.logger.log(self.log_level, f"Tool {tool_name}: {args}")

    def on_after_tool_execute(self, tool_name, args, result):
        self.logger.log(self.log_level, f"Tool {tool_name} result: {result[:100]}...")


class MetricsPlugin(AgentPlugin):
    """Plugin that collects execution metrics"""

    name = "metrics"
    description = "Collects execution metrics"

    def __init__(self):
        super().__init__()
        self.execution_count = 0
        self.total_execution_time = 0.0
        self.tool_usage: dict[str, int] = {}
        self.error_count = 0

    def on_after_execute(self, response, context):
        self.execution_count += 1
        self.total_execution_time += response.execution_time

        for tool_name, _ in response.tools_used:
            self.tool_usage[tool_name] = self.tool_usage.get(tool_name, 0) + 1

    def on_error(self, error, context):
        self.error_count += 1

    def get_stats(self) -> dict[str, Any]:
        """Get collected metrics"""
        return {
            "execution_count": self.execution_count,
            "total_execution_time": self.total_execution_time,
            "average_execution_time": (
                self.total_execution_time / self.execution_count
                if self.execution_count > 0 else 0
            ),
            "tool_usage": self.tool_usage,
            "error_count": self.error_count,
        }

    def reset(self) -> None:
        """Reset all metrics"""
        self.execution_count = 0
        self.total_execution_time = 0.0
        self.tool_usage.clear()
        self.error_count = 0


class CachingPlugin(AgentPlugin):
    """Plugin that caches query responses"""

    name = "caching"
    description = "Caches query responses for faster repeated queries"
    priority = 10  # Run early

    def __init__(self, max_size: int = 100, ttl: int = 300):
        super().__init__()
        self.max_size = max_size
        self.ttl = ttl
        self._cache: dict[str, tuple] = {}  # query -> (response, timestamp)
        self._hits = 0
        self._misses = 0

    def on_before_execute(self, query, context):
        import time
        cache_key = self._get_cache_key(query)

        if cache_key in self._cache:
            _response, timestamp = self._cache[cache_key]
            if time.time() - timestamp < self.ttl:
                self._hits += 1
                context.add_metadata("cache_hit", True)
                # Return cached response - this will short-circuit execution
                return None  # TODO: Need mechanism to return cached response

        self._misses += 1
        context.add_metadata("cache_hit", False)

    def on_after_execute(self, response, context):
        import time
        if not context.metadata.get("cache_hit", False):
            cache_key = self._get_cache_key(context.query)

            # Evict old entries if needed
            if len(self._cache) >= self.max_size:
                oldest = min(self._cache.items(), key=lambda x: x[1][1])
                del self._cache[oldest[0]]

            self._cache[cache_key] = (response, time.time())

    def _get_cache_key(self, query: str) -> str:
        """Generate cache key from query"""
        import hashlib
        return hashlib.md5(query.encode()).hexdigest()

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics"""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0,
            "size": len(self._cache),
            "max_size": self.max_size,
        }

    def clear(self) -> None:
        """Clear the cache"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
