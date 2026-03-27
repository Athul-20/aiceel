# aiccel/mcp/protocol.py
"""
Model Context Protocol (MCP) Protocol Definitions
==================================================

Implements the MCP protocol specification for tool/resource communication.
Based on the Anthropic MCP specification and JSON-RPC 2.0.

References:
- https://github.com/anthropics/mcp
- https://www.jsonrpc.org/specification
"""

import uuid
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class MCPVersion:
    """MCP Protocol Version"""
    CURRENT = "2024-11-05"
    SUPPORTED = ["2024-11-05", "2024-10-01"]


class MCPMethod(str, Enum):
    """Standard MCP methods"""
    # Lifecycle
    INITIALIZE = "initialize"
    INITIALIZED = "notifications/initialized"
    SHUTDOWN = "shutdown"

    # Tools
    TOOLS_LIST = "tools/list"
    TOOLS_CALL = "tools/call"

    # Resources
    RESOURCES_LIST = "resources/list"
    RESOURCES_READ = "resources/read"
    RESOURCES_SUBSCRIBE = "resources/subscribe"
    RESOURCES_UNSUBSCRIBE = "resources/unsubscribe"

    # Prompts
    PROMPTS_LIST = "prompts/list"
    PROMPTS_GET = "prompts/get"

    # Logging
    LOGGING_SET_LEVEL = "logging/setLevel"

    # Notifications
    PROGRESS = "notifications/progress"
    MESSAGE = "notifications/message"
    RESOURCES_UPDATED = "notifications/resources/updated"
    TOOLS_CHANGED = "notifications/tools/list_changed"


class MCPErrorCode(int, Enum):
    """Standard JSON-RPC and MCP error codes"""
    # JSON-RPC standard errors
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # MCP-specific errors
    RESOURCE_NOT_FOUND = -32001
    TOOL_NOT_FOUND = -32002
    TOOL_EXECUTION_ERROR = -32003
    INVALID_TOOL_ARGS = -32004
    TIMEOUT = -32005


class MCPBaseModel(BaseModel):
    """Base model for all MCP objects"""
    model_config = ConfigDict(populate_by_name=True)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (alias for model_dump for compatibility)"""
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]):
        """Create from dictionary (alias for model_validate)"""
        return cls.model_validate(data)


class MCPError(MCPBaseModel):
    """MCP Error object"""
    code: int
    message: str
    data: Optional[Any] = None


class JSONSchema(MCPBaseModel):
    """JSON Schema for tool parameters"""
    type: str = "object"
    properties: dict[str, dict[str, Any]] = Field(default_factory=dict)
    required: list[str] = Field(default_factory=list)
    description: Optional[str] = None


class ToolDefinition(MCPBaseModel):
    """MCP Tool definition"""
    name: str
    description: str = ""
    inputSchema: JSONSchema = Field(default_factory=JSONSchema)


class ToolCallResult(MCPBaseModel):
    """Result of tool call"""
    content: list[dict[str, Any]]  # Array of content items (text, image, etc.)
    isError: bool = False

    @classmethod
    def text(cls, text: str, is_error: bool = False) -> "ToolCallResult":
        """Create a text result"""
        return cls(
            content=[{"type": "text", "text": text}],
            isError=is_error
        )

    @classmethod
    def error(cls, message: str) -> "ToolCallResult":
        """Create an error result"""
        return cls.text(message, is_error=True)


class ResourceDefinition(MCPBaseModel):
    """MCP Resource definition"""
    uri: str
    name: str
    description: Optional[str] = None
    mimeType: Optional[str] = None


class ResourceContent(MCPBaseModel):
    """Content of a resource"""
    uri: str
    text: Optional[str] = None
    blob: Optional[str] = None  # base64 encoded
    mimeType: Optional[str] = None


class MCPMessage(MCPBaseModel):
    """Base MCP message (JSON-RPC 2.0)"""
    jsonrpc: str = "2.0"

    def to_json(self) -> str:
        return self.model_dump_json(exclude_none=True)


class MCPRequest(MCPMessage):
    """MCP Request message"""
    id: Union[str, int] = Field(default_factory=lambda: str(uuid.uuid4()))
    method: str
    params: Optional[dict[str, Any]] = None


class MCPResponse(MCPMessage):
    """MCP Response message"""
    id: Union[str, int]
    result: Optional[Any] = None
    error: Optional[MCPError] = None

    @classmethod
    def success(cls, id: Union[str, int], result: Any) -> "MCPResponse":
        return cls(id=id, result=result)

    @classmethod
    def failure(cls, id: Union[str, int], code: int, message: str, data: Any = None) -> "MCPResponse":
        return cls(id=id, error=MCPError(code=code, message=message, data=data))


class MCPNotification(MCPMessage):
    """MCP Notification message (no response expected)"""
    method: str
    params: Optional[dict[str, Any]] = None


class ServerCapabilities(MCPBaseModel):
    """Server capabilities advertised during initialization"""
    tools: Optional[dict[str, Any]] = None
    resources: Optional[dict[str, Any]] = None
    prompts: Optional[dict[str, Any]] = None
    logging: Optional[dict[str, Any]] = None


class ClientCapabilities(MCPBaseModel):
    """Client capabilities sent during initialization"""
    roots: Optional[dict[str, Any]] = None
    sampling: Optional[dict[str, Any]] = None


class InitializeParams(MCPBaseModel):
    """Parameters for initialize request"""
    protocolVersion: str
    capabilities: ClientCapabilities
    clientInfo: dict[str, str]


class InitializeResult(MCPBaseModel):
    """Result of initialize request"""
    protocolVersion: str
    capabilities: ServerCapabilities
    serverInfo: dict[str, str]


class MCPProtocol(ABC):
    "Abstract base class for MCP protocol handlers"

    @abstractmethod
    async def send_request(self, method: str, params: Optional[dict[str, Any]] = None) -> Any:
        "Send a request and wait for response"
        pass

    @abstractmethod
    async def send_notification(self, method: str, params: Optional[dict[str, Any]] = None) -> None:
        "Send a notification (no response expected)"
        pass

    @abstractmethod
    async def receive(self) -> MCPMessage:
        "Receive next message"
        pass

    @abstractmethod
    async def close(self) -> None:
        "Close the connection"
        pass
