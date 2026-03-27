# aiccel/mcp/agent.py
"""
MCP-Enabled Agent
=================

Agent that seamlessly integrates MCP tools from multiple servers.

Features:
- Automatic MCP server connection
- Tool aggregation from multiple servers
- Dynamic tool refresh
- Resource access
- Prompt templates

Usage:
    from aiccel.mcp import MCPAgent

    # Simple usage with single server
    agent = await MCPAgent.create(
        provider=GeminiProvider(),
        mcp_servers=[
            {"name": "search", "command": ["npx", "@mcp/search"]},
            {"name": "database", "url": "http://localhost:3001/mcp"},
        ]
    )

    result = agent.run("Search for AI news")

    # With context manager
    async with MCPAgent.connect(
        provider=provider,
        mcp_servers=[...]
    ) as agent:
        result = await agent.run_async("Query")
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional, Union

from .adapter import MCPTool
from .manager import MCPManager, ServerStatus


logger = logging.getLogger(__name__)


@dataclass
class MCPServerSpec:
    """Specification for an MCP server connection."""
    name: str
    url: Optional[str] = None
    command: Optional[list[str]] = None
    cwd: Optional[str] = None
    env: Optional[dict[str, str]] = None
    headers: Optional[dict[str, str]] = None
    enabled: bool = True
    priority: int = 0
    tool_prefix: Optional[str] = None


class MCPAgent:
    """
    Agent with integrated MCP tool support.

    This class wraps a standard aiccel Agent and adds MCP capabilities:
    - Connects to MCP servers on startup
    - Aggregates tools from all connected servers
    - Handles tool refresh on server changes
    - Provides access to MCP resources
    """

    def __init__(
        self,
        provider: Any,
        mcp_manager: MCPManager,
        native_tools: Optional[list[Any]] = None,
        **agent_kwargs
    ):
        """
        Initialize MCP Agent.

        Use MCPAgent.create() or MCPAgent.connect() instead of direct instantiation.

        Args:
            provider: LLM provider
            mcp_manager: Configured MCPManager
            native_tools: Additional non-MCP tools
            **agent_kwargs: Arguments passed to Agent
        """
        self._provider = provider
        self._mcp_manager = mcp_manager
        self._native_tools = native_tools or []
        self._agent_kwargs = agent_kwargs
        self._agent = None
        self._initialized = False

    @classmethod
    async def create(
        cls,
        provider: Any,
        mcp_servers: list[Union[dict[str, Any], MCPServerSpec]],
        native_tools: Optional[list[Any]] = None,
        auto_reconnect: bool = True,
        **agent_kwargs
    ) -> "MCPAgent":
        """
        Create and initialize an MCP Agent.

        Args:
            provider: LLM provider
            mcp_servers: List of MCP server configurations
            native_tools: Additional non-MCP tools
            auto_reconnect: Auto-reconnect to failed servers
            **agent_kwargs: Arguments passed to Agent

        Returns:
            Initialized MCPAgent

        Example:
            agent = await MCPAgent.create(
                provider=GeminiProvider(),
                mcp_servers=[
                    {"name": "search", "command": ["npx", "@mcp/search"]},
                    {"name": "db", "url": "http://localhost:3001/mcp"},
                ]
            )
        """
        # Create manager
        manager = MCPManager(auto_reconnect=auto_reconnect)

        # Add servers
        for server in mcp_servers:
            if isinstance(server, dict):
                manager.add_server(**server)
            else:
                manager.add_server(
                    name=server.name,
                    url=server.url,
                    command=server.command,
                    cwd=server.cwd,
                    env=server.env,
                    headers=server.headers,
                    enabled=server.enabled,
                    priority=server.priority,
                    tool_prefix=server.tool_prefix,
                )

        # Create agent
        mcp_agent = cls(
            provider=provider,
            mcp_manager=manager,
            native_tools=native_tools,
            **agent_kwargs
        )

        # Initialize
        await mcp_agent.initialize()

        return mcp_agent

    @classmethod
    def connect(
        cls,
        provider: Any,
        mcp_servers: list[Union[dict[str, Any], MCPServerSpec]],
        native_tools: Optional[list[Any]] = None,
        **agent_kwargs
    ) -> "MCPAgentContext":
        """
        Create an MCP Agent context manager.

        Usage:
            async with MCPAgent.connect(provider, servers) as agent:
                result = await agent.run_async("Query")

        Returns:
            Context manager that yields MCPAgent
        """
        return MCPAgentContext(
            provider=provider,
            mcp_servers=mcp_servers,
            native_tools=native_tools,
            agent_kwargs=agent_kwargs
        )

    async def initialize(self) -> None:
        """Initialize the agent and connect to MCP servers."""
        if self._initialized:
            return

        # Connect to all MCP servers
        results = await self._mcp_manager.connect_all()
        connected = sum(1 for v in results.values() if v)
        logger.info(f"Connected to {connected}/{len(results)} MCP servers")

        # Register for tool changes
        self._mcp_manager.on("tools_changed", self._on_tools_changed)

        # Create agent with all tools
        self._create_agent()
        self._initialized = True

    async def close(self) -> None:
        """Close all MCP connections."""
        await self._mcp_manager.disconnect_all()
        self._initialized = False

    def run(self, query: str, **kwargs) -> dict[str, Any]:
        """
        Run a query synchronously.

        Args:
            query: User query
            **kwargs: Additional arguments for agent.run()

        Returns:
            Agent response dict
        """
        if not self._initialized:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        return self._agent.run(query, **kwargs)

    async def run_async(self, query: str, **kwargs) -> dict[str, Any]:
        """
        Run a query asynchronously.

        Args:
            query: User query
            **kwargs: Additional arguments

        Returns:
            Agent response dict
        """
        if not self._initialized:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        return await self._agent.run_async(query, **kwargs)

    def get_tools(self) -> list[Any]:
        """Get all available tools (MCP + native)."""
        mcp_tools = self._mcp_manager.get_all_tools()
        return list(mcp_tools) + list(self._native_tools)

    def get_mcp_tools(self) -> list[MCPTool]:
        """Get only MCP tools."""
        return self._mcp_manager.get_all_tools()

    def get_server_status(self) -> dict[str, dict[str, Any]]:
        """Get status of all MCP servers."""
        return self._mcp_manager.get_status()

    def get_memory(self) -> list[dict[str, Any]]:
        """Get conversation memory."""
        return self._agent.get_memory() if self._agent else []

    def clear_memory(self) -> None:
        """Clear conversation memory."""
        if self._agent:
            self._agent.clear_memory()

    async def refresh_tools(self) -> None:
        """Refresh tools from all connected servers."""
        for _name, state in self._mcp_manager._servers.items():
            if state.status == ServerStatus.CONNECTED and state.adapter:
                await state.adapter.refresh_tools()
        self._create_agent()

    async def read_resource(self, server: str, uri: str) -> str:
        """
        Read a resource from an MCP server.

        Args:
            server: Server name
            uri: Resource URI

        Returns:
            Resource content
        """
        client = self._mcp_manager.get_server(server)
        if not client:
            raise ValueError(f"Server '{server}' not connected")

        content = await client.read_resource(uri)
        return content.text or ""

    async def list_resources(self, server: str) -> list[dict[str, Any]]:
        """
        List resources from an MCP server.

        Args:
            server: Server name

        Returns:
            List of resource definitions
        """
        client = self._mcp_manager.get_server(server)
        if not client:
            raise ValueError(f"Server '{server}' not connected")

        resources = await client.list_resources()
        return [r.to_dict() for r in resources]

    def _create_agent(self) -> None:
        """Create or recreate the underlying agent with current tools."""
        from ..agent import Agent

        all_tools = self.get_tools()

        self._agent = Agent(
            provider=self._provider,
            tools=all_tools,
            **self._agent_kwargs
        )

        logger.debug(f"Agent created with {len(all_tools)} tools")

    def _on_tools_changed(self) -> None:
        """Handle MCP tools changed notification."""
        logger.info("MCP tools changed, recreating agent")
        self._create_agent()

    @property
    def config(self):
        """Get agent config."""
        return self._agent.config if self._agent else None

    @property
    def provider(self):
        """Get LLM provider."""
        return self._provider


class MCPAgentContext:
    """Context manager for MCPAgent."""

    def __init__(
        self,
        provider: Any,
        mcp_servers: list[Union[dict[str, Any], MCPServerSpec]],
        native_tools: Optional[list[Any]],
        agent_kwargs: dict[str, Any]
    ):
        self._provider = provider
        self._mcp_servers = mcp_servers
        self._native_tools = native_tools
        self._agent_kwargs = agent_kwargs
        self._agent: Optional[MCPAgent] = None

    async def __aenter__(self) -> MCPAgent:
        self._agent = await MCPAgent.create(
            provider=self._provider,
            mcp_servers=self._mcp_servers,
            native_tools=self._native_tools,
            **self._agent_kwargs
        )
        return self._agent

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._agent:
            await self._agent.close()


# Convenience function
async def create_mcp_agent(
    provider: Any,
    servers: list[dict[str, Any]],
    **kwargs
) -> MCPAgent:
    """
    Convenience function to create an MCP agent.

    Args:
        provider: LLM provider
        servers: List of server configs
        **kwargs: Agent arguments

    Returns:
        Initialized MCPAgent

    Example:
        agent = await create_mcp_agent(
            provider=GeminiProvider(),
            servers=[
                {"name": "tools", "command": ["npx", "@mcp/tools"]},
            ],
            verbose=True
        )
    """
    return await MCPAgent.create(
        provider=provider,
        mcp_servers=servers,
        **kwargs
    )


__all__ = [
    "MCPAgent",
    "MCPAgentContext",
    "MCPServerSpec",
    "create_mcp_agent",
]
