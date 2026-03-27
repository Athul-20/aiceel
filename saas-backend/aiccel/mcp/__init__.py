# aiccel/mcp/__init__.py
"""
Model Context Protocol (MCP) Support for AICCEL
================================================

Production-ready MCP implementation for connecting AI agents to external
tools, resources, and data sources.

Features:
- MCPClient: Connect to MCP-compliant tool servers
- MCPServer: Expose aiccel tools as MCP tools
- MCPServerBuilder: Fluent API for building MCP servers
- MCPManager: Manage multiple server connections
- MCPAgent: Agent with integrated MCP support
- MCPToolAdapter: Convert MCP tools to aiccel Tool instances
- Multiple transports: stdio, HTTP/SSE, WebSocket

Basic Usage - Client:
    from aiccel.mcp import MCPClient, MCPToolAdapter

    # Connect to an MCP server
    client = MCPClient.from_command(["npx", "@mcp/search-server"])
    await client.connect()

    # Get tools and use with agent
    adapter = MCPToolAdapter(client)
    tools = adapter.get_tools()
    agent = Agent(provider=provider, tools=tools)

Basic Usage - Server:
    from aiccel.mcp import MCPServerBuilder

    server = (
        MCPServerBuilder("my-tools", "1.0.0")
        .add_tool(search_tool)
        .add_tool(weather_tool)
        .with_logging()
        .build()
    )

    await server.run_stdio()

Advanced Usage - MCP Agent:
    from aiccel.mcp import MCPAgent

    async with MCPAgent.connect(
        provider=GeminiProvider(),
        mcp_servers=[
            {"name": "search", "command": ["npx", "@mcp/search"]},
            {"name": "database", "url": "http://localhost:3001/mcp"},
        ]
    ) as agent:
        result = await agent.run_async("Search for AI news")

Multi-Server Management:
    from aiccel.mcp import MCPManager

    manager = MCPManager()
    manager.add_server("search", command=["npx", "@mcp/search"])
    manager.add_server("db", url="http://localhost:3001/mcp")

    await manager.connect_all()
    tools = manager.get_all_tools()
"""

# Protocol definitions
# Adapter
from .adapter import (
    MCPResourceAdapter,
    MCPTool,
    MCPToolAdapter,
    connect_mcp_server,
)

# MCP Agent
from .agent import (
    MCPAgent,
    MCPAgentContext,
    MCPServerSpec,
    create_mcp_agent,
)

# Client
from .client import (
    MCPClient,
    MCPClientError,
)

# Manager
from .manager import (
    MCPManager,
    ServerConfig,
    ServerState,
    ServerStatus,
)
from .protocol import (
    ClientCapabilities,
    InitializeParams,
    InitializeResult,
    JSONSchema,
    MCPError,
    MCPErrorCode,
    MCPMessage,
    MCPMethod,
    MCPNotification,
    MCPProtocol,
    MCPRequest,
    MCPResponse,
    MCPVersion,
    ResourceContent,
    ResourceDefinition,
    ServerCapabilities,
    ToolCallResult,
    ToolDefinition,
)

# Server
from .server import (
    MCPServer as MCPServerLegacy,
)
from .server import (
    run_mcp_server,
)

# Server Builder
from .server_builder import (
    LoggingMiddleware,
    MCPMiddleware,
    MCPServer,
    MCPServerBuilder,
    MetricsMiddleware,
    PromptDefinition,
    RateLimitMiddleware,
)

# Transport layer
from .transports import (
    HTTPSSETransport,
    MCPTransport,
    StdioTransport,
    TransportConfig,
    TransportState,
    WebSocketTransport,
    create_transport,
)


__all__ = [
    "ClientCapabilities",
    "HTTPSSETransport",
    "InitializeParams",
    "InitializeResult",
    "JSONSchema",
    "LoggingMiddleware",
    "MCPAgent",
    "MCPAgentContext",
    # Client
    "MCPClient",
    "MCPClientError",
    "MCPError",
    "MCPErrorCode",
    "MCPManager",
    "MCPMessage",
    "MCPMethod",
    "MCPMiddleware",
    "MCPNotification",
    "MCPProtocol",
    "MCPRequest",
    "MCPResourceAdapter",
    "MCPResponse",
    # Server
    "MCPServer",
    "MCPServerBuilder",
    "MCPServerLegacy",
    # Agent
    "MCPServerSpec",
    # Adapter
    "MCPTool",
    "MCPToolAdapter",
    "MCPTransport",
    # Protocol
    "MCPVersion",
    "MetricsMiddleware",
    "PromptDefinition",
    "RateLimitMiddleware",
    "ResourceContent",
    "ResourceDefinition",
    "ServerCapabilities",
    "ServerConfig",
    "ServerState",
    # Manager
    "ServerStatus",
    "StdioTransport",
    "ToolCallResult",
    "ToolDefinition",
    "TransportConfig",
    # Transports
    "TransportState",
    "WebSocketTransport",
    "connect_mcp_server",
    "create_mcp_agent",
    "create_transport",
    "run_mcp_server",
]
