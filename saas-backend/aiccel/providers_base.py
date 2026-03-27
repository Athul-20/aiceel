# aiccel/providers_base.py
"""
Provider Base Classes
======================

Shared functionality for all LLM providers.
Follows Google's engineering patterns for production-grade code.
"""

import os
import threading
import zlib
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Optional, Union

import orjson
from cachetools import TTLCache
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .constants import Cache, Retries, Timeouts
from .exceptions import ProviderException
from .logger import create_logger


@dataclass
class ProviderConfig:
    """Configuration for LLM providers."""
    api_key: str
    model: str
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: float = 60.0
    max_retries: int = 3
    cache_ttl: int = 3600
    cache_size: int = 1000

    @classmethod
    def from_env(cls, prefix: str, model: str) -> 'ProviderConfig':
        """Create config from environment variables."""
        api_key = os.environ.get(f"{prefix}_API_KEY", "")
        return cls(api_key=api_key, model=model)


class BaseProvider(ABC):
    """
    Abstract base class for all LLM providers.

    Provides:
    - Instance-level response caching with TTL (thread-safe)
    - Automatic retry with exponential backoff
    - Rate limit handling
    - Structured logging
    - Environment variable support for API keys

    Subclasses must implement:
    - _generate_impl
    - _chat_impl
    - _generate_async_impl
    - _chat_async_impl
    """

    # Environment variable prefix for API key
    ENV_KEY_PREFIX: str = ""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        verbose: bool = False,
        log_file: Optional[str] = None,
        structured_logging: bool = False,
        cache_ttl: Optional[int] = None,
        cache_size: Optional[int] = None,
        **kwargs
    ):
        # Initialize logger
        self.logger = create_logger(
            name=self.__class__.__name__,
            verbose=verbose,
            log_file=log_file,
            structured_logging=structured_logging
        )

        # Get API key from env if not provided
        if not api_key and self.ENV_KEY_PREFIX:
            api_key = os.environ.get(f"{self.ENV_KEY_PREFIX}_API_KEY", "")

        if not api_key:
            raise ValueError(
                f"API key required. Provide api_key or set {self.ENV_KEY_PREFIX}_API_KEY environment variable."
            )

        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout if timeout is not None else Timeouts.DEFAULT_REQUEST
        self.max_retries = max_retries if max_retries is not None else Retries.DEFAULT_MAX_ATTEMPTS
        self.verbose = verbose

        # Instance-level cache (thread-safe)
        cache_ttl = cache_ttl if cache_ttl is not None else Cache.DEFAULT_TTL
        cache_size = cache_size if cache_size is not None else Cache.DEFAULT_MAX_SIZE
        self._response_cache = TTLCache(maxsize=cache_size, ttl=cache_ttl)
        self._cache_lock = threading.RLock()

        # Stats
        self._request_count = 0
        self._cache_hits = 0
        self._total_tokens = 0

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def generate(self, prompt: str, **kwargs) -> str:
        """Generate response from prompt (sync)."""
        cache_key = self._get_cache_key("generate", prompt, kwargs)

        # Check cache (thread-safe)
        cached = self._get_cached(cache_key)
        if cached is not None:
            self._cache_hits += 1
            return cached

        # Call implementation with retry
        try:
            response = self._generate_with_retry(prompt, **kwargs)
            self._cache_response(cache_key, response)
            self._request_count += 1
            return response
        except RetryError as e:
            raise ProviderException(
                f"Generation failed after {self.max_retries} retries",
                context={"provider": self.__class__.__name__, "error": str(e)}
            )

    async def generate_async(self, prompt: str, **kwargs) -> str:
        """Generate response from prompt (async)."""
        cache_key = self._get_cache_key("generate", prompt, kwargs)

        cached = self._get_cached(cache_key)
        if cached is not None:
            self._cache_hits += 1
            return cached

        try:
            response = await self._generate_async_with_retry(prompt, **kwargs)
            self._cache_response(cache_key, response)
            self._request_count += 1
            return response
        except RetryError as e:
            raise ProviderException(
                f"Async generation failed after {self.max_retries} retries",
                context={"provider": self.__class__.__name__, "error": str(e)}
            )

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Chat completion (sync)."""
        cache_key = self._get_cache_key("chat", messages, kwargs)

        cached = self._get_cached(cache_key)
        if cached is not None:
            self._cache_hits += 1
            return cached

        try:
            response = self._chat_with_retry(messages, **kwargs)
            self._cache_response(cache_key, response)
            self._request_count += 1
            return response
        except RetryError as e:
            raise ProviderException(
                f"Chat failed after {self.max_retries} retries",
                context={"provider": self.__class__.__name__, "error": str(e)}
            )

    async def chat_async(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Chat completion (async)."""
        cache_key = self._get_cache_key("chat", messages, kwargs)

        cached = self._get_cached(cache_key)
        if cached is not None:
            self._cache_hits += 1
            return cached

        try:
            response = await self._chat_async_with_retry(messages, **kwargs)
            self._cache_response(cache_key, response)
            self._request_count += 1
            return response
        except RetryError as e:
            raise ProviderException(
                f"Async chat failed after {self.max_retries} retries",
                context={"provider": self.__class__.__name__, "error": str(e)}
            )

    async def stream(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        """Stream response tokens."""
        async for chunk in self._stream_impl(prompt, **kwargs):
            yield chunk

    def embed(self, text: Union[str, list[str]]) -> Union[list[float], list[list[float]]]:
        """Generate embeddings."""
        return self._embed_impl(text)

    async def embed_async(self, text: Union[str, list[str]]) -> Union[list[float], list[list[float]]]:
        """Generate embeddings (async)."""
        return await self._embed_async_impl(text)

    # =========================================================================
    # ABSTRACT METHODS (subclasses implement)
    # =========================================================================

    @abstractmethod
    def _generate_impl(self, prompt: str, **kwargs) -> str:
        """Implementation of generate."""
        pass

    @abstractmethod
    async def _generate_async_impl(self, prompt: str, **kwargs) -> str:
        """Implementation of async generate."""
        pass

    @abstractmethod
    def _chat_impl(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Implementation of chat."""
        pass

    @abstractmethod
    async def _chat_async_impl(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Implementation of async chat."""
        pass

    def _embed_impl(self, text: Union[str, list[str]]) -> Union[list[float], list[list[float]]]:
        """Implementation of embed (optional)."""
        raise NotImplementedError("Embeddings not supported by this provider")

    async def _embed_async_impl(self, text: Union[str, list[str]]) -> Union[list[float], list[list[float]]]:
        """Implementation of async embed (optional)."""
        return self._embed_impl(text)  # Default: run sync

    async def _stream_impl(self, prompt: str, **kwargs) -> AsyncIterator[str]:
        """Implementation of streaming (optional)."""
        # Default: yield full response
        response = await self.generate_async(prompt, **kwargs)
        yield response

    # =========================================================================
    # RETRY WRAPPERS
    # =========================================================================

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError))
    )
    def _generate_with_retry(self, prompt: str, **kwargs) -> str:
        return self._generate_impl(prompt, **kwargs)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError))
    )
    async def _generate_async_with_retry(self, prompt: str, **kwargs) -> str:
        return await self._generate_async_impl(prompt, **kwargs)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError))
    )
    def _chat_with_retry(self, messages: list[dict[str, str]], **kwargs) -> str:
        return self._chat_impl(messages, **kwargs)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError))
    )
    async def _chat_async_with_retry(self, messages: list[dict[str, str]], **kwargs) -> str:
        return await self._chat_async_impl(messages, **kwargs)

    # =========================================================================
    # CACHING
    # =========================================================================

    def _get_cache_key(self, method: str, content: Any, kwargs: dict) -> str:
        """Generate cache key from method, content, and kwargs."""
        key_data = {
            "method": method,
            "model": self.model,
            "content": content,
            "kwargs": kwargs
        }
        serialized = orjson.dumps(key_data, option=orjson.OPT_SORT_KEYS)
        return str(zlib.crc32(serialized))

    def _get_cached(self, key: str) -> Optional[str]:
        """Get cached response if exists (thread-safe)."""
        with self._cache_lock:
            return self._response_cache.get(key)

    def _cache_response(self, key: str, response: str):
        """Cache a response (thread-safe)."""
        with self._cache_lock:
            self._response_cache[key] = response

    def clear_cache(self):
        """Clear the response cache (thread-safe)."""
        with self._cache_lock:
            self._response_cache.clear()

    # =========================================================================
    # RATE LIMIT HANDLING
    # =========================================================================

    def _handle_rate_limit(self, response, default_wait: float = 60.0) -> float:
        """
        Extract retry-after from rate limit response.
        Returns seconds to wait.
        """
        # Try to get retry-after header
        if hasattr(response, 'headers'):
            retry_after = response.headers.get('Retry-After')
            if retry_after:
                try:
                    return float(retry_after)
                except ValueError:
                    pass
        return default_wait

    def _is_rate_limited(self, response) -> bool:
        """Check if response indicates rate limiting."""
        if hasattr(response, 'status_code'):
            return response.status_code == 429
        return False

    # =========================================================================
    # STATS
    # =========================================================================

    def get_stats(self) -> dict[str, Any]:
        """Get provider statistics."""
        return {
            "model": self.model,
            "requests": self._request_count,
            "cache_hits": self._cache_hits,
            "cache_hit_rate": (
                self._cache_hits / self._request_count
                if self._request_count > 0 else 0
            ),
            "cache_size": len(self._response_cache)
        }

    # =========================================================================
    # CONTEXT MANAGER
    # =========================================================================

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(model='{self.model}')>"
