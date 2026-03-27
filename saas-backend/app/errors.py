"""Shared HTTP error helpers used across routers."""

from __future__ import annotations

from fastapi import HTTPException


def provider_error_to_http(exc: RuntimeError) -> HTTPException:
    """Convert a provider RuntimeError into an appropriate HTTPException.

    This centralises the error-mapping logic previously duplicated in
    ``routers/engine.py`` and ``routers/playground.py``.
    """
    message = str(exc)
    lowered = message.lower()
    if (
        "http 400" in lowered
        or "http 401" in lowered
        or "http 403" in lowered
        or "invalid" in lowered
        or "unauthorized" in lowered
        or "forbidden" in lowered
    ):
        return HTTPException(
            status_code=400,
            detail=(
                "Provider rejected the request. Verify provider key, model name, account access, "
                f"and region/network policy. Raw provider error: {message}"
            ),
        )
    if "timed out" in lowered or "urlopen error" in lowered or "temporary failure" in lowered:
        return HTTPException(
            status_code=502,
            detail=f"Provider network call failed. Verify outbound internet from backend host. Raw: {message}",
        )
    return HTTPException(status_code=502, detail=message)
