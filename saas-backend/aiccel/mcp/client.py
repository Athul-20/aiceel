# aiccel/mcp/client.py
"""
MCP Client Implementation
=========================

Provides a client for connecting to MCP-compliant tool servers.
Supports multiple transports: stdio, HTTP/SSE, WebSocket.

Usage:
    from aiccel.mcp import MCPClient

    # HTTP transport
    client = MCPClient.from_url("http://localhost:3000/mcp")
    await client.connect()

    # List available tools
    tools = await client.list_tools()

    # Call a tool
    result = await client.call_tool("search", {"query": "AI news"})

    # Cleanup
    await client.close()
"""

import asyncio
import contextlib
import json
import logging
from typing import Any, Callable, Optional, Union

from .protocol import (
    ClientCapabilities,
    InitializeParams,
    InitializeResult,
    MCPErrorCode,
    MCPMethod,
    MCPNotification,
    MCPRequest,
    MCPResponse,
    MCPVersion,
    ResourceContent,
    ResourceDefinition,
    ServerCapabilities,
    ToolCallResult,
    ToolDefinition,
)
from .transports import (
    HTTPSSETransport,
    MCPTransport,
    StdioTransport,
)


logger = logging.getLogger(__name__)



class MCPClient:
    """
    MCP Client for connecting to tool servers.

    Supports:
    - Stdio transport (subprocess)
    - HTTP transport (REST/SSE)
    - WebSocket transport (bidirectional)

    Example:
        # Connect to stdio server
        client = MCPClient.from_command(["npx", "@modelcontextprotocol/server-search"])
        await client.connect()

        # Connect to HTTP server
        client = MCPClient.from_url("http://localhost:3000/mcp")
        await client.connect()

        # Use tools
        tools = await client.list_tools()
        result = await client.call_tool("search", {"query": "hello"})
    """

    def __init__(self, transport: MCPTransport):
        self.transport = transport
        self._initialized = False
        self._request_id = 0
        self._pending_requests: dict[Union[str, int], asyncio.Future] = {}
        self._server_info: Optional[InitializeResult] = None
        self._tools: dict[str, ToolDefinition] = {}
        self._resources: dict[str, ResourceDefinition] = {}
        self._notification_handlers: dict[str, list[Callable]] = {}
        self._receive_task: Optional[asyncio.Task] = None

    @classmethod
    def from_command(
        cls,
        command: list[str],
        cwd: Optional[str] = None,
        env: Optional[dict[str, str]] = None
    ) -> "MCPClient":
        """Create client from subprocess command"""
        return cls(StdioTransport(command, cwd, env))

    @classmethod
    def from_url(
        cls,
        url: str,
        headers: Optional[dict[str, str]] = None
    ) -> "MCPClient":
        """Create client from HTTP URL"""
        return cls(HTTPSSETransport(url, headers))

    async def connect(self) -> InitializeResult:
        """Connect and initialize the MCP session"""
        await self.transport.connect()

        # Start message receiver for all transports
        self._receive_task = asyncio.create_task(self._receive_loop())

        # Initialize session
        result = await self._initialize()
        self._initialized = True

        # Cache tools and resources
        if result.capabilities.tools:
            await self._refresh_tools()
        if result.capabilities.resources:
            await self._refresh_resources()

        return result

    async def close(self) -> None:
        """Close the connection"""
        if self._receive_task:
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task

        await self.transport.close()
        self._initialized = False

    async def list_tools(self) -> list[ToolDefinition]:
        """List available tools"""
        if not self._initialized:
            raise RuntimeError("Client not initialized. Call connect() first.")

        result = await self._send_request(MCPMethod.TOOLS_LIST)
        tools = [ToolDefinition.from_dict(t) for t in result.get("tools", [])]
        self._tools = {t.name: t for t in tools}
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any], timeout: float = 300.0) -> ToolCallResult:
        """
        Call a tool by name.

        Args:
            name: Tool name
            arguments: Tool arguments
            timeout: Timeout in seconds (default: 300.0)
        """
        if not self._initialized:
            raise RuntimeError("Client not initialized. Call connect() first.")

        result = await self._send_request(
            MCPMethod.TOOLS_CALL,
            {"name": name, "arguments": arguments},
            timeout=timeout
        )
        return ToolCallResult.from_dict(result)

    async def list_resources(self) -> list[ResourceDefinition]:
        """List available resources"""
        if not self._initialized:
            raise RuntimeError("Client not initialized. Call connect() first.")

        result = await self._send_request(MCPMethod.RESOURCES_LIST)
        resources = [ResourceDefinition.from_dict(r) for r in result.get("resources", [])]
        self._resources = {r.uri: r for r in resources}
        return resources

    async def read_resource(self, uri: str) -> ResourceContent:
        """Read a resource by URI"""
        if not self._initialized:
            raise RuntimeError("Client not initialized. Call connect() first.")

        result = await self._send_request(
            MCPMethod.RESOURCES_READ,
            {"uri": uri}
        )
        contents = result.get("contents", [])
        if not contents:
            raise ValueError(f"No content returned for resource: {uri}")

        content = contents[0]
        return ResourceContent(
            uri=content.get("uri", uri),
            text=content.get("text"),
            blob=content.get("blob"),
            mimeType=content.get("mimeType")
        )

    def get_tool(self, name: str) -> Optional[ToolDefinition]:
        """Get cached tool by name"""
        return self._tools.get(name)

    def get_resource(self, uri: str) -> Optional[ResourceDefinition]:
        """Get cached resource by URI"""
        return self._resources.get(uri)

    def on_notification(self, method: str, handler: Callable[[dict[str, Any]], None]) -> None:
        """Register notification handler"""
        if method not in self._notification_handlers:
            self._notification_handlers[method] = []
        self._notification_handlers[method].append(handler)

    @property
    def server_info(self) -> Optional[dict[str, str]]:
        """Get server info from initialization"""
        return self._server_info.serverInfo if self._server_info else None

    @property
    def capabilities(self) -> Optional[ServerCapabilities]:
        """Get server capabilities"""
        return self._server_info.capabilities if self._server_info else None

    async def _initialize(self) -> InitializeResult:
        """Send initialize request"""
        params = InitializeParams(
            protocolVersion=MCPVersion.CURRENT,
            capabilities=ClientCapabilities(),
            clientInfo={"name": "aiccel", "version": "2.0.0"}
        )

        result = await self._send_request(MCPMethod.INITIALIZE, params.to_dict())
        self._server_info = InitializeResult.from_dict(result)

        # Send initialized notification
        await self._send_notification(MCPMethod.INITIALIZED)

        logger.info(f"Initialized MCP session with {self._server_info.serverInfo.get('name', 'unknown')}")
        return self._server_info

    async def _refresh_tools(self) -> None:
        """Refresh tool cache"""
        await self.list_tools()

    async def _refresh_resources(self) -> None:
        """Refresh resource cache"""
        await self.list_resources()

    async def _send_request(
        self,
        method: Union[str, MCPMethod],
        params: Optional[dict[str, Any]] = None,
        timeout: float = 60.0
    ) -> Any:
        """Send request and wait for response"""
        self._request_id += 1
        request_id = self._request_id

        request = MCPRequest(
            id=request_id,
            method=method.value if isinstance(method, MCPMethod) else method,
            params=params
        )

        # Create future for response
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending_requests[request_id] = future

        try:
            await self.transport.send(request.to_json())

            # Wait for response via receive loop
            # Default to 60s for generic requests, but allow overrides
            result = await asyncio.wait_for(future, timeout=timeout)
            return result

        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise MCPClientError(MCPErrorCode.TIMEOUT, "Request timed out")
        finally:
            self._pending_requests.pop(request_id, None)

    async def _send_notification(
        self,
        method: Union[str, MCPMethod],
        params: Optional[dict[str, Any]] = None
    ) -> None:
        """Send notification (no response expected)"""
        notification = MCPNotification(
            method=method.value if isinstance(method, MCPMethod) else method,
            params=params
        )
        await self.transport.send(notification.to_json())

    async def _receive_loop(self) -> None:
        """Background loop to receive messages"""
        try:
            while True:
                message_str = await self.transport.receive()
                message = json.loads(message_str)

                if "id" in message:
                    # Response
                    response = MCPResponse.from_dict(message)
                    future = self._pending_requests.get(response.id)
                    if future and not future.done():
                        if response.error:
                            future.set_exception(MCPClientError(
                                response.error.code,
                                response.error.message,
                                response.error.data
                            ))
                        else:
                            future.set_result(response.result)
                else:
                    # Notification
                    notification = MCPNotification.from_dict(message)
                    await self._handle_notification(notification)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in receive loop: {e}")

    async def _handle_notification(self, notification: MCPNotification) -> None:
        """Handle incoming notification"""
        handlers = self._notification_handlers.get(notification.method, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(notification.params or {})
                else:
                    handler(notification.params or {})
            except Exception as e:
                logger.error(f"Error in notification handler: {e}")

        # Handle tool/resource change notifications
        if notification.method == MCPMethod.TOOLS_CHANGED.value:
            await self._refresh_tools()
        elif notification.method == MCPMethod.RESOURCES_UPDATED.value:
            await self._refresh_resources()


class MCPClientError(Exception):
    """Exception raised by MCP client"""

    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"
