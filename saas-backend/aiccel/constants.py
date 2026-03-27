# aiccel/constants.py
"""
Constants used throughout the AICCL framework.
Centralizes all magic strings, limits, and configuration values.
"""

from dataclasses import dataclass
from typing import Final


class ToolTags:
    """Tags used for tool invocation parsing"""
    TOOL_START: Final[str] = "[TOOL]"
    TOOL_END: Final[str] = "[/TOOL]"
    NO_TOOL_START: Final[str] = "[NO_TOOL]"
    NO_TOOL_END: Final[str] = "[/NO_TOOL]"


class ErrorMessages:
    """Standard error messages"""
    NO_TOOLS_AVAILABLE: Final[str] = "No tools are available to handle this query"
    TOOL_EXECUTION_FAILED: Final[str] = "Tool execution failed: {error}"
    INVALID_TOOL_RESPONSE: Final[str] = "Invalid tool response format"
    NO_LLM_PROVIDER: Final[str] = "No LLM provider configured"
    MEMORY_FULL: Final[str] = "Memory limit exceeded"
    INVALID_QUERY: Final[str] = "Query cannot be empty"
    TOOL_NOT_FOUND: Final[str] = "Tool '{tool_name}' not found in registry"
    RATE_LIMIT_EXCEEDED: Final[str] = "Rate limit exceeded, please try again later"
    API_KEY_INVALID: Final[str] = "Invalid or missing API key"


class Limits:
    """Resource limits and thresholds"""
    MAX_PROMPT_LENGTH: Final[int] = 8000
    MAX_RESPONSE_LENGTH: Final[int] = 4000
    MAX_TOOL_RETRIES: Final[int] = 3
    MAX_MEMORY_TURNS: Final[int] = 10
    MAX_MEMORY_TOKENS: Final[int] = 1000
    DEFAULT_TIMEOUT: Final[float] = 30.0
    CACHE_TTL: Final[int] = 3600
    CACHE_MAX_SIZE: Final[int] = 1000
    MAX_COMPRESSED_LENGTH: Final[int] = 2000
    MAX_UNCOMPRESSED_LENGTH: Final[int] = 500
    COMPRESSION_LEVEL: Final[int] = 6


class PromptTemplates:
    """Reusable prompt templates"""

    TOOL_SELECTION: Final[str] = """Instructions: {instructions}

Query: {query}

Available tools:
{tool_descriptions}

Select the most appropriate tool(s) for this query. Return JSON array:
["tool1", "tool2"]

Consider:
1. Query intent and requirements
2. Tool capabilities and limitations
3. Multiple tools if needed for complex queries

Return only the JSON array, no markdown."""

    TOOL_USAGE_DECISION: Final[str] = """Instructions: {instructions}

Query: {query}

Available tools:
{tool_descriptions}

Tool usage format:
{tool_tag_start}{{"name":"tool_name","args":{{"param":"value"}}}}{tool_tag_end}

Examples:
{examples}

Provide your response following the tool usage instructions."""

    SYNTHESIS: Final[str] = """Combine the following agent responses into a single, coherent response.

Original Query: {query}

Agent Responses:
{agent_responses}

Requirements:
- Be concise and accurate
- Remove redundancy
- Maintain all important information
- Use natural language
- If agents disagree, note the discrepancy

Response:"""


@dataclass
class CacheConfig:
    """Cache configuration"""
    enabled: bool = True
    ttl: int = Limits.CACHE_TTL
    max_size: int = Limits.CACHE_MAX_SIZE
    compression_enabled: bool = True



@dataclass
class RetryConfig:
    """Retry configuration for resilience"""
    max_attempts: int = Limits.MAX_TOOL_RETRIES
    base_delay: float = 1.0
    max_delay: float = 10.0
    exponential_base: float = 2.0


class Timeouts:
    """Standard timeouts in seconds"""
    DEFAULT_REQUEST: Final[float] = 30.0
    CONNECT: Final[float] = 10.0
    READ: Final[float] = 30.0
    WRITE: Final[float] = 30.0
    LONG_POLLING: Final[float] = 60.0


class Retries:
    """Retry configuration constants"""
    DEFAULT_MAX_ATTEMPTS: Final[int] = 3
    MIN_WAIT: Final[float] = 1.0
    MAX_WAIT: Final[float] = 10.0
    MULTIPLIER: Final[float] = 1.5


class Cache:
    """Cache configuration constants"""
    DEFAULT_TTL: Final[int] = 3600
    DEFAULT_MAX_SIZE: Final[int] = 1000
    SHORT_TTL: Final[int] = 60
    LONG_TTL: Final[int] = 86400


class HTTP:
    """HTTP constants"""
    STATUS_OK: Final[int] = 200
    STATUS_CREATED: Final[int] = 201
    STATUS_BAD_REQUEST: Final[int] = 400
    STATUS_UNAUTHORIZED: Final[int] = 401
    STATUS_FORBIDDEN: Final[int] = 403
    STATUS_NOT_FOUND: Final[int] = 404
    STATUS_RATE_LIMIT: Final[int] = 429
    STATUS_INTERNAL_ERROR: Final[int] = 500

    # Connection pooling
    POOL_CONNECTIONS: Final[int] = 10
    POOL_MAXSIZE: Final[int] = 10
