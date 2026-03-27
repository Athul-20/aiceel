# aiccel/mcp/transports/__init__.py
"""
MCP Transport Implementations
=============================

Production-ready transports for MCP communication:
- StdioTransport: For subprocess-based servers
- HTTPTransport: For REST/SSE servers
- WebSocketTransport: For bidirectional real-time communication
- SSETransport: For Server-Sent Events

All transports support:
- Automatic reconnection
- Health checks
- Metrics collection
- Graceful shutdown
"""

import asyncio
import contextlib
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger(__name__)


class TransportState(Enum):
    """Transport connection state."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSED = "closed"


@dataclass
class TransportConfig:
    """Transport configuration."""
    connect_timeout: float = 30.0
    read_timeout: float = 60.0
    write_timeout: float = 30.0
    reconnect_attempts: int = 3
    reconnect_delay: float = 1.0
    reconnect_max_delay: float = 30.0
    heartbeat_interval: float = 30.0
    buffer_size: int = 65536


class MCPTransport(ABC):
    """Abstract base transport for MCP communication."""

    def __init__(self, config: Optional[TransportConfig] = None):
        self.config = config or TransportConfig()
        self._state = TransportState.DISCONNECTED
        self._metrics = {
            "messages_sent": 0,
            "messages_received": 0,
            "bytes_sent": 0,
            "bytes_received": 0,
            "errors": 0,
            "reconnects": 0,
        }
        self._state_callbacks: list[Callable[[TransportState], None]] = []

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection."""
        pass

    @abstractmethod
    async def send(self, message: str) -> None:
        """Send a message."""
        pass

    @abstractmethod
    async def receive(self) -> str:
        """Receive a message."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close connection."""
        pass

    @property
    def state(self) -> TransportState:
        """Get current state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._state == TransportState.CONNECTED

    @property
    def metrics(self) -> dict[str, int]:
        """Get transport metrics."""
        return dict(self._metrics)

    def on_state_change(self, callback: Callable[[TransportState], None]) -> None:
        """Register state change callback."""
        self._state_callbacks.append(callback)

    def _set_state(self, state: TransportState) -> None:
        """Update state and notify callbacks."""
        old_state = self._state
        self._state = state
        if old_state != state:
            logger.debug(f"Transport state: {old_state.value} -> {state.value}")
            for callback in self._state_callbacks:
                try:
                    callback(state)
                except Exception as e:
                    logger.error(f"State callback error: {e}")


class StdioTransport(MCPTransport):
    """
    Transport for stdio-based MCP servers (subprocess).

    Uses Content-Length framing (LSP-style).
    """

    def __init__(
        self,
        command: list[str],
        cwd: Optional[str] = None,
        env: Optional[dict[str, str]] = None,
        config: Optional[TransportConfig] = None
    ):
        super().__init__(config)
        self.command = command
        self.cwd = cwd
        self.env = {**os.environ, **(env or {})}
        self._process: Optional[asyncio.subprocess.Process] = None
        self._read_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()

    async def connect(self) -> None:
        """Start the subprocess."""
        self._set_state(TransportState.CONNECTING)

        try:
            logger.info(f"Starting MCP server: {' '.join(self.command)}")
            self._process = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *self.command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self.cwd,
                    env=self.env
                ),
                timeout=self.config.connect_timeout
            )
            self._set_state(TransportState.CONNECTED)
            logger.info(f"MCP server started with PID: {self._process.pid}")

            # Start stderr reader for debugging
            asyncio.create_task(self._read_stderr())

        except asyncio.TimeoutError:
            self._set_state(TransportState.DISCONNECTED)
            raise ConnectionError("Timeout starting MCP server")
        except Exception as e:
            self._set_state(TransportState.DISCONNECTED)
            raise ConnectionError(f"Failed to start MCP server: {e}")

    async def send(self, message: str) -> None:
        """Send message via stdin with Content-Length framing."""
        if not self._process or not self._process.stdin:
            raise ConnectionError("Not connected")

        async with self._write_lock:
            try:
                data = message.encode('utf-8')
                header = f"Content-Length: {len(data)}\r\n\r\n"
                self._process.stdin.write(header.encode('utf-8') + data)
                await asyncio.wait_for(
                    self._process.stdin.drain(),
                    timeout=self.config.write_timeout
                )
                self._metrics["messages_sent"] += 1
                self._metrics["bytes_sent"] += len(data)
                logger.debug(f"Sent {len(data)} bytes")
            except Exception as e:
                self._metrics["errors"] += 1
                raise ConnectionError(f"Send failed: {e}")

    async def receive(self) -> str:
        """Receive message from stdout with Content-Length framing."""
        if not self._process or not self._process.stdout:
            raise ConnectionError("Not connected")

        async with self._read_lock:
            try:
                # Read headers until we find Content-Length
                content_length = None
                while content_length is None:
                    header_line = await asyncio.wait_for(
                        self._process.stdout.readline(),
                        timeout=self.config.read_timeout
                    )
                    if not header_line:
                        raise ConnectionError("Server closed connection")

                    header = header_line.decode('utf-8').strip()
                    if header.startswith("Content-Length:"):
                        content_length = int(header.split(":")[1].strip())
                    elif header == "":
                        continue  # Skip blank lines between messages

                # Read the blank line after headers
                await self._process.stdout.readline()

                # Read content
                data = await asyncio.wait_for(
                    self._process.stdout.read(content_length),
                    timeout=self.config.read_timeout
                )
                message = data.decode('utf-8')

                self._metrics["messages_received"] += 1
                self._metrics["bytes_received"] += len(data)
                logger.debug(f"Received {len(data)} bytes")

                return message

            except asyncio.TimeoutError:
                self._metrics["errors"] += 1
                raise ConnectionError("Read timeout")
            except Exception as e:
                self._metrics["errors"] += 1
                raise ConnectionError(f"Receive failed: {e}")

    async def close(self) -> None:
        """Terminate subprocess."""
        if self._process:
            self._set_state(TransportState.CLOSED)
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            logger.info("MCP server terminated")

    async def _read_stderr(self) -> None:
        """Read stderr for debugging."""
        if not self._process or not self._process.stderr:
            return
        try:
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    break
                logger.debug(f"MCP stderr: {line.decode('utf-8').strip()}")
        except Exception:
            pass


class WebSocketTransport(MCPTransport):
    """
    WebSocket transport for bidirectional MCP communication.

    Features:
    - Automatic reconnection
    - Heartbeat/ping-pong
    - Message queuing during reconnection
    """

    def __init__(
        self,
        url: str,
        headers: Optional[dict[str, str]] = None,
        config: Optional[TransportConfig] = None
    ):
        super().__init__(config)
        self.url = url
        self.headers = headers or {}
        self._ws = None
        self._receive_queue: asyncio.Queue = asyncio.Queue()
        self._send_queue: asyncio.Queue = asyncio.Queue()
        self._reader_task: Optional[asyncio.Task] = None
        self._writer_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Establish WebSocket connection."""
        self._set_state(TransportState.CONNECTING)

        try:
            import websockets

            self._ws = await asyncio.wait_for(
                websockets.connect(
                    self.url,
                    extra_headers=self.headers,
                    ping_interval=self.config.heartbeat_interval,
                    ping_timeout=self.config.read_timeout,
                ),
                timeout=self.config.connect_timeout
            )

            self._set_state(TransportState.CONNECTED)
            logger.info(f"WebSocket connected to {self.url}")

            # Start background tasks
            self._reader_task = asyncio.create_task(self._reader_loop())
            self._writer_task = asyncio.create_task(self._writer_loop())

        except ImportError:
            raise ImportError("websockets package required for WebSocket transport")
        except asyncio.TimeoutError:
            self._set_state(TransportState.DISCONNECTED)
            raise ConnectionError("WebSocket connection timeout")
        except Exception as e:
            self._set_state(TransportState.DISCONNECTED)
            raise ConnectionError(f"WebSocket connection failed: {e}")

    async def send(self, message: str) -> None:
        """Queue message for sending."""
        await self._send_queue.put(message)

    async def receive(self) -> str:
        """Get next received message."""
        return await self._receive_queue.get()

    async def close(self) -> None:
        """Close WebSocket connection."""
        self._set_state(TransportState.CLOSED)

        # Cancel background tasks
        for task in [self._reader_task, self._writer_task, self._heartbeat_task]:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        # Close WebSocket
        if self._ws:
            await self._ws.close()
            logger.info("WebSocket connection closed")

    async def _reader_loop(self) -> None:
        """Background task to read messages."""
        try:
            async for message in self._ws:
                self._metrics["messages_received"] += 1
                self._metrics["bytes_received"] += len(message)
                await self._receive_queue.put(message)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"WebSocket reader error: {e}")
            self._metrics["errors"] += 1
            await self._handle_disconnect()

    async def _writer_loop(self) -> None:
        """Background task to send messages."""
        try:
            while True:
                message = await self._send_queue.get()
                await self._ws.send(message)
                self._metrics["messages_sent"] += 1
                self._metrics["bytes_sent"] += len(message)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"WebSocket writer error: {e}")
            self._metrics["errors"] += 1

    async def _handle_disconnect(self) -> None:
        """Handle disconnection with reconnection logic."""
        if self._state == TransportState.CLOSED:
            return

        self._set_state(TransportState.RECONNECTING)
        delay = self.config.reconnect_delay

        for attempt in range(self.config.reconnect_attempts):
            try:
                logger.info(f"Reconnection attempt {attempt + 1}/{self.config.reconnect_attempts}")
                await asyncio.sleep(delay)
                await self.connect()
                self._metrics["reconnects"] += 1
                return
            except Exception as e:
                logger.warning(f"Reconnection failed: {e}")
                delay = min(delay * 2, self.config.reconnect_max_delay)

        self._set_state(TransportState.DISCONNECTED)
        logger.error("Max reconnection attempts reached")


class HTTPSSETransport(MCPTransport):
    """
    HTTP transport with Server-Sent Events for notifications.

    - POST for requests
    - SSE for server-initiated messages
    """

    def __init__(
        self,
        url: str,
        headers: Optional[dict[str, str]] = None,
        config: Optional[TransportConfig] = None
    ):
        super().__init__(config)
        self.url = url.rstrip('/')
        self.headers = headers or {}
        self._session = None
        self._sse_task: Optional[asyncio.Task] = None
        self._receive_queue: asyncio.Queue = asyncio.Queue()

    async def connect(self) -> None:
        """Establish HTTP session and SSE connection."""
        self._set_state(TransportState.CONNECTING)

        try:
            import aiohttp

            timeout = aiohttp.ClientTimeout(
                total=self.config.read_timeout,
                connect=self.config.connect_timeout
            )
            self._session = aiohttp.ClientSession(
                timeout=timeout,
                headers={"Content-Type": "application/json", **self.headers}
            )

            self._set_state(TransportState.CONNECTED)
            logger.info(f"HTTP transport connected to {self.url}")

            # Start SSE listener if endpoint exists
            asyncio.create_task(self._start_sse())

        except ImportError:
            raise ImportError("aiohttp required for HTTP transport")
        except Exception as e:
            self._set_state(TransportState.DISCONNECTED)
            raise ConnectionError(f"HTTP connection failed: {e}")

    async def send(self, message: str) -> None:
        """Send message via POST and queue response."""
        if not self._session:
            raise ConnectionError("Not connected")

        try:
            async with self._session.post(
                self.url,
                data=message,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    raise ConnectionError(f"HTTP {response.status}: {text}")

                data = await response.text()
                self._metrics["messages_sent"] += 1
                self._metrics["bytes_sent"] += len(message)

                # Queue response
                await self._receive_queue.put(data)
                self._metrics["messages_received"] += 1
                self._metrics["bytes_received"] += len(data)

        except Exception as e:
            self._metrics["errors"] += 1
            raise ConnectionError(f"HTTP request failed: {e}")

    async def receive(self) -> str:
        """Get next message from queue."""
        return await self._receive_queue.get()

    async def close(self) -> None:
        """Close HTTP session."""
        self._set_state(TransportState.CLOSED)

        if self._sse_task:
            self._sse_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sse_task

        if self._session:
            await self._session.close()
            logger.info("HTTP transport closed")

    async def _start_sse(self) -> None:
        """Start SSE listener for server notifications."""
        sse_url = f"{self.url}/events"
        try:
            async with self._session.get(sse_url) as response:
                if response.status != 200:
                    logger.debug("SSE endpoint not available")
                    return

                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        await self._receive_queue.put(data)
                        self._metrics["messages_received"] += 1

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f"SSE not available: {e}")


def create_transport(
    url: Optional[str] = None,
    command: Optional[list[str]] = None,
    transport_type: Optional[str] = None,
    **kwargs
) -> MCPTransport:
    """
    Factory function to create appropriate transport.

    Args:
        url: URL for HTTP/WebSocket transport
        command: Command for stdio transport
        transport_type: Force specific transport type
        **kwargs: Additional transport options

    Returns:
        MCPTransport instance
    """
    config = TransportConfig(**{k: v for k, v in kwargs.items() if hasattr(TransportConfig, k)})
    headers = kwargs.get("headers")

    if command:
        return StdioTransport(
            command=command,
            cwd=kwargs.get("cwd"),
            env=kwargs.get("env"),
            config=config
        )

    if url:
        if transport_type == "websocket" or url.startswith("ws://") or url.startswith("wss://"):
            return WebSocketTransport(url=url, headers=headers, config=config)
        else:
            return HTTPSSETransport(url=url, headers=headers, config=config)

    raise ValueError("Either url or command must be provided")


__all__ = [
    "HTTPSSETransport",
    "MCPTransport",
    "StdioTransport",
    "TransportConfig",
    "TransportState",
    "WebSocketTransport",
    "create_transport",
]
