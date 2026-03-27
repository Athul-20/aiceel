from __future__ import annotations

import hashlib
import json
from typing import Any, Callable

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.models import IdempotencyKeyRecord


def _hash_payload(payload: dict | list | None) -> str:
    if payload is None:
        normalized = ""
    else:
        normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def run_idempotent(
    *,
    db: Session,
    request: Request,
    workspace_id: int,
    user_id: int,
    payload: dict | list | None,
    execute: Callable[[], Any],
) -> Any:
    key = request.headers.get("Idempotency-Key")
    if not key:
        return execute()

    key = key.strip()
    if not key:
        return execute()

    request_hash = _hash_payload(payload)
    method = request.method.upper()
    path = request.url.path

    existing = (
        db.query(IdempotencyKeyRecord)
        .filter(
            IdempotencyKeyRecord.workspace_id == workspace_id,
            IdempotencyKeyRecord.idempotency_key == key,
            IdempotencyKeyRecord.method == method,
            IdempotencyKeyRecord.path == path,
        )
        .first()
    )
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Idempotency key reuse with different payload is not allowed",
            )
        try:
            return json.loads(existing.response_json)
        except Exception:
            return {}

    result = execute()

    if hasattr(result, "model_dump"):
        response_obj = result.model_dump()
    elif isinstance(result, (dict, list)):
        response_obj = result
    else:
        response_obj = {"result": str(result)}

    row = IdempotencyKeyRecord(
        workspace_id=workspace_id,
        user_id=user_id,
        idempotency_key=key,
        method=method,
        path=path,
        request_hash=request_hash,
        status_code=200,
        response_json=json.dumps(response_obj, ensure_ascii=True),
    )
    db.add(row)
    db.commit()
    return result

