# aiccel/pipeline/middleware.py
"""
Middleware Pipeline System
===========================

Extensible middleware chain for cross-cutting concerns.
Inspired by Express.js, ASP.NET Core, and Django middleware.

Usage:
    pipeline = MiddlewarePipeline()
    pipeline.use(LoggingMiddleware())
    pipeline.use(ValidationMiddleware())
    pipeline.use(RateLimitMiddleware())

    result = await pipeline.execute(context)
"""

import asyncio
import time
from collections.abc import Awaitable
from typing import Any, Callable, Optional

from ..core.protocols import Context, Middleware
from ..logging_config import get_logger


logger = get_logger("pipeline")


# ============================================================================
# MIDDLEWARE PIPELINE
# ============================================================================

class MiddlewarePipeline:
    """
    Middleware execution pipeline.

    Middleware are executed in order for requests,
    and in reverse order for responses (like an onion).
    """

    def __init__(self):
        self._middleware: list[Middleware] = []
        self._final_handler: Optional[Callable[[Context], Awaitable[Context]]] = None

    def use(self, middleware: Middleware) -> 'MiddlewarePipeline':
        """Add middleware to the pipeline."""
        self._middleware.append(middleware)
        return self

    def set_handler(self, handler: Callable[[Context], Awaitable[Context]]) -> 'MiddlewarePipeline':
        """Set the final handler (the actual agent execution)."""
        self._final_handler = handler
        return self

    async def execute(self, context: Context) -> Context:
        """Execute the middleware pipeline."""

        async def final(ctx: Context) -> Context:
            if self._final_handler:
                return await self._final_handler(ctx)
            return ctx

        # Build the chain from the end
        chain = final
        for middleware in reversed(self._middleware):
            chain = self._wrap(middleware, chain)

        return await chain(context)

    def _wrap(
        self,
        middleware: Middleware,
        next_handler: Callable[[Context], Awaitable[Context]]
    ) -> Callable[[Context], Awaitable[Context]]:
        """Wrap middleware with next handler."""
        async def wrapped(context: Context) -> Context:
            return await middleware(context, next_handler)
        return wrapped


# ============================================================================
# BUILT-IN MIDDLEWARE
# ============================================================================

class LoggingMiddleware(Middleware):
    """Log request/response with timing."""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self._logger = get_logger("middleware.logging")

    async def __call__(
        self,
        context: Context,
        next_middleware: Callable[[Context], Awaitable[Context]]
    ) -> Context:
        start = time.perf_counter()

        query_preview = context.query[:50] + "..." if len(context.query) > 50 else context.query

        if self.verbose:
            self._logger.info(f"▶ Request: {query_preview}")

        try:
            context = await next_middleware(context)

            elapsed = (time.perf_counter() - start) * 1000

            if self.verbose:
                if context.response:
                    resp_preview = context.response.content[:50] + "..." if len(context.response.content) > 50 else context.response.content
                    self._logger.info(f"■ Response ({elapsed:.0f}ms): {resp_preview}")
                else:
                    self._logger.info(f"■ Completed ({elapsed:.0f}ms)")

            return context

        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            self._logger.error(f"✗ Error ({elapsed:.0f}ms): {str(e)[:100]}")
            context.error = e
            raise


class ValidationMiddleware(Middleware):
    """Validate input/output."""

    def __init__(
        self,
        max_query_length: int = 10000,
        max_response_length: int = 50000,
        blocked_patterns: Optional[list[str]] = None
    ):
        self.max_query_length = max_query_length
        self.max_response_length = max_response_length
        self.blocked_patterns = blocked_patterns or []
        self._logger = get_logger("middleware.validation")

    async def __call__(
        self,
        context: Context,
        next_middleware: Callable[[Context], Awaitable[Context]]
    ) -> Context:
        # Validate input
        if len(context.query) > self.max_query_length:
            raise ValueError(f"Query exceeds maximum length of {self.max_query_length}")

        # Check blocked patterns
        import re
        for pattern in self.blocked_patterns:
            if re.search(pattern, context.query, re.IGNORECASE):
                self._logger.warning(f"Blocked pattern detected: {pattern}")
                raise ValueError("Query contains blocked content")

        # Process
        context = await next_middleware(context)

        # Validate output
        if context.response and len(context.response.content) > self.max_response_length:
            self._logger.warning("Response truncated due to length")
            context.response.content = context.response.content[:self.max_response_length]

        return context


class RateLimitMiddleware(Middleware):
    """
    Token bucket rate limiter.

    Prevents API abuse and controls costs.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        tokens_per_request: int = 1,
        burst_size: int = 10
    ):
        self.rate = requests_per_minute / 60.0  # tokens per second
        self.burst_size = burst_size
        self.tokens = float(burst_size)
        self.last_update = time.time()
        self._lock = asyncio.Lock()
        self._logger = get_logger("middleware.ratelimit")

    async def __call__(
        self,
        context: Context,
        next_middleware: Callable[[Context], Awaitable[Context]]
    ) -> Context:
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(self.burst_size, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens < 1:
                wait_time = (1 - self.tokens) / self.rate
                self._logger.warning(f"Rate limit hit, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                self.tokens = 0
            else:
                self.tokens -= 1

        return await next_middleware(context)


class RetryMiddleware(Middleware):
    """
    Automatic retry with exponential backoff.
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        retry_exceptions: tuple = (Exception,)
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.retry_exceptions = retry_exceptions
        self._logger = get_logger("middleware.retry")

    async def __call__(
        self,
        context: Context,
        next_middleware: Callable[[Context], Awaitable[Context]]
    ) -> Context:
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return await next_middleware(context)
            except self.retry_exceptions as e:
                last_exception = e

                if attempt < self.max_retries:
                    delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                    self._logger.warning(f"Retry {attempt + 1}/{self.max_retries} in {delay:.1f}s: {str(e)[:50]}")
                    await asyncio.sleep(delay)

        raise last_exception


class CachingMiddleware(Middleware):
    """
    Response caching for identical queries.
    """

    def __init__(self, ttl_seconds: int = 300, max_size: int = 100):
        self.ttl = ttl_seconds
        self.max_size = max_size
        self._cache: dict[str, tuple] = {}  # query -> (response, timestamp)
        self._logger = get_logger("middleware.cache")

    def _cache_key(self, context: Context) -> str:
        """Generate cache key from context."""
        import hashlib
        key_data = context.query + str(sorted(context.metadata.items()))
        return hashlib.md5(key_data.encode()).hexdigest()

    async def __call__(
        self,
        context: Context,
        next_middleware: Callable[[Context], Awaitable[Context]]
    ) -> Context:
        key = self._cache_key(context)
        now = time.time()

        # Check cache
        if key in self._cache:
            response, timestamp = self._cache[key]
            if now - timestamp < self.ttl:
                self._logger.debug("Cache hit")
                context.response = response
                context.metadata["cache_hit"] = True
                return context

        # Execute
        context = await next_middleware(context)

        # Cache result
        if context.response and not context.error:
            if len(self._cache) >= self.max_size:
                # Evict oldest
                oldest = min(self._cache.items(), key=lambda x: x[1][1])
                del self._cache[oldest[0]]

            self._cache[key] = (context.response, now)

        return context


class MetricsMiddleware(Middleware):
    """
    Collect execution metrics.
    """

    def __init__(self):
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "total_duration_ms": 0.0,
            "tool_calls": 0,
        }
        self._lock = asyncio.Lock()
        self._logger = get_logger("middleware.metrics")

    async def __call__(
        self,
        context: Context,
        next_middleware: Callable[[Context], Awaitable[Context]]
    ) -> Context:
        start = time.perf_counter()

        async with self._lock:
            self.metrics["total_requests"] += 1

        try:
            context = await next_middleware(context)

            async with self._lock:
                self.metrics["successful_requests"] += 1
                self.metrics["total_duration_ms"] += (time.perf_counter() - start) * 1000
                if context.response:
                    self.metrics["tool_calls"] += len(context.response.tool_calls)

            return context

        except Exception:
            async with self._lock:
                self.metrics["failed_requests"] += 1
            raise

    def get_metrics(self) -> dict[str, Any]:
        """Get current metrics."""
        return {
            **self.metrics,
            "avg_duration_ms": (
                self.metrics["total_duration_ms"] / self.metrics["total_requests"]
                if self.metrics["total_requests"] > 0 else 0
            ),
            "success_rate": (
                self.metrics["successful_requests"] / self.metrics["total_requests"]
                if self.metrics["total_requests"] > 0 else 0
            )
        }


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def create_default_pipeline(
    verbose: bool = True,
    rate_limit: bool = True,
    cache: bool = False,
    metrics: bool = True
) -> MiddlewarePipeline:
    """Create a pipeline with sensible defaults."""
    pipeline = MiddlewarePipeline()

    if metrics:
        pipeline.use(MetricsMiddleware())

    if rate_limit:
        pipeline.use(RateLimitMiddleware())

    pipeline.use(RetryMiddleware(max_retries=2))
    pipeline.use(ValidationMiddleware())

    if cache:
        pipeline.use(CachingMiddleware())

    if verbose:
        pipeline.use(LoggingMiddleware(verbose=True))

    return pipeline
