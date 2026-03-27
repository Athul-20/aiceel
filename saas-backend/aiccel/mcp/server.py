# aiccel/mcp/server.py
"""
MCP Server Implementation
=========================

Exposes aiccel tools as an MCP-compliant server.
Allows external applications to use aiccel tools via MCP protocol.

Features:
- Tool registration and execution
- Resource serving
- Prompt templates
- Middleware support
- Multiple transports (stdio, HTTP)
- Robust error handling and concurrency

Usage:
    from aiccel.mcp import MCPServerBuilder

    server = (
        MCPServerBuilder("my-server")
        .add_tool(tool)
        .build()
    )

    await server.run_stdio()
"""

import asyncio
import json
import logging
import sys
import time
from typing import Any, Callable, Optional

from pydantic import Field

from .protocol import (
    MCPBaseModel,
    MCPErrorCode,
    MCPMethod,
    MCPNotification,
    MCPRequest,
    MCPResponse,
    MCPVersion,
    ResourceDefinition,
    ServerCapabilities,
    ToolCallResult,
    ToolDefinition,
)


logger = logging.getLogger(__name__)


class PromptDefinition(MCPBaseModel):
    """MCP Prompt template definition."""
    name: str
    description: str
    arguments: list[dict[str, Any]] = Field(default_factory=list)
    template: str = ""


class MCPMiddleware:
    """Base class for MCP middleware."""

    async def on_request(self, request: MCPRequest) -> Optional[MCPRequest]:
        """Called before handling request. Return None to skip default handling."""
        return request

    async def on_response(self, request: MCPRequest, response: MCPResponse) -> MCPResponse:
        """Called after handling request."""
        return response

    async def on_tool_call(self, name: str, args: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Called before tool execution. Return modified args or None to skip."""
        return args

    async def on_tool_result(self, name: str, result: Any) -> Any:
        """Called after tool execution."""
        return result


class LoggingMiddleware(MCPMiddleware):
    """Middleware that logs all requests and responses."""

    async def on_request(self, request: MCPRequest) -> MCPRequest:
        logger.info(f"MCP Request: {request.method}")
        return request

    async def on_response(self, request: MCPRequest, response: MCPResponse) -> MCPResponse:
        if response.error:
            logger.error(f"MCP Error: {response.error.message}")
        else:
            logger.info(f"MCP Response: {request.method} OK")
        return response


class MetricsMiddleware(MCPMiddleware):
    """Middleware that collects metrics."""

    def __init__(self):
        self.metrics = {
            "requests": 0,
            "errors": 0,
            "tool_calls": 0,
            "total_duration_ms": 0.0,
        }
        self._request_start: dict[Any, float] = {}

    async def on_request(self, request: MCPRequest) -> MCPRequest:
        self.metrics["requests"] += 1
        self._request_start[request.id] = time.perf_counter()
        return request

    async def on_response(self, request: MCPRequest, response: MCPResponse) -> MCPResponse:
        start = self._request_start.pop(request.id, None)
        if start:
            duration = (time.perf_counter() - start) * 1000
            self.metrics["total_duration_ms"] += duration

        if response.error:
            self.metrics["errors"] += 1
        return response

    async def on_tool_call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        self.metrics["tool_calls"] += 1
        return args


class RateLimitMiddleware(MCPMiddleware):
    """Middleware that rate limits requests."""

    def __init__(self, requests_per_minute: int = 60):
        self.rate = requests_per_minute
        self.tokens = float(requests_per_minute)
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def on_request(self, request: MCPRequest) -> Optional[MCPRequest]:
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.rate, self.tokens + elapsed * (self.rate / 60))
            self.last_update = now

            if self.tokens < 1:
                logger.warning("Rate limit exceeded")
                return None  # Skip request

            self.tokens -= 1
            return request


class MCPServer:
    """
    Production-ready MCP server.
    """

    def __init__(
        self,
        name: str,
        version: str,
        tools: dict[str, Callable],
        tool_definitions: dict[str, ToolDefinition],
        resources: dict[str, ResourceDefinition],
        resource_handlers: dict[str, Callable],
        prompts: dict[str, PromptDefinition],
        prompt_handlers: dict[str, Callable],
        middleware: list[MCPMiddleware],
        custom_handlers: dict[str, Callable],
    ):
        self.name = name
        self.version = version
        self._tools = tools
        self._tool_definitions = tool_definitions
        self._resources = resources
        self._resource_handlers = resource_handlers
        self._prompts = prompts
        self._prompt_handlers = prompt_handlers
        self._middleware = middleware
        self._custom_handlers = custom_handlers
        self._initialized = False
        self._client_info: Optional[dict[str, str]] = None

        # Built-in handlers
        self._handlers: dict[str, Callable] = {
            MCPMethod.INITIALIZE.value: self._handle_initialize,
            MCPMethod.SHUTDOWN.value: self._handle_shutdown,
            MCPMethod.TOOLS_LIST.value: self._handle_tools_list,
            MCPMethod.TOOLS_CALL.value: self._handle_tools_call,
            MCPMethod.RESOURCES_LIST.value: self._handle_resources_list,
            MCPMethod.RESOURCES_READ.value: self._handle_resources_read,
            MCPMethod.PROMPTS_LIST.value: self._handle_prompts_list,
            MCPMethod.PROMPTS_GET.value: self._handle_prompts_get,
            **custom_handlers,
        }

        self._running = True

    @property
    def capabilities(self) -> ServerCapabilities:
        """Get server capabilities."""
        caps = ServerCapabilities()

        if self._tools:
            caps.tools = {"listChanged": True}
        if self._resources:
            caps.resources = {"subscribe": False, "listChanged": True}
        if self._prompts:
            caps.prompts = {"listChanged": True}

        return caps

    async def handle_message(self, message: str) -> Optional[str]:
        """Handle incoming MCP message."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError as e:
            response = MCPResponse.failure(
                None,
                MCPErrorCode.PARSE_ERROR,
                f"Invalid JSON: {e}"
            )
            return response.to_json()

        # Notification (no id)
        if "id" not in data:
            await self._handle_notification(MCPNotification.from_dict(data))
            return None

        # Request
        try:
            request = MCPRequest.from_dict(data)
        except Exception as e:
             response = MCPResponse.failure(
                data.get("id"),
                MCPErrorCode.INVALID_REQUEST,
                f"Invalid request format: {e}"
            )
             return response.to_json()

        # Apply request middleware
        for mw in self._middleware:
            request = await mw.on_request(request)
            if request is None:
                return MCPResponse.failure(
                    data.get("id"),
                    MCPErrorCode.INTERNAL_ERROR,
                    "Request rejected by middleware"
                ).to_json()

        # Handle request
        response = await self._handle_request(request)

        # Apply response middleware
        for mw in reversed(self._middleware):
            response = await mw.on_response(request, response)

        return response.to_json()

    async def _handle_request(self, request: MCPRequest) -> MCPResponse:
        """Handle a request."""
        handler = self._handlers.get(request.method)

        if not handler:
            return MCPResponse.failure(
                request.id,
                MCPErrorCode.METHOD_NOT_FOUND,
                f"Method not found: {request.method}"
            )

        try:
            result = await handler(request.params or {})
            return MCPResponse.success(request.id, result)
        except Exception as e:
            logger.error(f"Error handling {request.method}: {e}")
            return MCPResponse.failure(
                request.id,
                MCPErrorCode.INTERNAL_ERROR,
                str(e)
            )

    async def _handle_notification(self, notification: MCPNotification) -> None:
        """Handle notification."""
        if notification.method == MCPMethod.INITIALIZED.value:
            self._initialized = True
            logger.info("Client initialized")

    async def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle initialize request."""
        self._client_info = params.get("clientInfo", {})
        logger.info(f"Initialize from {self._client_info.get('name', 'unknown')}")

        return {
            "protocolVersion": MCPVersion.CURRENT,
            "capabilities": self.capabilities.to_dict(),
            "serverInfo": {"name": self.name, "version": self.version}
        }

    async def _handle_shutdown(self, params: dict[str, Any]) -> None:
        """Handle shutdown request."""
        logger.info("Shutdown requested")
        self._running = False

    async def _handle_tools_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tools/list request."""
        return {
            "tools": [d.to_dict() for d in self._tool_definitions.values()]
        }

    async def _handle_tools_call(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle tools/call request."""
        name = params.get("name")
        arguments = params.get("arguments", {})

        if not name or name not in self._tools:
            raise ValueError(f"Tool not found: {name}")

        # Apply tool middleware
        for mw in self._middleware:
            arguments = await mw.on_tool_call(name, arguments)
            if arguments is None:
                return ToolCallResult.error("Tool call rejected").to_dict()

        logger.info(f"Calling tool: {name}")

        try:
            tool = self._tools[name]

            # Execute tool
            if hasattr(tool, 'execute_async'):
                result = await tool.execute_async(arguments)
            elif hasattr(tool, 'execute'):
                result = tool.execute(arguments)
            elif asyncio.iscoroutinefunction(tool):
                result = await tool(**arguments)
            else:
                result = tool(**arguments)

            # Apply result middleware
            for mw in reversed(self._middleware):
                result = await mw.on_tool_result(name, result)

            # Format result
            # Check for aiccel v2 ToolResult (duck typing)
            if hasattr(result, "success") and hasattr(result, "data") and hasattr(result, "error"):
                # It's likely a ToolResult
                if result.success:
                    # Check if data is already a list of content items (advanced usage)
                    if isinstance(result.data, list) and all(isinstance(x, dict) and "type" in x for x in result.data):
                        return ToolCallResult(content=result.data, isError=False).to_dict()

                    # Otherwise treat as text/json
                    if isinstance(result.data, (dict, list)):
                        content = json.dumps(result.data, indent=2)
                    else:
                        content = str(result.data)
                    return ToolCallResult.text(content).to_dict()
                else:
                    return ToolCallResult.error(result.error or "Unknown error").to_dict()

            return ToolCallResult.text(str(result)).to_dict()

        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return ToolCallResult.error(str(e)).to_dict()

    async def _handle_resources_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle resources/list request."""
        return {
            "resources": [r.to_dict() for r in self._resources.values()]
        }

    async def _handle_resources_read(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle resources/read request."""
        uri = params.get("uri")

        if not uri or uri not in self._resource_handlers:
            raise ValueError(f"Resource not found: {uri}")

        handler = self._resource_handlers[uri]

        try:
            if asyncio.iscoroutinefunction(handler):
                content = await handler(uri)
            else:
                content = handler(uri)

            return {
                "contents": [{
                    "uri": uri,
                    "text": content,
                    "mimeType": self._resources[uri].mimeType
                }]
            }
        except Exception as e:
            raise ValueError(f"Error reading resource: {e}")

    async def _handle_prompts_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle prompts/list request."""
        return {
            "prompts": [p.dict(by_alias=True) for p in self._prompts.values()]  # Use pydantic dict
        }

    async def _handle_prompts_get(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle prompts/get request."""
        name = params.get("name")
        arguments = params.get("arguments", {})

        if not name or name not in self._prompt_handlers:
            raise ValueError(f"Prompt not found: {name}")

        handler = self._prompt_handlers[name]

        try:
            if asyncio.iscoroutinefunction(handler):
                content = await handler(**arguments)
            else:
                content = handler(**arguments)

            return {
                "messages": [{"role": "user", "content": {"type": "text", "text": content}}]
            }
        except Exception as e:
            raise ValueError(f"Error generating prompt: {e}")

    async def run_stdio(self) -> None:
        """
        Run server on stdio.

        Supports both valid JSON-RPC 2.0 (NDJSON) and LSP-style Content-Length framing.
        """

        # Configure logging to stderr to avoid corrupting stdout
        root_logger = logging.getLogger()
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        root_logger.addHandler(handler)
        # Avoid double logging if handlers already exist
        if not root_logger.handlers:
            root_logger.addHandler(handler)
        root_logger.setLevel(logging.INFO)

        logger.info(f"Starting MCP server {self.name} v{self.version} on stdio")

        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()

        if sys.platform == 'win32':
            # Windows: blocking read in thread
            def stdin_feeder():
                try:
                    while True:
                        data = sys.stdin.buffer.read1(4096) if hasattr(sys.stdin.buffer, 'read1') else sys.stdin.buffer.read(1)
                        if not data:
                            break
                        loop.call_soon_threadsafe(reader.feed_data, data)
                except Exception as e:
                    logger.error(f"Stdin error: {e}")
                finally:
                    loop.call_soon_threadsafe(reader.feed_eof)

            import threading
            threading.Thread(target=stdin_feeder, daemon=True).start()
        else:
            # Unix: connect_read_pipe
            protocol = asyncio.StreamReaderProtocol(reader)
            await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)

        # Writer setup
        if sys.platform == 'win32':
             class StdoutWriter:
                 def write(self, data):
                     sys.stdout.buffer.write(data)
                     sys.stdout.buffer.flush()
                 async def drain(self):
                     pass
             writer = StdoutWriter()
        else:
            writer_transport, writer_protocol = await loop.connect_write_pipe(
                asyncio.streams.FlowControlMixin, sys.stdout.buffer
            )
            writer = asyncio.StreamWriter(writer_transport, writer_protocol, None, loop)

        try:
            while self._running:
                # Read line
                line = await reader.readline()
                if not line:
                    break

                line_str = line.decode('utf-8', errors='ignore')

                # Check for Content-Length (LSP mode)
                if line_str.startswith("Content-Length:"):
                    try:
                        content_length = int(line_str.split(":")[1].strip())
                        await reader.readline()  # Blank line

                        # Read content
                        data = await reader.read(content_length)
                        message = data.decode('utf-8')

                        # Handle and respond
                        response = await self.handle_message(message)

                        if response:
                            response_bytes = response.encode('utf-8')
                            header = f"Content-Length: {len(response_bytes)}\r\n\r\n"
                            writer.write(header.encode('utf-8') + response_bytes)
                            await writer.drain()
                    except Exception as e:
                         logger.error(f"Error handling LSP message: {e}")

                # Check for NDJSON (Standard mode)
                else:
                    line_stripped = line_str.strip()
                    if not line_stripped:
                         continue

                    try:
                        json.loads(line_stripped)
                        response = await self.handle_message(line_stripped)
                        if response:
                            writer.write(response.encode('utf-8') + b"\n")
                            await writer.drain()
                    except json.JSONDecodeError:
                        pass
                    except Exception as e:
                        logger.error(f"Error handling NDJSON message: {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Server error: {e}")

    async def run_http(self, host: str = "0.0.0.0", port: int = 3000, path: str = "/mcp") -> None:
        """Run server on HTTP."""
        try:
            from aiohttp import web
        except ImportError:
            raise ImportError("aiohttp required for HTTP server")

        async def handle_request(request: web.Request) -> web.Response:
            try:
                data = await request.json()
                response = await self.handle_message(json.dumps(data))

                if response:
                    return web.json_response(json.loads(response))
                return web.Response(status=204)
            except Exception as e:
                return web.json_response({"error": str(e)}, status=500)

        app = web.Application()
        app.router.add_post(path, handle_request)

        logger.info(f"Starting MCP server {self.name} v{self.version} on http://{host}:{port}{path}")

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()

        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()
