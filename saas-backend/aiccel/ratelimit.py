# aiccel/ratelimit.py
"""
Enterprise Rate Limiting
========================

Production-grade rate limiting with multiple strategies:
- Token bucket (burst-friendly)
- Sliding window (precise)
- Per-user/per-key limiting
- Distributed support (Redis-compatible interface)

Usage:
    from aiccel.ratelimit import RateLimiter, SlidingWindowLimiter

    # Simple usage
    limiter = RateLimiter(requests_per_minute=60)
    if limiter.allow("user_123"):
        process_request()
    else:
        raise RateLimitExceeded()

    # As middleware
    from aiccel.ratelimit import RateLimitMiddleware
    pipeline.use(RateLimitMiddleware(limiter))
"""

import asyncio
import hashlib
import time
from collections import deque
from collections.abc import Awaitable
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Optional, Protocol

from .exceptions import AICCLException
from .logging_config import get_logger


logger = get_logger("ratelimit")


# ============================================================================
# EXCEPTIONS
# ============================================================================

class RateLimitExceeded(AICCLException):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[float] = None,
        limit: Optional[int] = None,
        remaining: int = 0,
        reset_at: Optional[float] = None
    ):
        context = {
            "retry_after": retry_after,
            "limit": limit,
            "remaining": remaining,
            "reset_at": reset_at
        }
        super().__init__(message, context)
        self.retry_after = retry_after
        self.limit = limit
        self.remaining = remaining
        self.reset_at = reset_at


# ============================================================================
# RATE LIMITER PROTOCOL
# ============================================================================

class RateLimiterProtocol(Protocol):
    """Protocol for rate limiters."""

    def allow(self, key: str = "default") -> bool:
        """Check if request is allowed."""
        ...

    async def allow_async(self, key: str = "default") -> bool:
        """Async check if request is allowed."""
        ...

    def get_status(self, key: str = "default") -> dict[str, Any]:
        """Get current rate limit status."""
        ...


# ============================================================================
# TOKEN BUCKET RATE LIMITER
# ============================================================================

@dataclass
class TokenBucket:
    """Token bucket for a single key."""
    tokens: float
    last_update: float
    rate: float
    capacity: float

    def refill(self) -> float:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now
        return self.tokens


class TokenBucketLimiter:
    """
    Token bucket rate limiter.

    Best for: APIs with burst traffic patterns.
    Allows short bursts while maintaining average rate.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        burst_size: Optional[int] = None,
        per_key: bool = True
    ):
        """
        Initialize token bucket limiter.

        Args:
            requests_per_minute: Sustained request rate
            burst_size: Maximum burst (defaults to requests_per_minute / 6)
            per_key: Enable per-key limiting (user/API key)
        """
        self.rate = requests_per_minute / 60.0  # tokens per second
        self.capacity = burst_size or max(10, requests_per_minute // 6)
        self.per_key = per_key
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = asyncio.Lock()
        self._sync_lock = __import__('threading').Lock()

    def _get_bucket(self, key: str) -> TokenBucket:
        """Get or create bucket for key."""
        if key not in self._buckets:
            self._buckets[key] = TokenBucket(
                tokens=self.capacity,
                last_update=time.time(),
                rate=self.rate,
                capacity=self.capacity
            )
        return self._buckets[key]

    def allow(self, key: str = "default") -> bool:
        """Check if request is allowed (sync)."""
        if not self.per_key:
            key = "default"

        with self._sync_lock:
            bucket = self._get_bucket(key)
            bucket.refill()

            if bucket.tokens >= 1:
                bucket.tokens -= 1
                return True
            return False

    async def allow_async(self, key: str = "default") -> bool:
        """Check if request is allowed (async)."""
        if not self.per_key:
            key = "default"

        async with self._lock:
            bucket = self._get_bucket(key)
            bucket.refill()

            if bucket.tokens >= 1:
                bucket.tokens -= 1
                return True
            return False

    def get_status(self, key: str = "default") -> dict[str, Any]:
        """Get current rate limit status."""
        if not self.per_key:
            key = "default"

        bucket = self._get_bucket(key)
        bucket.refill()

        return {
            "allowed": bucket.tokens >= 1,
            "remaining": int(bucket.tokens),
            "limit": int(self.capacity),
            "reset_in_seconds": (self.capacity - bucket.tokens) / self.rate if bucket.tokens < self.capacity else 0,
            "retry_after": max(0, (1 - bucket.tokens) / self.rate) if bucket.tokens < 1 else 0
        }

    def wait_time(self, key: str = "default") -> float:
        """Get time to wait before next request is allowed."""
        status = self.get_status(key)
        return status["retry_after"]


# ============================================================================
# SLIDING WINDOW RATE LIMITER
# ============================================================================

@dataclass
class SlidingWindow:
    """Sliding window for a single key."""
    timestamps: deque = field(default_factory=deque)
    window_size: float = 60.0
    max_requests: int = 60


class SlidingWindowLimiter:
    """
    Sliding window rate limiter.

    Best for: Precise rate limiting, compliance requirements.
    More accurate than token bucket but slightly more memory.
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        window_seconds: float = 60.0,
        per_key: bool = True
    ):
        """
        Initialize sliding window limiter.

        Args:
            requests_per_minute: Maximum requests in window
            window_seconds: Window size in seconds
            per_key: Enable per-key limiting
        """
        self.max_requests = requests_per_minute
        self.window_size = window_seconds
        self.per_key = per_key
        self._windows: dict[str, SlidingWindow] = {}
        self._lock = asyncio.Lock()
        self._sync_lock = __import__('threading').Lock()

    def _get_window(self, key: str) -> SlidingWindow:
        """Get or create window for key."""
        if key not in self._windows:
            self._windows[key] = SlidingWindow(
                timestamps=deque(),
                window_size=self.window_size,
                max_requests=self.max_requests
            )
        return self._windows[key]

    def _cleanup_window(self, window: SlidingWindow) -> None:
        """Remove expired timestamps."""
        now = time.time()
        cutoff = now - window.window_size
        while window.timestamps and window.timestamps[0] < cutoff:
            window.timestamps.popleft()

    def allow(self, key: str = "default") -> bool:
        """Check if request is allowed (sync)."""
        if not self.per_key:
            key = "default"

        with self._sync_lock:
            window = self._get_window(key)
            self._cleanup_window(window)

            if len(window.timestamps) < self.max_requests:
                window.timestamps.append(time.time())
                return True
            return False

    async def allow_async(self, key: str = "default") -> bool:
        """Check if request is allowed (async)."""
        if not self.per_key:
            key = "default"

        async with self._lock:
            window = self._get_window(key)
            self._cleanup_window(window)

            if len(window.timestamps) < self.max_requests:
                window.timestamps.append(time.time())
                return True
            return False

    def get_status(self, key: str = "default") -> dict[str, Any]:
        """Get current rate limit status."""
        if not self.per_key:
            key = "default"

        window = self._get_window(key)
        self._cleanup_window(window)

        remaining = max(0, self.max_requests - len(window.timestamps))
        oldest = window.timestamps[0] if window.timestamps else time.time()
        reset_at = oldest + self.window_size

        return {
            "allowed": remaining > 0,
            "remaining": remaining,
            "limit": self.max_requests,
            "reset_at": reset_at,
            "retry_after": max(0, reset_at - time.time()) if remaining == 0 else 0
        }


# ============================================================================
# ADAPTIVE RATE LIMITER
# ============================================================================

class AdaptiveRateLimiter:
    """
    Adaptive rate limiter that adjusts based on system load.

    Best for: Auto-scaling systems, variable load patterns.
    """

    def __init__(
        self,
        base_requests_per_minute: int = 60,
        min_rate: float = 0.1,
        max_rate: float = 2.0,
        adaptation_window: float = 60.0,
        per_key: bool = True
    ):
        """
        Initialize adaptive limiter.

        Args:
            base_requests_per_minute: Base rate
            min_rate: Minimum multiplier (0.1 = 10% of base)
            max_rate: Maximum multiplier (2.0 = 200% of base)
            adaptation_window: Window for measuring success rate
            per_key: Enable per-key limiting
        """
        self.base_rate = base_requests_per_minute
        self.min_multiplier = min_rate
        self.max_multiplier = max_rate
        self.adaptation_window = adaptation_window
        self.per_key = per_key

        self._current_multiplier = 1.0
        self._success_count = 0
        self._failure_count = 0
        self._last_adaptation = time.time()
        self._inner_limiter = TokenBucketLimiter(
            requests_per_minute=base_requests_per_minute,
            per_key=per_key
        )
        self._lock = asyncio.Lock()

    def _adapt_rate(self) -> None:
        """Adjust rate based on success/failure ratio."""
        now = time.time()
        if now - self._last_adaptation < self.adaptation_window:
            return

        total = self._success_count + self._failure_count
        if total > 0:
            success_rate = self._success_count / total

            # Increase rate if high success, decrease if low
            if success_rate > 0.95:
                self._current_multiplier = min(
                    self.max_multiplier,
                    self._current_multiplier * 1.1
                )
            elif success_rate < 0.8:
                self._current_multiplier = max(
                    self.min_multiplier,
                    self._current_multiplier * 0.8
                )

            # Update inner limiter
            new_rate = int(self.base_rate * self._current_multiplier)
            self._inner_limiter.rate = new_rate / 60.0

        self._success_count = 0
        self._failure_count = 0
        self._last_adaptation = now

    def allow(self, key: str = "default") -> bool:
        """Check if request is allowed."""
        self._adapt_rate()
        return self._inner_limiter.allow(key)

    async def allow_async(self, key: str = "default") -> bool:
        """Async check if request is allowed."""
        async with self._lock:
            self._adapt_rate()
        return await self._inner_limiter.allow_async(key)

    def record_success(self) -> None:
        """Record successful request (for adaptation)."""
        self._success_count += 1

    def record_failure(self) -> None:
        """Record failed request (for adaptation)."""
        self._failure_count += 1

    def get_status(self, key: str = "default") -> dict[str, Any]:
        """Get current status."""
        status = self._inner_limiter.get_status(key)
        status["current_multiplier"] = self._current_multiplier
        status["effective_rate"] = int(self.base_rate * self._current_multiplier)
        return status


# ============================================================================
# DISTRIBUTED RATE LIMITER (Redis-compatible)
# ============================================================================

class DistributedRateLimiter:
    """
    Distributed rate limiter using Redis-compatible backend.

    Best for: Multi-instance deployments, microservices.
    """

    def __init__(
        self,
        backend: Any,  # Redis client or compatible
        key_prefix: str = "ratelimit:",
        requests_per_minute: int = 60,
        window_seconds: float = 60.0
    ):
        """
        Initialize distributed limiter.

        Args:
            backend: Redis client (or compatible with get/set/incr/expire)
            key_prefix: Prefix for Redis keys
            requests_per_minute: Max requests per window
            window_seconds: Window size
        """
        self.backend = backend
        self.key_prefix = key_prefix
        self.max_requests = requests_per_minute
        self.window_size = int(window_seconds)

    def _make_key(self, key: str) -> str:
        """Generate Redis key."""
        window_id = int(time.time() // self.window_size)
        return f"{self.key_prefix}{key}:{window_id}"

    def allow(self, key: str = "default") -> bool:
        """Check if request is allowed using Redis."""
        redis_key = self._make_key(key)

        try:
            # Atomic increment
            current = self.backend.incr(redis_key)

            # Set expiry on first request
            if current == 1:
                self.backend.expire(redis_key, self.window_size + 1)

            return current <= self.max_requests
        except Exception as e:
            logger.warning(f"Redis rate limit check failed: {e}, allowing request")
            return True  # Fail open

    async def allow_async(self, key: str = "default") -> bool:
        """Async check using Redis."""
        # For async Redis clients
        redis_key = self._make_key(key)

        try:
            if hasattr(self.backend, 'incr'):
                # Async Redis client
                current = await self.backend.incr(redis_key)
                if current == 1:
                    await self.backend.expire(redis_key, self.window_size + 1)
                return current <= self.max_requests
            else:
                # Fallback to sync
                return self.allow(key)
        except Exception as e:
            logger.warning(f"Async Redis rate limit check failed: {e}")
            return True

    def get_status(self, key: str = "default") -> dict[str, Any]:
        """Get current status from Redis."""
        redis_key = self._make_key(key)

        try:
            current = int(self.backend.get(redis_key) or 0)
            ttl = self.backend.ttl(redis_key)

            return {
                "allowed": current < self.max_requests,
                "remaining": max(0, self.max_requests - current),
                "limit": self.max_requests,
                "reset_in_seconds": max(0, ttl) if ttl > 0 else self.window_size
            }
        except Exception:
            return {
                "allowed": True,
                "remaining": self.max_requests,
                "limit": self.max_requests,
                "reset_in_seconds": self.window_size
            }


# ============================================================================
# RATE LIMIT MIDDLEWARE
# ============================================================================

class EnterpriseRateLimitMiddleware:
    """
    Enterprise-grade rate limiting middleware.

    Features:
    - Multiple limiter support (global + per-user)
    - Configurable key extraction
    - Rate limit headers
    - Graceful degradation
    """

    def __init__(
        self,
        limiter: RateLimiterProtocol,
        key_func: Optional[Callable[[Any], str]] = None,
        on_limited: Optional[Callable[[Any], Awaitable[Any]]] = None,
        include_headers: bool = True,
        fail_open: bool = True
    ):
        """
        Initialize middleware.

        Args:
            limiter: Rate limiter instance
            key_func: Function to extract key from context (default: use context.user_id or "default")
            on_limited: Callback when rate limited (default: raise RateLimitExceeded)
            include_headers: Add rate limit headers to response
            fail_open: Allow requests if limiter fails
        """
        self.limiter = limiter
        self.key_func = key_func or self._default_key_func
        self.on_limited = on_limited
        self.include_headers = include_headers
        self.fail_open = fail_open
        self._logger = get_logger("middleware.ratelimit")

    def _default_key_func(self, context: Any) -> str:
        """Default key extraction."""
        if hasattr(context, 'user_id') and context.user_id:
            return str(context.user_id)
        if hasattr(context, 'metadata') and context.metadata.get('user_id'):
            return str(context.metadata['user_id'])
        if hasattr(context, 'metadata') and context.metadata.get('api_key'):
            # Hash API key for privacy
            return hashlib.sha256(context.metadata['api_key'].encode()).hexdigest()[:16]
        return "default"

    async def __call__(
        self,
        context: Any,
        next_middleware: Callable[[Any], Awaitable[Any]]
    ) -> Any:
        """Execute rate limiting."""
        key = self.key_func(context)

        try:
            allowed = await self.limiter.allow_async(key)
        except Exception as e:
            self._logger.error(f"Rate limiter error: {e}")
            if self.fail_open:
                allowed = True
            else:
                raise

        if not allowed:
            status = self.limiter.get_status(key)
            self._logger.warning(f"Rate limit exceeded for key: {key[:8]}...")

            if self.on_limited:
                return await self.on_limited(context)

            raise RateLimitExceeded(
                retry_after=status.get("retry_after"),
                limit=status.get("limit"),
                remaining=status.get("remaining", 0),
                reset_at=status.get("reset_at")
            )

        # Execute request
        result = await next_middleware(context)

        # Add rate limit headers to response metadata
        if self.include_headers and hasattr(context, 'metadata'):
            status = self.limiter.get_status(key)
            context.metadata['ratelimit_limit'] = status.get('limit')
            context.metadata['ratelimit_remaining'] = status.get('remaining')
            context.metadata['ratelimit_reset'] = status.get('reset_at') or status.get('reset_in_seconds')

        return result


# ============================================================================
# DECORATORS
# ============================================================================

def rate_limit(
    requests_per_minute: int = 60,
    per_key: bool = False,
    key_arg: Optional[str] = None,
    limiter: Optional[RateLimiterProtocol] = None
):
    """
    Decorator for rate limiting functions.

    Usage:
        @rate_limit(requests_per_minute=10)
        def my_api_call():
            ...

        @rate_limit(requests_per_minute=100, per_key=True, key_arg="user_id")
        def user_action(user_id: str):
            ...
    """
    _limiter = limiter or TokenBucketLimiter(
        requests_per_minute=requests_per_minute,
        per_key=per_key
    )

    def decorator(func):
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            key = "default"
            if per_key and key_arg:
                key = str(kwargs.get(key_arg, args[0] if args else "default"))

            if not _limiter.allow(key):
                status = _limiter.get_status(key)
                raise RateLimitExceeded(
                    retry_after=status.get("retry_after"),
                    limit=status.get("limit")
                )

            return func(*args, **kwargs)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            key = "default"
            if per_key and key_arg:
                key = str(kwargs.get(key_arg, args[0] if args else "default"))

            if not await _limiter.allow_async(key):
                status = _limiter.get_status(key)
                raise RateLimitExceeded(
                    retry_after=status.get("retry_after"),
                    limit=status.get("limit")
                )

            return await func(*args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================

def create_rate_limiter(
    strategy: str = "token_bucket",
    requests_per_minute: int = 60,
    per_key: bool = True,
    **kwargs
) -> RateLimiterProtocol:
    """
    Create a rate limiter with the specified strategy.

    Args:
        strategy: "token_bucket", "sliding_window", or "adaptive"
        requests_per_minute: Request limit
        per_key: Enable per-key limiting
        **kwargs: Strategy-specific options

    Returns:
        Rate limiter instance
    """
    if strategy == "token_bucket":
        return TokenBucketLimiter(
            requests_per_minute=requests_per_minute,
            per_key=per_key,
            burst_size=kwargs.get("burst_size")
        )
    elif strategy == "sliding_window":
        return SlidingWindowLimiter(
            requests_per_minute=requests_per_minute,
            per_key=per_key,
            window_seconds=kwargs.get("window_seconds", 60.0)
        )
    elif strategy == "adaptive":
        return AdaptiveRateLimiter(
            base_requests_per_minute=requests_per_minute,
            per_key=per_key,
            min_rate=kwargs.get("min_rate", 0.1),
            max_rate=kwargs.get("max_rate", 2.0)
        )
    else:
        raise ValueError(f"Unknown strategy: {strategy}")


# Convenience alias
RateLimiter = TokenBucketLimiter
RateLimitMiddleware = EnterpriseRateLimitMiddleware


__all__ = [
    'AdaptiveRateLimiter',
    'DistributedRateLimiter',
    # Middleware
    'EnterpriseRateLimitMiddleware',
    # Exceptions
    'RateLimitExceeded',
    'RateLimitMiddleware',
    # Aliases
    'RateLimiter',
    'SlidingWindowLimiter',
    # Limiters
    'TokenBucketLimiter',
    # Factory
    'create_rate_limiter',
    # Decorators
    'rate_limit',
]
