from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import threading

try:
    import redis
except Exception:  # pragma: no cover - optional dependency at runtime
    redis = None

from app.config import get_settings


@dataclass
class RateLimitStatus:
    allowed: bool
    remaining: int
    reset_at: datetime


class MemoryLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[int, datetime]] = defaultdict(lambda: (0, datetime.now(timezone.utc)))

    def hit(self, key: str, limit: int, window_seconds: int = 60) -> RateLimitStatus:
        now = datetime.now(timezone.utc)
        with self._lock:
            count, reset_at = self._buckets[key]
            if now >= reset_at:
                count = 0
                reset_at = now + timedelta(seconds=window_seconds)
            count += 1
            self._buckets[key] = (count, reset_at)

        remaining = max(0, limit - count)
        return RateLimitStatus(allowed=count <= limit, remaining=remaining, reset_at=reset_at)


class RedisLimiter:
    def __init__(self, url: str) -> None:
        if redis is None:
            raise RuntimeError("redis package is not installed")
        self._client = redis.Redis.from_url(url)

    def hit(self, key: str, limit: int, window_seconds: int = 60) -> RateLimitStatus:
        bucket = f"ratelimit:{key}:{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}"
        value = self._client.incr(bucket)
        if value == 1:
            self._client.expire(bucket, window_seconds)
        ttl = self._client.ttl(bucket)
        reset_at = datetime.now(timezone.utc) + timedelta(seconds=max(ttl, 0))
        remaining = max(0, limit - int(value))
        return RateLimitStatus(allowed=int(value) <= limit, remaining=remaining, reset_at=reset_at)


_memory_limiter = MemoryLimiter()
_redis_limiter: RedisLimiter | None = None


def _get_limiter():
    global _redis_limiter
    settings = get_settings()
    if settings.redis_url and settings.redis_url.strip():
        if _redis_limiter is None:
            try:
                _redis_limiter = RedisLimiter(settings.redis_url)
            except Exception:
                _redis_limiter = None
        if _redis_limiter is not None:
            return _redis_limiter
    return _memory_limiter


def apply_rate_limit(key: str, limit: int, window_seconds: int = 60) -> RateLimitStatus:
    try:
        limiter = _get_limiter()
        return limiter.hit(key=key, limit=limit, window_seconds=window_seconds)
    except Exception as e:
        # Graceful fallback to memory limiter if redis hits a runtime snag
        logging.getLogger("app.rate_limit").error(f"Rate limiter failure: {e}. Falling back to memory.")
        return _memory_limiter.hit(key=key, limit=limit, window_seconds=window_seconds)

