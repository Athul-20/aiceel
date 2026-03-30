# aiccel/cabtp/__init__.py
"""
CABTP – Cryptographically-Anchored Bidirectional Trust Propagation
==================================================================

Zero-trust security layer for AICCEL's LLM Privacy Gateway.

Modules:
    tpt           - Trust Propagation Token (mint, sign, verify, derive)
    canary        - ZK Canary injection and response scanning (merged)
    output_filter - Context-coupled output filtering (Claim 2)
    audit_ledger  - Immutable hash-chained audit log (Claim 5)
"""

from .tpt import (
    TrustPropagationToken,
    RiskBand,
    mint_token,
    sign_token,
    verify_token,
    derive_child_token,
)
from .canary import (
    inject_canary,
    scan_response,
    prove_canary,
    CommitmentTier,
    ScanResult,
)
from .output_filter import evaluate_response, FilterResult, SCOPE_RULES
from .audit_ledger import AuditLedger, AuditEntry

__all__ = [
    "TrustPropagationToken",
    "RiskBand",
    "mint_token",
    "sign_token",
    "verify_token",
    "derive_child_token",
    "inject_canary",
    "scan_response",
    "prove_canary",
    "CommitmentTier",
    "ScanResult",
    "evaluate_response",
    "FilterResult",
    "SCOPE_RULES",
    "AuditLedger",
    "AuditEntry",
]
