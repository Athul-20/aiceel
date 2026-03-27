
import logging
import re
from typing import Any, Optional

import orjson


logger = logging.getLogger(__name__)

class ResponseParser:
    """Robust parser for LLM responses"""

    @staticmethod
    def clean_json_text(text: str) -> str:
        """Remove markdown formatting and whitespace from JSON text"""
        # Remove code blocks
        cleaned = re.sub(r'^```(?:json)?\n?|\n?```$', '', text.strip(), flags=re.MULTILINE).strip()
        return cleaned

    @staticmethod
    def parse_json(text: str, expected_type: Optional[type] = None) -> Any:
        """
        Parse JSON from text with multiple fallback strategies.

        Args:
            text: The text containing JSON
            expected_type: Optional expected type (dict or list) for validation

        Returns:
            The parsed JSON object or None if parsing fails
        """
        cleaned = ResponseParser.clean_json_text(text)

        # Strategy 1: Direct parsing
        try:
            parsed = orjson.loads(cleaned)
            if expected_type and not isinstance(parsed, expected_type):
                pass  # Use next strategy or return failure later
            else:
                return parsed
        except orjson.JSONDecodeError:
            pass

        # Strategy 2: Regex extraction for arrays
        if expected_type == list:
            json_match = re.search(r'\[\s*\{.*?\}\s*\]', cleaned, re.DOTALL)
            if json_match:
                try:
                    parsed = orjson.loads(json_match.group(0))
                    if isinstance(parsed, list):
                        return parsed
                except orjson.JSONDecodeError:
                    pass

        # Strategy 3: Regex extraction for objects
        if expected_type == dict:
            json_match = re.search(r'\{.*?\}', cleaned, re.DOTALL)
            if json_match:
                try:
                    parsed = orjson.loads(json_match.group(0))
                    if isinstance(parsed, dict):
                        return parsed
                except orjson.JSONDecodeError:
                    pass

        # Strategy 4: Python literal eval (safe-ish subset) - Last Resort
        # This is omitted for security reasons, sticking to JSON standards.

        return None

    @staticmethod
    def parse_tool_selection(response: str, available_tools: dict[str, Any]) -> list[str]:
        """
        Specialized parser for tool selection responses.
        Handles both JSON arrays and quoted string lists.
        """
        if not response:
            return []

        cleaned = ResponseParser.clean_json_text(response)

        # Option A: Valid JSON array
        parsed = ResponseParser.parse_json(cleaned, list)
        if parsed:
             return [str(name) for name in parsed if isinstance(name, str) and name in available_tools]

        # Option B: Regex for loose lists like ["tool1", 'tool2']
        quoted_strings = re.findall(r'["\']([^"\']+)["\']', cleaned)
        if quoted_strings:
            return [name for name in quoted_strings if name in available_tools]

        return []
