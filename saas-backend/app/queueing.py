from __future__ import annotations

from typing import Callable
import uuid

try:
    import redis
    from rq import Queue
except Exception:  # pragma: no cover
    redis = None
    Queue = None

from app.config import get_settings


def enqueue_job(func: Callable, *args, **kwargs) -> bool:
    settings = get_settings()
    if not settings.redis_url or redis is None or Queue is None:
        func(*args, **kwargs)
        return False

    try:
        conn = redis.Redis.from_url(settings.redis_url)
        queue = Queue(settings.queue_name, connection=conn)
        queue.enqueue(func, *args, **kwargs, job_timeout=settings.queue_job_timeout_seconds)
        return True
    except Exception:
        func(*args, **kwargs)
        return False


def enqueue_job_with_id(func: Callable, *args, **kwargs) -> tuple[str, bool]:
    settings = get_settings()
    job_id = f"job_{uuid.uuid4().hex[:24]}"
    if not settings.redis_url or redis is None or Queue is None:
        func(*args, **kwargs)
        return job_id, False

    try:
        conn = redis.Redis.from_url(settings.redis_url)
        queue = Queue(settings.queue_name, connection=conn)
        queue.enqueue(func, *args, **kwargs, job_id=job_id, job_timeout=settings.queue_job_timeout_seconds)
        return job_id, True
    except Exception:
        func(*args, **kwargs)
        return job_id, False


def enqueue_job_by_id(job_id: str, func: Callable, *args, **kwargs) -> bool:
    settings = get_settings()
    if not settings.redis_url or redis is None or Queue is None:
        func(*args, **kwargs)
        return False

    try:
        conn = redis.Redis.from_url(settings.redis_url)
        queue = Queue(settings.queue_name, connection=conn)
        queue.enqueue(func, *args, **kwargs, job_id=job_id, job_timeout=settings.queue_job_timeout_seconds)
        return True
    except Exception:
        func(*args, **kwargs)
        return False
