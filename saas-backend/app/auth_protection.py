from __future__ import annotations

from datetime import datetime, timedelta, timezone
import threading

try:
    import redis
except Exception:  # pragma: no cover
    redis = None

from app.config import get_settings


class MemoryAttemptStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._values: dict[str, tuple[int, datetime]] = {}

    def increment(self, key: str, window_seconds: int) -> int:
        now = datetime.now(timezone.utc)
        with self._lock:
            count, expires = self._values.get(key, (0, now + timedelta(seconds=window_seconds)))
            if now >= expires:
                count = 0
                expires = now + timedelta(seconds=window_seconds)
            count += 1
            self._values[key] = (count, expires)
            return count

    def reset(self, key: str) -> None:
        with self._lock:
            self._values.pop(key, None)

    def get_count(self, key: str) -> int:
        now = datetime.now(timezone.utc)
        with self._lock:
            item = self._values.get(key)
            if not item:
                return 0
            count, expires = item
            if now >= expires:
                self._values.pop(key, None)
                return 0
            return count


_memory = MemoryAttemptStore()
_redis = None


def _get_redis():
    global _redis
    settings = get_settings()
    if not settings.redis_url or redis is None:
        return None
    if _redis is None:
        try:
            _redis = redis.Redis.from_url(settings.redis_url)
        except Exception:
            _redis = None
    return _redis


def _build_key(identifier: str, ip: str | None) -> str:
    ip_part = ip or "unknown"
    return f"auth:{identifier.lower()}:{ip_part}"


def register_failed_attempt(identifier: str, ip: str | None) -> int:
    settings = get_settings()
    key = _build_key(identifier, ip)
    client = _get_redis()
    if client is not None:
        value = client.incr(key)
        if int(value) == 1:
            client.expire(key, settings.auth_bruteforce_window_seconds)
        return int(value)
    return _memory.increment(key, settings.auth_bruteforce_window_seconds)


def clear_attempts(identifier: str, ip: str | None) -> None:
    key = _build_key(identifier, ip)
    client = _get_redis()
    if client is not None:
        client.delete(key)
    else:
        _memory.reset(key)


def check_blocked(identifier: str, ip: str | None) -> bool:
    settings = get_settings()
    key = _build_key(identifier, ip)
    client = _get_redis()
    if client is not None:
        value = client.get(key)
        return int(value or 0) >= settings.auth_bruteforce_limit
    attempts = _memory.get_count(key)
    return attempts >= settings.auth_bruteforce_limit
