# aiccel/tools/base.py
"""
Tool Base Classes and Interfaces
================================

Provides abstract interfaces and base classes for the AICCEL tool system.
This is the canonical location for tool-related classes.

Usage:
    from aiccel.tools import BaseTool, ToolResult, ToolSchema

    class MyTool(BaseTool):
        ...
"""

import asyncio
import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

# Import exceptions and types from canonical source
from ..exceptions import (
    ToolConfigurationError,
    ToolError,
    ToolExecutionError,
    ToolValidationError,
)
from ..interfaces import Tool, ToolResult


logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

class ParameterType(str, Enum):
    """Supported parameter types"""
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


@dataclass
class ParameterSchema:
    """Schema for a tool parameter"""
    name: str
    type: ParameterType
    description: str = ""
    required: bool = False
    default: Any = None
    enum: Optional[list[Any]] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None
    items: Optional["ParameterSchema"] = None  # For array types

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON Schema format"""
        result = {
            "type": self.type.value,
            "description": self.description
        }

        if self.enum:
            result["enum"] = self.enum
        if self.min_length is not None:
            result["minLength"] = self.min_length
        if self.max_length is not None:
            result["maxLength"] = self.max_length
        if self.pattern:
            result["pattern"] = self.pattern
        if self.items:
            result["items"] = self.items.to_dict()
        if self.default is not None:
            result["default"] = self.default

        return result

    def validate(self, value: Any) -> tuple[bool, Optional[str]]:
        """Validate a value against this schema"""
        if value is None:
            if self.required:
                return False, f"Parameter '{self.name}' is required"
            return True, None

        # Type checking
        type_validators = {
            ParameterType.STRING: lambda v: isinstance(v, str),
            ParameterType.NUMBER: lambda v: isinstance(v, (int, float)),
            ParameterType.INTEGER: lambda v: isinstance(v, int),
            ParameterType.BOOLEAN: lambda v: isinstance(v, bool),
            ParameterType.ARRAY: lambda v: isinstance(v, list),
            ParameterType.OBJECT: lambda v: isinstance(v, dict),
        }

        validator = type_validators.get(self.type)
        if validator and not validator(value):
            return False, f"Parameter '{self.name}' must be of type {self.type.value}"

        # String-specific validation
        if self.type == ParameterType.STRING and isinstance(value, str):
            if self.min_length is not None and len(value) < self.min_length:
                return False, f"Parameter '{self.name}' must be at least {self.min_length} characters"
            if self.max_length is not None and len(value) > self.max_length:
                return False, f"Parameter '{self.name}' must be at most {self.max_length} characters"
            if self.pattern and not re.match(self.pattern, value):
                return False, f"Parameter '{self.name}' does not match required pattern"

        # Enum validation
        if self.enum and value not in self.enum:
            return False, f"Parameter '{self.name}' must be one of: {self.enum}"

        return True, None


@dataclass
class ToolSchema:
    """Complete schema for a tool"""
    name: str
    description: str
    parameters: list[ParameterSchema] = field(default_factory=list)
    version: str = "1.0.0"
    category: Optional[str] = None
    tags: list[str] = field(default_factory=list)

    @property
    def required_parameters(self) -> list[str]:
        """Get list of required parameter names"""
        return [p.name for p in self.parameters if p.required]

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON Schema format"""
        properties = {}
        for param in self.parameters:
            properties[param.name] = param.to_dict()

        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": self.required_parameters
            }
        }

    def get_parameter(self, name: str) -> Optional[ParameterSchema]:
        """Get parameter by name"""
        for param in self.parameters:
            if param.name == name:
                return param
        return None





# =============================================================================
# TOOL VALIDATOR
# =============================================================================

class ToolValidator:
    """Validates tool inputs against schemas"""

    def validate(self, schema: ToolSchema, args: dict[str, Any]) -> tuple[bool, list[str]]:
        """
        Validate arguments against tool schema.

        Args:
            schema: Tool schema
            args: Arguments to validate

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Check required parameters
        for param_name in schema.required_parameters:
            if param_name not in args or args[param_name] is None:
                errors.append(f"Missing required parameter: {param_name}")

        # Validate each provided argument
        for name, value in args.items():
            param = schema.get_parameter(name)
            if param:
                is_valid, error = param.validate(value)
                if not is_valid:
                    errors.append(error)
            else:
                # Unknown parameter - could be a warning
                logger.debug(f"Unknown parameter for {schema.name}: {name}")

        return len(errors) == 0, errors

    def coerce_types(self, schema: ToolSchema, args: dict[str, Any]) -> dict[str, Any]:
        """
        Attempt to coerce argument types to match schema.

        Args:
            schema: Tool schema
            args: Arguments to coerce

        Returns:
            Arguments with coerced types
        """
        coerced = {}

        for name, value in args.items():
            param = schema.get_parameter(name)
            if param and value is not None:
                try:
                    coerced[name] = self._coerce_value(value, param.type)
                except (ValueError, TypeError):
                    coerced[name] = value
            else:
                coerced[name] = value

        return coerced

    def _coerce_value(self, value: Any, target_type: ParameterType) -> Any:
        """Coerce a single value to target type"""
        if target_type == ParameterType.STRING:
            return str(value)
        elif target_type == ParameterType.INTEGER:
            return int(value)
        elif target_type == ParameterType.NUMBER:
            return float(value)
        elif target_type == ParameterType.BOOLEAN:
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes")
            return bool(value)
        return value


# =============================================================================
# TOOL PROTOCOL (INTERFACE)
# =============================================================================

class ToolProtocol(Tool, ABC):
    """
    Abstract interface for all tools.

    This defines the contract that all tools must implement.
    It ensures consistency across tool implementations.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name (unique identifier)"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description"""
        pass

    @property
    @abstractmethod
    def schema(self) -> ToolSchema:
        """Full tool schema"""
        pass

    @abstractmethod
    def execute(self, args: dict[str, Any]) -> ToolResult:
        """Execute the tool synchronously"""
        pass

    async def execute_async(self, args: dict[str, Any]) -> ToolResult:
        """Execute the tool asynchronously (default: run sync in executor)"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.execute, args)

    def validate(self, args: dict[str, Any]) -> tuple[bool, list[str]]:
        """Validate arguments against schema"""
        validator = ToolValidator()
        return validator.validate(self.schema, args)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation"""
        return self.schema.to_dict()


# =============================================================================
# BASE TOOL IMPLEMENTATION
# =============================================================================

class BaseTool(ToolProtocol):
    """
    Base implementation of ToolProtocol.

    Provides common functionality and can be subclassed.
    """

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Optional[list[ParameterSchema]] = None,
        executor: Optional[Callable[[dict[str, Any]], Any]] = None,
        timeout: float = 30.0
    ):
        self._name = name
        self._description = description
        self._parameters = parameters or []
        self._executor = executor
        self._timeout = timeout
        self._validator = ToolValidator()

        # For compatibility with old interface
        self.example_usages: list[dict[str, Any]] = []
        self.llm_provider = None
        self.detection_threshold = 0.5

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name=self._name,
            description=self._description,
            parameters=self._parameters
        )

    def execute(self, args: dict[str, Any]) -> ToolResult:
        """Execute with validation and error handling"""
        start_time = time.time()

        # Coerce types (handle stringified numbers/bools from LLMs)
        try:
            args = self._validator.coerce_types(self.schema, args)
        except Exception as e:
            logger.warning(f"Argument coercion failed: {e}")

        # Validate inputs
        is_valid, errors = self.validate(args)
        if not is_valid:
            return ToolResult.fail(
                f"Validation failed: {'; '.join(errors)}",
                execution_time=time.time() - start_time
            )

        try:
            result = self._executor(args) if self._executor else self._execute(args)

            execution_time = time.time() - start_time

            if isinstance(result, ToolResult):
                result.execution_time = execution_time
                return result

            return ToolResult.ok(result, execution_time=execution_time)

        except Exception as e:
            return ToolResult.fail(
                str(e),
                execution_time=time.time() - start_time
            )

    def _execute(self, args: dict[str, Any]) -> Any:
        """Override this in subclasses for custom execution"""
        raise NotImplementedError("Subclasses must implement _execute or provide executor")

    # Compatibility methods for old interface
    def set_llm_provider(self, provider) -> "BaseTool":
        self.llm_provider = provider
        return self

    def add_example(self, example: dict[str, Any]) -> "BaseTool":
        self.example_usages.append(example)
        return self

    def assess_relevance(self, query: str) -> float:
        if not self.llm_provider:
            return 0.0
        # Implement LLM-based relevance
        return 0.5

    def is_relevant(self, query: str) -> bool:
        return self.assess_relevance(query) >= self.detection_threshold
