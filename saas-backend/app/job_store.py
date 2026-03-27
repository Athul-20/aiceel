from __future__ import annotations

from datetime import datetime, timezone
import threading


_lock = threading.Lock()
_jobs: dict[str, dict] = {}


def set_job(job_id: str, payload: dict) -> None:
    with _lock:
        _jobs[job_id] = payload


def get_job(job_id: str) -> dict | None:
    with _lock:
        return _jobs.get(job_id)


def init_job(job_id: str, status: str = "queued") -> None:
    set_job(
        job_id,
        {
            "job_id": job_id,
            "status": status,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "result": None,
            "error": None,
        },
    )


def complete_job(job_id: str, result: dict) -> None:
    payload = get_job(job_id) or {"job_id": job_id, "created_at": datetime.now(timezone.utc).isoformat()}
    payload["status"] = "completed"
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload["result"] = result
    payload["error"] = None
    set_job(job_id, payload)


def fail_job(job_id: str, error: str) -> None:
    payload = get_job(job_id) or {"job_id": job_id, "created_at": datetime.now(timezone.utc).isoformat()}
    payload["status"] = "failed"
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload["error"] = error
    set_job(job_id, payload)

