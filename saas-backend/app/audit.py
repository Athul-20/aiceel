from __future__ import annotations

import json

from fastapi import Request
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import AuditLog


def _safe_ip(request: Request | None) -> str | None:
    if request is None or request.client is None:
        return None
    return request.client.host


def _safe_user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    ua = request.headers.get("user-agent")
    if not ua:
        return None
    return ua[:250]


def log_audit(
    db: Session,
    action: str,
    workspace_id: int | None = None,
    user_id: int | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    request: Request | None = None,
    metadata: dict | None = None,
) -> None:
    request_id = getattr(request.state, "request_id", None) if request is not None else None
    row = AuditLog(
        workspace_id=workspace_id,
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        ip_address=_safe_ip(request),
        user_agent=_safe_user_agent(request),
        request_id=request_id,
        metadata_json=json.dumps(metadata or {}, ensure_ascii=True),
    )
    try:
        db.add(row)
        db.commit()
    except OperationalError:
        db.rollback()
