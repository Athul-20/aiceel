# aiccel/tracing.py
"""
Tracing functionality for AICCL framework.
Provides distributed tracing capabilities similar to LangTrace.
"""

from typing import Any

import requests


# Global tracing configuration
_tracing_config = {
    "api_key": None,
    "backend_url": "http://localhost:8000",
    "enabled": False
}


def init_tracing(api_key: str, backend_url: str = "http://localhost:8000") -> None:
    """
    Initialize tracing for AICCL framework.

    Args:
        api_key: API key for tracing backend
        backend_url: URL of tracing backend

    Raises:
        ValueError: If API key validation fails

    Example:
        >>> from aiccel import init_tracing
        >>> init_tracing(api_key="your-api-key", backend_url="https://trace.example.com")
    """
    global _tracing_config

    _tracing_config["api_key"] = api_key
    _tracing_config["backend_url"] = backend_url

    # Validate API key
    try:
        response = requests.get(
            f"{backend_url}/api/validate/{api_key}",
            timeout=5
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("valid"):
            raise ValueError("Invalid API key")

        _tracing_config["enabled"] = True

    except requests.exceptions.RequestException as e:
        raise ValueError(f"Failed to connect to tracing backend: {e!s}")
    except Exception as e:
        raise ValueError(f"Failed to validate API key: {e!s}")


def get_tracing_config() -> dict[str, Any]:
    """Get current tracing configuration"""
    return _tracing_config.copy()


def disable_tracing() -> None:
    """Disable tracing"""
    global _tracing_config
    _tracing_config["enabled"] = False


def enable_tracing() -> None:
    """Enable tracing (if previously initialized)"""
    global _tracing_config
    if _tracing_config["api_key"]:
        _tracing_config["enabled"] = True
    else:
        raise ValueError("Tracing not initialized. Call init_tracing() first.")
