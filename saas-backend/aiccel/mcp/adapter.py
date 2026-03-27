# aiccel/mcp/adapter.py
"""
MCP Tool Adapter
================

Converts MCP tools to aiccel-compatible Tool instances.
Allows seamless integration of MCP servers with aiccel agents.

Usage:
    from aiccel.mcp import MCPClient, MCPToolAdapter

    client = MCPClient.from_url("http://localhost:3000/mcp")
    await client.connect()

    adapter = MCPToolAdapter(client)
    tools = adapter.get_tools()

    # Use with agent
    agent = Agent(provider=provider, tools=tools)
"""

import asyncio
import logging
from typing import Any, Optional

from .client import MCPClient
from .protocol import ToolCallResult, ToolDefinition


logger = logging.getLogger(__name__)


class MCPTool:
    """
    Wrapper that makes an MCP tool compatible with aiccel's Tool interface.

    This class adapts the MCP tool protocol to work with aiccel agents,
    providing sync and async execution methods.
    """

    def __init__(
        self,
        client: MCPClient,
        definition: ToolDefinition,
        timeout: float = 30.0
    ):
        self.client = client
        self.definition = definition
        self.timeout = timeout

        # aiccel Tool interface properties
        self.name = definition.name
        self.description = definition.description
        self.example_usages: list[dict[str, Any]] = []
        self.llm_provider = None
        self.detection_threshold = 0.5

    def execute(self, args: dict[str, Any]) -> str:
        """
        Execute the MCP tool synchronously.

        Args:
            args: Tool arguments

        Returns:
            Tool output as string
        """
        try:
            # Check if we're in a running event loop
            try:
                asyncio.get_running_loop()
                # We're in an async context - use thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.execute_async(args))
                    return future.result(timeout=self.timeout)
            except RuntimeError:
                # No running loop - we can use asyncio.run
                return asyncio.run(self.execute_async(args))
        except Exception as e:
            logger.error(f"Error executing MCP tool {self.name}: {e}")
            return f"Error: {e!s}"

    async def execute_async(self, args: dict[str, Any]) -> str:
        """
        Execute the MCP tool asynchronously.

        Args:
            args: Tool arguments

        Returns:
            Tool output as string
        """
        try:
            result = await asyncio.wait_for(
                self.client.call_tool(self.name, args),
                timeout=self.timeout
            )

            # Convert result to string
            return self._format_result(result)

        except asyncio.TimeoutError:
            error_msg = f"Tool {self.name} timed out after {self.timeout}s"
            logger.error(error_msg)
            return f"Error: {error_msg}"
        except Exception as e:
            logger.error(f"Error executing MCP tool {self.name}: {e}")
            return f"Error: {e!s}"

    def _format_result(self, result: ToolCallResult) -> str:
        """Format ToolCallResult to string"""
        if result.isError:
            text_parts = []
            for content in result.content:
                if content.get("type") == "text":
                    text_parts.append(content.get("text", ""))
            return f"Error: {' '.join(text_parts)}"

        # Concatenate all text content
        text_parts = []
        for content in result.content:
            if content.get("type") == "text":
                text_parts.append(content.get("text", ""))
            elif content.get("type") == "image":
                text_parts.append(f"[Image: {content.get('mimeType', 'image')}]")
            elif content.get("type") == "resource":
                text_parts.append(f"[Resource: {content.get('uri', 'unknown')}]")

        return "\n".join(text_parts) if text_parts else "No output"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation (aiccel Tool interface)"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.definition.inputSchema.to_dict()
        }

    def set_llm_provider(self, provider) -> "MCPTool":
        """Set LLM provider (aiccel Tool interface)"""
        self.llm_provider = provider
        return self

    def add_example(self, example: dict[str, Any]) -> "MCPTool":
        """Add usage example (aiccel Tool interface)"""
        self.example_usages.append(example)
        return self

    def assess_relevance(self, query: str) -> float:
        """Assess tool relevance for query (aiccel Tool interface)"""
        # Simple keyword matching if no LLM provider
        if not self.llm_provider:
            query_lower = query.lower()
            name_words = self.name.replace("_", " ").lower().split()
            desc_words = self.description.lower().split()

            matches = sum(1 for word in name_words if word in query_lower)
            matches += sum(0.5 for word in desc_words[:10] if word in query_lower)

            return min(matches / 5, 1.0)

        # Use LLM for relevance assessment
        prompt = (
            f"Query: {query}\n\n"
            f"Tool: {self.name}\n"
            f"Description: {self.description}\n\n"
            "Rate relevance 0-1. Return only the number."
        )

        try:
            response = self.llm_provider.generate(prompt)
            return float(response.strip())
        except Exception:
            return 0.0

    def is_relevant(self, query: str) -> bool:
        """Check if tool is relevant for query"""
        return self.assess_relevance(query) >= self.detection_threshold


class MCPToolAdapter:
    """
    Adapter for converting MCP tools to aiccel tools.

    This class manages the connection to an MCP server and provides
    aiccel-compatible tool instances that can be used with agents.

    Example:
        client = MCPClient.from_url("http://localhost:3000/mcp")
        await client.connect()

        adapter = MCPToolAdapter(client)
        tools = adapter.get_tools()

        # Register with agent
        agent = Agent(provider=provider, tools=tools)
    """

    def __init__(
        self,
        client: MCPClient,
        tool_timeout: float = 30.0,
        auto_refresh: bool = True
    ):
        self.client = client
        self.tool_timeout = tool_timeout
        self.auto_refresh = auto_refresh
        self._tools: dict[str, MCPTool] = {}

        # Register for tool change notifications
        if auto_refresh:
            client.on_notification(
                "notifications/tools/list_changed",
                self._on_tools_changed
            )

    async def refresh_tools(self) -> None:
        """Refresh tool list from server"""
        definitions = await self.client.list_tools()
        self._tools = {
            d.name: MCPTool(self.client, d, self.tool_timeout)
            for d in definitions
        }
        logger.info(f"Refreshed {len(self._tools)} MCP tools")

    def get_tools(self) -> list[MCPTool]:
        """Get all available tools"""
        return list(self._tools.values())

    def get_tool(self, name: str) -> Optional[MCPTool]:
        """Get tool by name"""
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        """Check if tool exists"""
        return name in self._tools

    def _on_tools_changed(self, params: dict[str, Any]) -> None:
        """Handle tool list change notification"""
        logger.info("MCP tools changed, refreshing...")
        asyncio.create_task(self.refresh_tools())


class MCPResourceAdapter:
    """
    Adapter for converting MCP resources to aiccel-compatible format.

    Resources in MCP are read-only data sources like files, database
    results, or API responses.
    """

    def __init__(self, client: MCPClient):
        self.client = client
        self._resources: dict[str, Any] = {}

    async def refresh_resources(self) -> None:
        """Refresh resource list from server"""
        resources = await self.client.list_resources()
        self._resources = {r.uri: r for r in resources}
        logger.info(f"Refreshed {len(self._resources)} MCP resources")

    async def read(self, uri: str) -> str:
        """Read a resource by URI"""
        content = await self.client.read_resource(uri)
        if content.text:
            return content.text
        if content.blob:
            return f"[Binary content: {content.mimeType or 'unknown'}]"
        return ""

    def list_resources(self) -> list[dict[str, Any]]:
        """List all resources"""
        return [r.to_dict() for r in self._resources.values()]


async def connect_mcp_server(
    url: Optional[str] = None,
    command: Optional[list[str]] = None,
    **kwargs
) -> tuple[MCPClient, MCPToolAdapter]:
    """
    Convenience function to connect to an MCP server and create adapter.

    Args:
        url: HTTP URL for server (mutually exclusive with command)
        command: Command to run server as subprocess
        **kwargs: Additional arguments for client/adapter

    Returns:
        Tuple of (MCPClient, MCPToolAdapter)

    Example:
        client, adapter = await connect_mcp_server(
            url="http://localhost:3000/mcp"
        )
        tools = adapter.get_tools()
    """
    if url:
        client = MCPClient.from_url(url, headers=kwargs.get("headers"))
    elif command:
        client = MCPClient.from_command(
            command,
            cwd=kwargs.get("cwd"),
            env=kwargs.get("env")
        )
    else:
        raise ValueError("Either url or command must be provided")

    await client.connect()

    adapter = MCPToolAdapter(
        client,
        tool_timeout=kwargs.get("tool_timeout", 30.0),
        auto_refresh=kwargs.get("auto_refresh", True)
    )
    await adapter.refresh_tools()

    return client, adapter
