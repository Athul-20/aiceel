# aiccel/providers/base.py
"""
Base LLM Provider Implementation
================================

Defines the base LLMProvider class with connection pooling and shared logic.
"""

import threading
from typing import Optional

import requests

from ..constants import HTTP
from ..providers_base import BaseProvider


class LLMProvider(BaseProvider):
    """
    Base class for LLM providers with connection pooling.

    Features:
    - Connection pooling for HTTP requests (reuses connections)
    - Request ID tracking for observability
    - Proper exception handling

    The LLMProvider interface provides:
    - generate(prompt): Simple text completion
    - chat(messages): Multi-turn conversation
    - embed(text): Text embeddings
    - Async variants: generate_async, chat_async, embed_async
    """

    # Shared session for sync requests (thread-safe with connection pooling)
    _sync_session: Optional[requests.Session] = None
    _sync_session_lock = threading.Lock()

    @classmethod
    def _get_sync_session(cls) -> requests.Session:
        """Get or create the shared sync HTTP session with connection pooling."""
        if cls._sync_session is None:
            with cls._sync_session_lock:
                if cls._sync_session is None:
                    session = requests.Session()
                    # Connection pooling settings
                    adapter = requests.adapters.HTTPAdapter(
                        pool_connections=HTTP.POOL_CONNECTIONS,
                        pool_maxsize=HTTP.POOL_MAXSIZE,
                        max_retries=0  # We handle retries at the provider level
                    )
                    session.mount('https://', adapter)
                    session.mount('http://', adapter)
                    cls._sync_session = session
        return cls._sync_session
