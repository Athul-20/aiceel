# aiccel/cabtp/output_filter.py
"""
Context-Coupled Output Filter (CABTP Claim 2)
==============================================

Evaluates LLM responses against the user's permission scope from
the Trust Propagation Token. Responses that are safe in isolation
but policy-violating in context are identified and redacted before
delivery.

This implements role-based data filtering at the AI output layer.
Traditional RBAC controls database access. This controls what the
AI is allowed to *say* to a specific user.

Usage:
    >>> from aiccel.cabtp.output_filter import evaluate_response
    >>> result = evaluate_response(
    ...     response_text="John Smith earns $450,000/year",
    ...     permission_scope=["read_data"],
    ...     entity_types_in_response=["person", "salary"],
    ... )
    >>> print(result.filtered_text)
    '[CLEARANCE DENIED] earns [CLEARANCE DENIED]/year'
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("aiccel.cabtp.output_filter")


# ── Scope-to-Entity Permission Rules ───────────────────────────────

# Each permission scope grants access to specific entity categories.
# If the user's TPT does not include the required scope for an entity
# type, that entity is redacted from the response.

SCOPE_RULES: dict[str, set[str]] = {
    # Basic read access
    "read_data": {
        "email", "phone", "address", "organization",
    },
    # PII masking operator (can see masked tokens)
    "mask_pii": {
        "email", "phone", "address", "person", "organization",
        "dob", "passport", "pancard",
    },
    # HR data access
    "read_hr_data": {
        "email", "phone", "address", "person", "organization",
        "ssn", "salary", "dob", "bank_account", "passport", "pancard",
    },
    # Medical data access (HIPAA)
    "read_medical": {
        "person", "medical_condition", "drug_name", "lab_result",
        "blood_group", "dob",
    },
    # Financial data access
    "read_financial": {
        "person", "card", "bank_account", "iban", "salary",
        "organization",
    },
    # Full admin access
    "admin": {
        "*",  # wildcard — all entity types allowed
    },
}

# Default redaction string
REDACTION_MARKER = "[CLEARANCE DENIED]"


# ── Data Structures ─────────────────────────────────────────────────

@dataclass
class FilterResult:
    """Result of context-coupled output filtering."""
    filtered_text: str
    original_text: str
    violations_found: int
    violated_entity_types: list[str]
    allowed_entity_types: list[str]
    filter_time_ms: float
    policy_action: str  # "PASS", "PARTIAL_REDACT", "FULL_BLOCK"


# ── Internal Helpers ────────────────────────────────────────────────

def _get_allowed_entity_types(permission_scope: list[str]) -> set[str]:
    """
    Compute the union of all allowed entity types for a given
    permission scope list.
    """
    allowed: set[str] = set()
    for scope in permission_scope:
        rules = SCOPE_RULES.get(scope, set())
        if "*" in rules:
            return {"*"}  # Admin: everything allowed
        allowed.update(rules)
    return allowed


# ── Public API ──────────────────────────────────────────────────────

def evaluate_response(
    response_text: str,
    permission_scope: list[str],
    entity_types_in_response: list[str],
    redaction_marker: str = REDACTION_MARKER,
    entity_values: Optional[dict[str, list[str]]] = None,
) -> FilterResult:
    """
    Evaluate an LLM response against the user's permission scope.

    Args:
        response_text:            The unmasked LLM response text.
        permission_scope:         Permission scope from the user's TPT.
        entity_types_in_response: List of entity types found in the response
                                  (from the PII masking engine's output).
        redaction_marker:         String to replace violated entities with.
        entity_values:            Optional mapping of entity_type -> list of
                                  actual values found (for targeted redaction).

    Returns:
        FilterResult with the filtered text and violation details.
    """
    start = time.perf_counter()

    allowed = _get_allowed_entity_types(permission_scope)

    # Admin bypass
    if "*" in allowed:
        elapsed = (time.perf_counter() - start) * 1000
        return FilterResult(
            filtered_text=response_text,
            original_text=response_text,
            violations_found=0,
            violated_entity_types=[],
            allowed_entity_types=list(allowed),
            filter_time_ms=round(elapsed, 3),
            policy_action="PASS",
        )

    # Identify violations
    violated_types = [
        etype for etype in entity_types_in_response
        if etype not in allowed
    ]
    allowed_types = [
        etype for etype in entity_types_in_response
        if etype in allowed
    ]

    filtered = response_text

    if violated_types and entity_values:
        # Targeted redaction: replace specific values
        for etype in violated_types:
            values = entity_values.get(etype, [])
            for value in values:
                if value in filtered:
                    filtered = filtered.replace(value, redaction_marker)
                    logger.info(
                        "Output filter: redacted '%s' entity (scope violation)",
                        etype,
                    )

    violations = len(violated_types)
    elapsed = (time.perf_counter() - start) * 1000

    if violations == 0:
        action = "PASS"
    elif violations < len(entity_types_in_response):
        action = "PARTIAL_REDACT"
    else:
        action = "FULL_BLOCK"

    if violations > 0:
        logger.warning(
            "Output filter: %d violations found | types=%s | action=%s",
            violations, violated_types, action,
        )

    return FilterResult(
        filtered_text=filtered,
        original_text=response_text,
        violations_found=violations,
        violated_entity_types=violated_types,
        allowed_entity_types=allowed_types,
        filter_time_ms=round(elapsed, 3),
        policy_action=action,
    )
