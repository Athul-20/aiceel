# aiccel/agent/config.py
"""
Agent Configuration
===================

All configuration dataclasses and enums for the Agent.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..constants import Limits
from ..exceptions import ValidationException


class ExecutionMode(Enum):
    """Agent execution modes"""
    NORMAL = "normal"
    THINKING = "thinking"
    STRICT_TOOLS = "strict_tools"
    NO_TOOLS = "no_tools"


@dataclass
class AgentConfig:
    """Configuration for agent behavior"""
    name: str = "Agent"
    description: str = "AI Agent"
    instructions: str = "You are a helpful AI assistant. Provide accurate and concise answers."
    memory_type: str = "buffer"
    max_memory_turns: int = Limits.MAX_MEMORY_TURNS
    max_memory_tokens: int = Limits.MAX_MEMORY_TOKENS
    strict_tool_usage: bool = False
    thinking_enabled: bool = False
    verbose: bool = False
    log_file: Optional[str] = None
    timeout: float = Limits.DEFAULT_TIMEOUT
    lightweight: bool = False
    safety_enabled: bool = False

    def validate(self) -> None:
        """Validate configuration parameters"""
        if self.max_memory_turns < 1:
            raise ValidationException("max_memory_turns", "Must be at least 1", self.max_memory_turns)
        if self.max_memory_tokens < 100:
            raise ValidationException("max_memory_tokens", "Must be at least 100", self.max_memory_tokens)
        if self.timeout < 0:
            raise ValidationException("timeout", "Must be positive", self.timeout)
        if self.memory_type not in ("buffer", "summary", "window"):
            raise ValidationException("memory_type", "Must be 'buffer', 'summary', or 'window'", self.memory_type)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
            "memory_type": self.memory_type,
            "max_memory_turns": self.max_memory_turns,
            "max_memory_tokens": self.max_memory_tokens,
            "strict_tool_usage": self.strict_tool_usage,
            "thinking_enabled": self.thinking_enabled,
            "verbose": self.verbose,
            "timeout": self.timeout,
            "lightweight": self.lightweight,
            "safety_enabled": self.safety_enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentConfig":
        """Create from dictionary"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class AgentResponse:
    """Structured response from agent"""
    response: str
    thinking: Optional[str] = None
    tools_used: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    tool_outputs: list[tuple[str, dict[str, Any], str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    execution_time: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "response": self.response,
            "thinking": self.thinking,
            "tools_used": self.tools_used,
            "tool_outputs": self.tool_outputs,
            "metadata": self.metadata,
            "execution_time": self.execution_time,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentResponse":
        """Create from dictionary"""
        return cls(
            response=data.get("response", ""),
            thinking=data.get("thinking"),
            tools_used=data.get("tools_used", []),
            tool_outputs=data.get("tool_outputs", []),
            metadata=data.get("metadata", {}),
            execution_time=data.get("execution_time", 0.0),
        )

    @classmethod
    def error(cls, message: str, execution_time: float = 0.0) -> "AgentResponse":
        """Create error response"""
        return cls(
            response=f"Error: {message}",
            metadata={"error": True, "error_message": message},
            execution_time=execution_time,
        )

    @property
    def has_tools(self) -> bool:
        """Check if tools were used"""
        return bool(self.tools_used)

    @property
    def has_errors(self) -> bool:
        """Check if any tool returned an error"""
        for _, _, output in self.tool_outputs:
            if isinstance(output, str) and output.startswith("Error"):
                return True
        return False

    @property
    def tool_names(self) -> list[str]:
        """Get list of tool names used"""
        return [name for name, _ in self.tools_used]

    def get_tool_output(self, tool_name: str) -> Optional[str]:
        """Get output for a specific tool"""
        for name, _, output in self.tool_outputs:
            if name == tool_name:
                return output
        return None

    def __str__(self) -> str:
        """Human-readable representation"""
        parts = [f"Response: {self.response[:200]}..."]
        if self.tools_used:
            parts.append(f"Tools used: {', '.join(self.tool_names)}")
        if self.thinking:
            parts.append(f"Thinking: {self.thinking[:100]}...")
        parts.append(f"Execution time: {self.execution_time:.2f}s")
        return "\n".join(parts)


@dataclass
class ExecutionContext:
    """Context for agent execution"""
    query: str
    trace_id: int
    has_tools: bool
    relevant_tools: list[Any]
    execution_mode: ExecutionMode
    start_time: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_duration(self) -> float:
        """Get execution duration in seconds"""
        return time.time() - self.start_time

    def add_metadata(self, key: str, value: Any) -> "ExecutionContext":
        """Add metadata to context"""
        self.metadata[key] = value
        return self

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        relevant_tool_names = [
            t.name for t in self.relevant_tools if hasattr(t, "name")
        ]
        return {
            "query": self.query,
            "trace_id": self.trace_id,
            "has_tools": self.has_tools,
            "relevant_tools": relevant_tool_names,
            "execution_mode": self.execution_mode.value,
            "duration": self.get_duration(),
            "metadata": self.metadata,
        }


@dataclass
class ToolCall:
    """Represents a parsed tool call"""
    name: str
    args: dict[str, Any]
    raw_json: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {"name": self.name, "args": self.args}


@dataclass
class ToolCallResult:
    """Result from tool execution"""
    tool_name: str
    args: dict[str, Any]
    output: str
    success: bool
    execution_time: float = 0.0
    error: Optional[str] = None

    def to_tuple(self) -> tuple[str, dict[str, Any], str]:
        """Convert to legacy tuple format"""
        return (self.tool_name, self.args, self.output)
