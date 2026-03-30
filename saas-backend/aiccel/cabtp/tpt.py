# aiccel/cabtp/tpt.py
"""
Trust Propagation Token (TPT)
=============================

Core cryptographic primitive for the CABTP architecture.

A TPT is a signed, scoped, time-bound token attached to every session.
It carries the user's permission scope and a canary signal for
deterministic prompt-injection detection.

Cryptographic Choices:
    - HMAC-SHA256 for signing (symmetric, < 0.5ms per operation)
    - SHA-256 for origin hashing
    - UUID4 for session identifiers

Usage:
    >>> from aiccel.cabtp.tpt import mint_token, verify_token, derive_child_token
    >>> token = mint_token("session-123", {"user_id": "u1", "role": "analyst"}, secret_key="key")
    >>> assert verify_token(token, secret_key="key")
    >>> child = derive_child_token(token, reduced_scope=["read_data"], secret_key="key")
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Risk Bands ──────────────────────────────────────────────────────

class RiskBand(str, Enum):
    """Jailbreak classification risk zones."""
    LOW = "LOW"       # Score 0.00 – 0.40: safe, full access
    MID = "MID"       # Score 0.41 – 0.75: suspicious, reduced scope
    HIGH = "HIGH"     # Score > 0.75: blocked, no token issued


# ── TPT Schema ──────────────────────────────────────────────────────

class TrustPropagationToken(BaseModel):
    """
    The Trust Propagation Token.

    Fields:
        session_id:       Unique session identifier (UUID4).
        origin_hash:      SHA-256 hash binding the token to the original
                          request and user context. Prevents token reuse
                          across sessions.
        permission_scope: List of granted permissions for this session.
                          Child tokens can only contain a subset of the
                          parent's scope (Scope Inheritance).
        canary_token:     HMAC-SHA256 digest embedded in the system prompt.
                          If the LLM leaks this value in its response,
                          the session is immediately terminated.
        scope_depth:      Number of delegation hops from the root token.
                          Root = 0, first child = 1, etc.
        integrity_sig:    HMAC-SHA256 signature over the entire token
                          payload. Any tampering invalidates the token.
        risk_band:        Classification of the originating prompt.
        expiry:           Unix timestamp after which the token is invalid.
        parent_session_id: Session ID of the parent token (None for root).
    """

    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    origin_hash: str = ""
    permission_scope: list[str] = Field(default_factory=list)
    canary_token: str = ""
    scope_depth: int = 0
    integrity_sig: str = ""
    risk_band: RiskBand = RiskBand.LOW
    expiry: float = 0.0
    parent_session_id: Optional[str] = None


# ── Internal Helpers ────────────────────────────────────────────────

def _compute_origin_hash(request_text: str, user_context: dict[str, Any]) -> str:
    """SHA-256 hash binding the token to the exact request + user."""
    payload = json.dumps(
        {"request": request_text, "context": user_context},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _compute_canary(session_id: str, secret_key: str) -> str:
    """HMAC-SHA256 canary derived from session ID and server secret."""
    return hmac.new(
        secret_key.encode("utf-8"),
        session_id.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _compute_integrity_sig(token: TrustPropagationToken, secret_key: str) -> str:
    """HMAC-SHA256 signature over the token payload (excluding the sig field itself)."""
    payload = token.model_dump(exclude={"integrity_sig"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hmac.new(
        secret_key.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


# ── Public API ──────────────────────────────────────────────────────

def mint_token(
    request_text: str,
    user_context: dict[str, Any],
    secret_key: str,
    permission_scope: Optional[list[str]] = None,
    risk_band: RiskBand = RiskBand.LOW,
    ttl_seconds: float = 300.0,
) -> TrustPropagationToken:
    """
    Mint a new root TPT for a user session.

    Args:
        request_text:     The raw user prompt.
        user_context:     Dictionary with user metadata (user_id, role, etc.).
        secret_key:       Server-side HMAC secret. Never sent to the LLM.
        permission_scope: List of granted permissions. Defaults to ["read_data", "mask_pii"].
        risk_band:        Risk classification from the Jailbreak Shield.
        ttl_seconds:      Token lifetime in seconds (default: 5 minutes).

    Returns:
        A signed TrustPropagationToken.
    """
    if permission_scope is None:
        permission_scope = ["read_data", "mask_pii"]

    session_id = str(uuid.uuid4())

    token = TrustPropagationToken(
        session_id=session_id,
        origin_hash=_compute_origin_hash(request_text, user_context),
        permission_scope=permission_scope,
        canary_token=_compute_canary(session_id, secret_key),
        scope_depth=0,
        risk_band=risk_band,
        expiry=time.time() + ttl_seconds,
        parent_session_id=None,
    )

    token.integrity_sig = _compute_integrity_sig(token, secret_key)
    return token


def sign_token(token: TrustPropagationToken, secret_key: str) -> TrustPropagationToken:
    """
    Re-sign an existing token (e.g., after modification).

    Args:
        token:      The token to sign.
        secret_key: Server-side HMAC secret.

    Returns:
        The token with an updated integrity_sig.
    """
    token.integrity_sig = _compute_integrity_sig(token, secret_key)
    return token


def verify_token(token: TrustPropagationToken, secret_key: str) -> bool:
    """
    Verify a token's integrity and expiry.

    Checks:
        1. The HMAC signature matches the payload (no tampering).
        2. The token has not expired.

    Args:
        token:      The token to verify.
        secret_key: Server-side HMAC secret.

    Returns:
        True if the token is valid, False otherwise.
    """
    # Check expiry
    if time.time() > token.expiry:
        return False

    # Constant-time signature comparison
    expected_sig = _compute_integrity_sig(token, secret_key)
    return hmac.compare_digest(token.integrity_sig, expected_sig)


def derive_child_token(
    parent: TrustPropagationToken,
    reduced_scope: list[str],
    secret_key: str,
    ttl_seconds: Optional[float] = None,
) -> TrustPropagationToken:
    """
    Derive a child TPT from a parent for agent delegation.

    Rules:
        1. The child's permission_scope is the INTERSECTION of the parent's
           scope and the requested reduced_scope. Permissions can only shrink.
        2. scope_depth is incremented by 1.
        3. The child gets a new session_id but inherits the parent's
           origin_hash and canary_token.
        4. The child's expiry cannot exceed the parent's expiry.

    Args:
        parent:         The parent TPT.
        reduced_scope:  The permissions requested for the child agent.
        secret_key:     Server-side HMAC secret.
        ttl_seconds:    Optional override for child TTL.

    Returns:
        A signed child TrustPropagationToken.

    Raises:
        ValueError: If the parent token is invalid or expired.
    """
    if not verify_token(parent, secret_key):
        raise ValueError("Cannot derive from an invalid or expired parent token.")

    # Scope intersection: child can only have permissions the parent has
    inherited_scope = [perm for perm in reduced_scope if perm in parent.permission_scope]

    child_session_id = str(uuid.uuid4())

    # Child expiry cannot exceed parent expiry
    if ttl_seconds is not None:
        child_expiry = min(time.time() + ttl_seconds, parent.expiry)
    else:
        child_expiry = parent.expiry

    child = TrustPropagationToken(
        session_id=child_session_id,
        origin_hash=parent.origin_hash,
        permission_scope=inherited_scope,
        canary_token=parent.canary_token,  # Same canary propagates
        scope_depth=parent.scope_depth + 1,
        risk_band=parent.risk_band,
        expiry=child_expiry,
        parent_session_id=parent.session_id,
    )

    child.integrity_sig = _compute_integrity_sig(child, secret_key)
    return child
