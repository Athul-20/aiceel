# aiccel/mcp/server_builder.py
"""
MCP Server Builder
==================

Fluent API for building production-ready MCP servers.

Features:
- Tool registration with decorators
- Resource serving
- Prompt templates
- Middleware support
- Multiple transports
- Health checks
- Metrics

Usage:
    from aiccel.mcp import MCPServerBuilder

    server = (
        MCPServerBuilder("my-server", "1.0.0")
        .add_tool(search_tool)
        .add_tool(weather_tool)
        .add_resource("config://app", read_config)
        .with_middleware(logging_middleware)
        .build()
    )

    # Run
    await server.run_stdio()

    # Or with decorator
    builder = MCPServerBuilder("my-server")

    @builder.tool("search", "Search the web")
    async def search(query: str) -> str:
        return f"Results for {query}"

    server = builder.build()
"""

import inspect
import logging
from collections.abc import Awaitable
from typing import Any, Callable, Optional, Union, get_type_hints

from .protocol import (
    JSONSchema,
    ResourceDefinition,
    ToolDefinition,
)
from .server import (
    LoggingMiddleware,
    MCPMiddleware,
    MCPServer,
    MetricsMiddleware,
    PromptDefinition,
    RateLimitMiddleware,
)


logger = logging.getLogger(__name__)


class MCPServerBuilder:
    """
    Fluent builder for MCP servers.

    Example:
        server = (
            MCPServerBuilder("my-server", "1.0.0")
            .add_tool(my_tool)
            .add_resource("file://config", read_config)
            .with_middleware(LoggingMiddleware())
            .build()
        )
    """

    def __init__(self, name: str = "aiccel-mcp-server", version: str = "1.0.0"):
        """
        Initialize server builder.

        Args:
            name: Server name
            version: Server version
        """
        self.name = name
        self.version = version

        self._tools: dict[str, Callable] = {}
        self._tool_definitions: dict[str, ToolDefinition] = {}
        self._resources: dict[str, ResourceDefinition] = {}
        self._resource_handlers: dict[str, Callable] = {}
        self._prompts: dict[str, PromptDefinition] = {}
        self._prompt_handlers: dict[str, Callable] = {}
        self._middleware: list[MCPMiddleware] = []
        self._custom_handlers: dict[str, Callable] = {}

    def add_tool(self, tool: Any) -> "MCPServerBuilder":
        """
        Add an aiccel tool.

        Args:
            tool: Tool instance with name, description, execute method

        Returns:
            Self for chaining
        """
        name = tool.name
        self._tools[name] = tool

        # Extract schema from tool
        tool_dict = tool.to_dict() if hasattr(tool, 'to_dict') else {}
        params = tool_dict.get("parameters", {})

        self._tool_definitions[name] = ToolDefinition(
            name=name,
            description=getattr(tool, 'description', ''),
            inputSchema=JSONSchema(
                type=params.get("type", "object"),
                properties=params.get("properties", {}),
                required=params.get("required", [])
            )
        )

        logger.debug(f"Added tool: {name}")
        return self

    def tool(
        self,
        name: str,
        description: str,
        parameters: Optional[dict[str, Any]] = None
    ) -> Callable:
        """
        Decorator to register a function as a tool.

        Example:
            @builder.tool("search", "Search the web")
            async def search(query: str) -> str:
                return f"Results for {query}"
        """
        def decorator(func: Callable) -> Callable:
            # Auto-generate parameters from type hints
            schema = parameters or self._generate_schema(func)

            self._tools[name] = func
            self._tool_definitions[name] = ToolDefinition(
                name=name,
                description=description,
                inputSchema=JSONSchema(**schema) if isinstance(schema, dict) else schema
            )

            logger.debug(f"Registered tool via decorator: {name}")
            return func

        return decorator

    def add_resource(
        self,
        uri: str,
        handler: Callable[[str], Union[str, Awaitable[str]]],
        name: Optional[str] = None,
        description: Optional[str] = None,
        mime_type: Optional[str] = None
    ) -> "MCPServerBuilder":
        """
        Add a resource.

        Args:
            uri: Resource URI (e.g., "file://config", "db://users")
            handler: Function that returns resource content
            name: Display name
            description: Resource description
            mime_type: Content MIME type

        Returns:
            Self for chaining
        """
        self._resources[uri] = ResourceDefinition(
            uri=uri,
            name=name or uri.split("://")[-1],
            description=description,
            mimeType=mime_type
        )
        self._resource_handlers[uri] = handler

        logger.debug(f"Added resource: {uri}")
        return self

    def resource(
        self,
        uri: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        mime_type: Optional[str] = None
    ) -> Callable:
        """
        Decorator to register a resource handler.

        Example:
            @builder.resource("config://app")
            def get_config(uri: str) -> str:
                return json.dumps(config)
        """
        def decorator(func: Callable) -> Callable:
            self.add_resource(uri, func, name, description, mime_type)
            return func
        return decorator

    def add_prompt(
        self,
        name: str,
        description: str,
        handler: Callable[..., str],
        arguments: Optional[list[dict[str, Any]]] = None
    ) -> "MCPServerBuilder":
        """
        Add a prompt template.

        Args:
            name: Prompt name
            description: Prompt description
            handler: Function that generates prompt content
            arguments: Prompt arguments schema

        Returns:
            Self for chaining
        """
        self._prompts[name] = PromptDefinition(
            name=name,
            description=description,
            arguments=arguments or []
        )
        self._prompt_handlers[name] = handler

        logger.debug(f"Added prompt: {name}")
        return self

    def prompt(
        self,
        name: str,
        description: str,
        arguments: Optional[list[dict[str, Any]]] = None
    ) -> Callable:
        """
        Decorator to register a prompt handler.

        Example:
            @builder.prompt("summarize", "Summarize text", [{"name": "text", "required": True}])
            def summarize_prompt(text: str) -> str:
                return f"Please summarize: {text}"
        """
        def decorator(func: Callable) -> Callable:
            self.add_prompt(name, description, func, arguments)
            return func
        return decorator

    def with_middleware(self, middleware: MCPMiddleware) -> "MCPServerBuilder":
        """
        Add middleware to the server.

        Args:
            middleware: MCPMiddleware instance

        Returns:
            Self for chaining
        """
        self._middleware.append(middleware)
        logger.debug(f"Added middleware: {type(middleware).__name__}")
        return self

    def with_logging(self) -> "MCPServerBuilder":
        """Add logging middleware."""
        return self.with_middleware(LoggingMiddleware())

    def with_metrics(self) -> "MCPServerBuilder":
        """Add metrics middleware."""
        return self.with_middleware(MetricsMiddleware())

    def with_rate_limit(self, requests_per_minute: int = 60) -> "MCPServerBuilder":
        """Add rate limiting middleware."""
        return self.with_middleware(RateLimitMiddleware(requests_per_minute))

    def on(self, method: str, handler: Callable) -> "MCPServerBuilder":
        """
        Register custom method handler.

        Args:
            method: MCP method name
            handler: Async handler function

        Returns:
            Self for chaining
        """
        self._custom_handlers[method] = handler
        return self

    def build(self) -> "MCPServer":
        """
        Build the MCP server.

        Returns:
            Configured MCPServer instance
        """
        return MCPServer(
            name=self.name,
            version=self.version,
            tools=self._tools,
            tool_definitions=self._tool_definitions,
            resources=self._resources,
            resource_handlers=self._resource_handlers,
            prompts=self._prompts,
            prompt_handlers=self._prompt_handlers,
            middleware=self._middleware,
            custom_handlers=self._custom_handlers,
        )

    def _generate_schema(self, func: Callable) -> dict[str, Any]:
        """Generate JSON schema from function signature."""
        hints = get_type_hints(func) if hasattr(func, '__annotations__') else {}
        sig = inspect.signature(func)

        properties = {}
        required = []

        for name, param in sig.parameters.items():
            if name in ('self', 'cls'):
                continue

            prop = {"type": "string"}  # Default

            # Map Python types to JSON schema types
            if name in hints:
                hint = hints[name]
                if hint == int:
                    prop = {"type": "integer"}
                elif hint == float:
                    prop = {"type": "number"}
                elif hint == bool:
                    prop = {"type": "boolean"}
                elif hint == list or (hasattr(hint, '__origin__') and hint.__origin__ == list):
                    prop = {"type": "array"}
                elif hint == dict:
                    prop = {"type": "object"}

            properties[name] = prop

            # Required if no default
            if param.default == inspect.Parameter.empty:
                required.append(name)

        return {
            "type": "object",
            "properties": properties,
            "required": required
        }


__all__ = [
    "MCPServerBuilder",
]
