# aiccel/utils/json_parser.py
"""
Robust JSON Parser
==================

Helper to parse JSON from LLM responses.
"""

import contextlib
import re
from typing import Any, Optional

import orjson

from ..logger import AILogger


def clean_and_parse_json(
    response: str,
    context: str = "json_parse",
    schema_class: Optional[type] = None,
    logger: Optional[AILogger] = None
) -> Any:
    """Robust JSON parsing with optional Pydantic validation."""

    # Remove markdown
    cleaned = re.sub(r'^```(?:json)?\n?|\n?```$', '', response.strip(), flags=re.MULTILINE).strip()

    # Attempt 1: Direct parsing
    parsed = None
    try:
        parsed = orjson.loads(cleaned)
    except orjson.JSONDecodeError:
        # Attempt 2: Extract JSON (array or object)
        # Use simple greedy search for first [ or {
        json_match = re.search(r'(\[.*?\]|\{.*?\})', cleaned, re.DOTALL)
        if json_match:
            with contextlib.suppress(orjson.JSONDecodeError):
                parsed = orjson.loads(json_match.group(0))

    if parsed is not None:
        if schema_class:
            try:
                # If it's a list but we expect a wrapping object (special case for CollaborationPlan if needed)
                # But generally we rely on the caller to provide correct schema
                return schema_class.model_validate(parsed)
            except Exception as e:
                if logger:
                    logger.warning(f"Schema validation failed for {context}: {e}")
                raise ValueError(f"Schema validation failed: {e}")
        return parsed

    msg = f"Failed to parse JSON for {context}"
    if logger:
        logger.warning(msg)
    raise ValueError(msg)
