# aiccel/base_custom_tool.py
"""
Base class for custom tools in AICCL framework.
"""

from abc import ABC, abstractmethod
from typing import Any

from .tools import Tool  # Fixed relative import


class BaseCustomTool(Tool, ABC):
    """Base class for custom tools in AICCL framework."""

    def __init__(
        self,
        name: str,
        description: str,
        capability_keywords: list[str],
        detection_patterns: list[str],
        parameters: dict[str, Any],
        examples: list[dict[str, Any]],
        detection_threshold: float,
        llm_provider: Any
    ):
        """
        Initialize the custom tool.

        Args:
            name: Name of the tool.
            description: Description of the tool's functionality.
            capability_keywords: Keywords indicating tool capabilities.
            detection_patterns: Regex patterns for query matching.
            parameters: JSON schema for tool parameters.
            examples: Example inputs for the tool.
            detection_threshold: Confidence threshold for tool selection.
            llm_provider: LLM provider instance for response generation.
        """
        # Pass a lambda that calls the abstract _execute method
        super().__init__(
            name=name,
            description=description,
            capability_keywords=capability_keywords,
            detection_patterns=detection_patterns,
            detection_threshold=detection_threshold,
            function=lambda args: self._execute(args)
        )
        self.parameters = parameters
        self.examples = examples
        self.llm_provider = llm_provider

    @abstractmethod
    def _execute(self, args: dict[str, Any]) -> str:
        """
        Execute the tool with the provided arguments.

        Args:
            args: Dictionary of arguments as per the tool's parameters schema.

        Returns:
            The result of the tool execution as a string.
        """
        pass

    def execute(self, args: dict[str, Any]) -> str:
        """
        Public method to execute the tool, delegating to _execute.

        Args:
            args: Dictionary of arguments.

        Returns:
            The tool's output.
        """
        try:
            return self._execute(args)
        except Exception as e:
            return f"Error executing {self.name}: {e!s}"
