"""
AICCEL Jailbreak Classifier — backend-local copy
=================================================

This is intentionally self-contained so the backend does not depend on the
installed version of the `aiccel` package (which may be stale/out-of-sync).

Falls back to a fast regex-based heuristic if the HuggingFace model is
unavailable, ensuring the backend always starts successfully.
"""

from __future__ import annotations

import os
import re
from threading import Lock
from typing import Any

# ── Config ───────────────────────────────────────────────────────────
_DEFAULT_MODEL = "traromal/AIccel_Jailbreak"
_DISABLED_VALUES = {"0", "false", "no", "off"}

_INJECTION_PATTERNS = [
    r"ignore\s+(previous|prior|all)\s+instructions?",
    r"disregard\s+(your|all|previous)\s+",
    r"forget\s+(everything|all|your)\s+",
    r"you\s+are\s+now\s+(a|an|the)\s+",
    r"act\s+as\s+(if|though|a|an)\s+",
    r"pretend\s+(you\s+are|to\s+be)\s+",
    r"jailbreak",
    r"DAN\s+(mode|prompt|test)",
    r"do\s+anything\s+now",
    r"system\s+prompt\s*[:=]",
    r"override\s+(your\s+)?(programming|instructions|safety)",
    r"reveal\s+(your|the)\s+(system\s+prompt|instructions|prompt)",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]


def _is_enabled() -> bool:
    raw = os.getenv("AICCEL_JAILBREAK_MODEL_ENABLED", "1").strip().lower()
    return raw not in _DISABLED_VALUES


def _score_threshold() -> float:
    raw = os.getenv("AICCEL_JAILBREAK_SCORE_THRESHOLD", "0.60").strip()
    try:
        return max(0.0, min(1.0, float(raw)))
    except ValueError:
        return 0.60


# ── Singleton model state (thread-safe lazy load) ────────────────────
_clf_lock = Lock()
_clf: Any | None = None
_clf_attempted = False
_clf_error: str | None = None


def _load_clf() -> Any | None:
    global _clf, _clf_attempted, _clf_error
    if _clf_attempted:
        return _clf
    with _clf_lock:
        if _clf_attempted:
            return _clf
        _clf_attempted = True
        if not _is_enabled():
            _clf_error = "disabled"
            return None
        try:
            from transformers import pipeline
            _clf = pipeline("text-classification", model=os.getenv("AICCEL_JAILBREAK_MODEL", _DEFAULT_MODEL))
        except Exception as exc:
            _clf_error = f"{exc.__class__.__name__}: {exc}"
            _clf = None
    return _clf


def _regex_check(text: str) -> tuple[bool, float]:
    """Heuristic fallback when model is unavailable."""
    for pattern in _COMPILED:
        if pattern.search(text):
            return True, 0.95
    return False, 0.05


# ── Public API ───────────────────────────────────────────────────────

def classify_jailbreak_text(text: str) -> dict[str, Any]:
    """
    Classify *text* for jailbreak / prompt-injection attempts.

    Returns a dict with keys:
        enabled   – whether classification is turned on
        available – whether the ML model loaded successfully
        detected  – True when the prompt looks like a jailbreak attempt
        label     – raw model label (or 'heuristic')
        score     – confidence 0-1
        error     – error string or None
    """
    clf = _load_clf()
    threshold = _score_threshold()

    if clf is None:
        # Fall back to regex heuristic
        detected, score = _regex_check(text)
        return {
            "enabled": _is_enabled(),
            "available": False,
            "detected": detected,
            "label": "heuristic",
            "score": score,
            "error": _clf_error,
        }

    try:
        raw = clf(text[:512])
        if isinstance(raw, list) and raw:
            item = raw[0]
        else:
            item = raw or {}
        label = str(item.get("label", "")).lower()
        score = float(item.get("score", 0.0))
        
        safe_hints = ("safe", "benign", "normal", "label_0", "non-jailbreak", "not_jailbreak")
        unsafe_hints = ("jailbreak", "prompt_injection", "injection", "unsafe", "malicious", "attack", "label_1")
        
        is_safe_label = any(h in label for h in safe_hints)
        is_unsafe_label = any(h in label for h in unsafe_hints)

        if is_safe_label:
            detected = False
        elif is_unsafe_label:
            detected = score >= threshold
        else:
            detected = score >= threshold and label == "label_1"

        return {
            "enabled": True,
            "available": True,
            "detected": detected,
            "label": label,
            "score": score,
            "error": None,
        }
    except Exception as exc:
        detected, score = _regex_check(text)
        return {
            "enabled": True,
            "available": False,
            "detected": detected,
            "label": "heuristic",
            "score": score,
            "error": str(exc),
        }


def check_prompt(text: str) -> bool:
    """Returns True when the text is classified as a jailbreak attempt."""
    return bool(classify_jailbreak_text(text).get("detected"))


__all__ = ["classify_jailbreak_text", "check_prompt"]
