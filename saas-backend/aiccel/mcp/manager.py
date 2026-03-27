# aiccel/mcp/manager.py
"""
MCP Connection Manager
======================

Production-ready connection management for MCP:
- Multiple server connections
- Connection pooling
- Automatic reconnection
- Health monitoring
- Tool aggregation from multiple servers

Usage:
    from aiccel.mcp import MCPManager

    manager = MCPManager()

    # Add servers
    manager.add_server("search", command=["npx", "@mcp/search-server"])
    manager.add_server("database", url="http://localhost:3001/mcp")

    # Connect all
    await manager.connect_all()

    # Get aggregated tools
    tools = manager.get_all_tools()

    # Use with agent
    agent = Agent(provider=provider, tools=tools)
"""

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from .adapter import MCPTool, MCPToolAdapter
from .client import MCPClient
from .protocol import ResourceDefinition
from .transports import TransportConfig, create_transport


logger = logging.getLogger(__name__)


class ServerStatus(Enum):
    """MCP server connection status."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class ServerConfig:
    """Configuration for an MCP server."""
    name: str
    url: Optional[str] = None
    command: Optional[list[str]] = None
    cwd: Optional[str] = None
    env: Optional[dict[str, str]] = None
    headers: Optional[dict[str, str]] = None
    transport_config: Optional[TransportConfig] = None
    enabled: bool = True
    priority: int = 0  # Higher = preferred for duplicate tools
    tool_prefix: Optional[str] = None  # Prefix for tool names
    tool_filter: Optional[Callable[[str], bool]] = None  # Filter tools by name


@dataclass
class ServerState:
    """Runtime state for an MCP server."""
    config: ServerConfig
    client: Optional[MCPClient] = None
    adapter: Optional[MCPToolAdapter] = None
    status: ServerStatus = ServerStatus.DISCONNECTED
    last_error: Optional[str] = None
    connected_at: Optional[float] = None
    tools: list[MCPTool] = field(default_factory=list)
    resources: list[ResourceDefinition] = field(default_factory=list)


class MCPManager:
    """
    Manages multiple MCP server connections.

    Features:
    - Multiple server support
    - Connection pooling
    - Automatic reconnection
    - Tool aggregation with conflict resolution
    - Health monitoring
    - Metrics collection
    """

    def __init__(
        self,
        auto_reconnect: bool = True,
        reconnect_interval: float = 30.0,
        health_check_interval: float = 60.0
    ):
        """
        Initialize MCP manager.

        Args:
            auto_reconnect: Automatically reconnect failed servers
            reconnect_interval: Seconds between reconnection attempts
            health_check_interval: Seconds between health checks
        """
        self.auto_reconnect = auto_reconnect
        self.reconnect_interval = reconnect_interval
        self.health_check_interval = health_check_interval

        self._servers: dict[str, ServerState] = {}
        self._tool_map: dict[str, MCPTool] = {}  # tool_name -> tool
        self._tool_sources: dict[str, str] = {}  # tool_name -> server_name
        self._reconnect_task: Optional[asyncio.Task] = None
        self._health_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        self._callbacks: dict[str, list[Callable]] = {
            "connected": [],
            "disconnected": [],
            "tools_changed": [],
            "error": [],
        }

    def add_server(
        self,
        name: str,
        url: Optional[str] = None,
        command: Optional[list[str]] = None,
        **kwargs
    ) -> "MCPManager":
        """
        Add an MCP server configuration.

        Args:
            name: Unique server name
            url: HTTP/WebSocket URL
            command: Subprocess command
            **kwargs: Additional ServerConfig options

        Returns:
            Self for chaining
        """
        if name in self._servers:
            raise ValueError(f"Server '{name}' already exists")

        config = ServerConfig(
            name=name,
            url=url,
            command=command,
            cwd=kwargs.get("cwd"),
            env=kwargs.get("env"),
            headers=kwargs.get("headers"),
            transport_config=kwargs.get("transport_config"),
            enabled=kwargs.get("enabled", True),
            priority=kwargs.get("priority", 0),
            tool_prefix=kwargs.get("tool_prefix"),
            tool_filter=kwargs.get("tool_filter"),
        )

        self._servers[name] = ServerState(config=config)
        logger.info(f"Added MCP server: {name}")
        return self

    def remove_server(self, name: str) -> "MCPManager":
        """Remove a server configuration."""
        if name not in self._servers:
            raise ValueError(f"Server '{name}' not found")

        state = self._servers.pop(name)
        if state.client:
            asyncio.create_task(state.client.close())

        self._rebuild_tool_map()
        logger.info(f"Removed MCP server: {name}")
        return self

    async def connect(self, name: str) -> bool:
        """
        Connect to a specific server.

        Args:
            name: Server name

        Returns:
            True if connected successfully
        """
        if name not in self._servers:
            raise ValueError(f"Server '{name}' not found")

        state = self._servers[name]
        if not state.config.enabled:
            logger.info(f"Server '{name}' is disabled")
            return False

        async with self._lock:
            try:
                state.status = ServerStatus.CONNECTING

                # Create transport and client
                transport = create_transport(
                    url=state.config.url,
                    command=state.config.command,
                    cwd=state.config.cwd,
                    env=state.config.env,
                    headers=state.config.headers,
                    **(state.config.transport_config.__dict__ if state.config.transport_config else {})
                )

                client = MCPClient(transport)
                await client.connect()

                # Create adapter and get tools
                adapter = MCPToolAdapter(client)
                await adapter.refresh_tools()

                # Apply tool prefix and filter
                tools = adapter.get_tools()
                if state.config.tool_filter:
                    tools = [t for t in tools if state.config.tool_filter(t.name)]
                if state.config.tool_prefix:
                    for tool in tools:
                        tool.name = f"{state.config.tool_prefix}_{tool.name}"

                # Update state
                state.client = client
                state.adapter = adapter
                state.tools = tools
                state.status = ServerStatus.CONNECTED
                state.connected_at = time.time()
                state.last_error = None

                logger.info(f"Connected to MCP server '{name}' with {len(tools)} tools")

                # Rebuild aggregated tool map
                self._rebuild_tool_map()

                # Notify callbacks
                await self._notify("connected", name)

                return True

            except Exception as e:
                state.status = ServerStatus.ERROR
                state.last_error = str(e)
                logger.error(f"Failed to connect to '{name}': {e}")
                await self._notify("error", name, str(e))
                return False

    async def connect_all(self) -> dict[str, bool]:
        """
        Connect to all enabled servers.

        Returns:
            Dict of server_name -> success
        """
        results = {}
        tasks = []

        for name, state in self._servers.items():
            if state.config.enabled:
                tasks.append((name, self.connect(name)))

        for name, task in tasks:
            results[name] = await task

        # Start background tasks
        if self.auto_reconnect:
            self._start_reconnect_loop()
        self._start_health_check_loop()

        return results

    async def disconnect(self, name: str) -> None:
        """Disconnect from a specific server."""
        if name not in self._servers:
            return

        state = self._servers[name]
        if state.client:
            try:
                await state.client.close()
            except Exception as e:
                logger.warning(f"Error closing '{name}': {e}")

        state.client = None
        state.adapter = None
        state.tools = []
        state.status = ServerStatus.DISCONNECTED
        state.connected_at = None

        self._rebuild_tool_map()
        await self._notify("disconnected", name)

    async def disconnect_all(self) -> None:
        """Disconnect from all servers."""
        # Stop background tasks
        for task in [self._reconnect_task, self._health_task]:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        # Disconnect all
        for name in list(self._servers.keys()):
            await self.disconnect(name)

    def get_all_tools(self) -> list[MCPTool]:
        """Get all tools from connected servers."""
        return list(self._tool_map.values())

    def get_tool(self, name: str) -> Optional[MCPTool]:
        """Get a specific tool by name."""
        return self._tool_map.get(name)

    def get_server_tools(self, server_name: str) -> list[MCPTool]:
        """Get tools from a specific server."""
        state = self._servers.get(server_name)
        return state.tools if state else []

    def get_status(self) -> dict[str, dict[str, Any]]:
        """Get status of all servers."""
        return {
            name: {
                "status": state.status.value,
                "enabled": state.config.enabled,
                "tools_count": len(state.tools),
                "connected_at": state.connected_at,
                "last_error": state.last_error,
            }
            for name, state in self._servers.items()
        }

    def get_server(self, name: str) -> Optional[MCPClient]:
        """Get client for a specific server."""
        state = self._servers.get(name)
        return state.client if state else None

    def on(self, event: str, callback: Callable) -> "MCPManager":
        """
        Register event callback.

        Events:
        - connected: (server_name)
        - disconnected: (server_name)
        - tools_changed: ()
        - error: (server_name, error_message)
        """
        if event in self._callbacks:
            self._callbacks[event].append(callback)
        return self

    def _rebuild_tool_map(self) -> None:
        """Rebuild aggregated tool map with conflict resolution."""
        self._tool_map.clear()
        self._tool_sources.clear()

        # Sort servers by priority (higher first)
        sorted_servers = sorted(
            self._servers.items(),
            key=lambda x: x[1].config.priority,
            reverse=True
        )

        for name, state in sorted_servers:
            if state.status != ServerStatus.CONNECTED:
                continue

            for tool in state.tools:
                if tool.name not in self._tool_map:
                    self._tool_map[tool.name] = tool
                    self._tool_sources[tool.name] = name
                else:
                    logger.debug(
                        f"Tool '{tool.name}' from '{name}' shadowed by "
                        f"'{self._tool_sources[tool.name]}'"
                    )

        logger.info(f"Tool map rebuilt: {len(self._tool_map)} tools from {len(self._servers)} servers")

    def _start_reconnect_loop(self) -> None:
        """Start background reconnection loop."""
        if self._reconnect_task:
            return

        async def reconnect_loop():
            while True:
                await asyncio.sleep(self.reconnect_interval)
                for name, state in self._servers.items():
                    if state.config.enabled and state.status in (
                        ServerStatus.ERROR,
                        ServerStatus.DISCONNECTED
                    ):
                        logger.info(f"Attempting reconnect to '{name}'")
                        await self.connect(name)

        self._reconnect_task = asyncio.create_task(reconnect_loop())

    def _start_health_check_loop(self) -> None:
        """Start background health check loop."""
        if self._health_task:
            return

        async def health_loop():
            while True:
                await asyncio.sleep(self.health_check_interval)
                for name, state in self._servers.items():
                    if state.status == ServerStatus.CONNECTED and state.client:
                        try:
                            # Try listing tools as health check
                            await asyncio.wait_for(
                                state.client.list_tools(),
                                timeout=10.0
                            )
                        except Exception as e:
                            logger.warning(f"Health check failed for '{name}': {e}")
                            state.status = ServerStatus.ERROR
                            state.last_error = str(e)

        self._health_task = asyncio.create_task(health_loop())

    async def _notify(self, event: str, *args) -> None:
        """Notify event callbacks."""
        for callback in self._callbacks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(*args)
                else:
                    callback(*args)
            except Exception as e:
                logger.error(f"Callback error for '{event}': {e}")

        # Always notify tools_changed after connect/disconnect
        if event in ("connected", "disconnected"):
            for callback in self._callbacks.get("tools_changed", []):
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback()
                    else:
                        callback()
                except Exception as e:
                    logger.error(f"tools_changed callback error: {e}")

    async def __aenter__(self) -> "MCPManager":
        """Async context manager entry."""
        await self.connect_all()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.disconnect_all()


__all__ = [
    "MCPManager",
    "ServerConfig",
    "ServerState",
    "ServerStatus",
]
