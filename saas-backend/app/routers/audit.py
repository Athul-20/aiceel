from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import assert_workspace_role, get_auth_context, get_user_from_api_key
from app.metering import parse_event_metadata
from app.models import AuditLog, User
from app.schemas import AuditLogOut


router = APIRouter(prefix="/v1/audit", tags=["audit"])


@router.get("/logs", response_model=list[AuditLogOut])
def list_audit_logs(
    request: Request,
    response: Response,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100000),
    action: str | None = Query(default=None, min_length=2, max_length=120),
    target_type: str | None = Query(default=None, min_length=2, max_length=120),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> list[AuditLogOut]:
    user, _ = user_auth
    assert_workspace_role(request, "admin")
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else user.default_workspace_id
    if workspace_id is None:
        return []

    query = db.query(AuditLog).filter(AuditLog.workspace_id == workspace_id)
    if action:
        query = query.filter(AuditLog.action.ilike(f"%{action.strip()}%"))
    if target_type:
        query = query.filter(AuditLog.target_type == target_type.strip())

    total = query.count()
    response.headers["X-Total-Count"] = str(total)
    query = query.order_by(AuditLog.created_at.asc() if order == "asc" else AuditLog.created_at.desc())
    rows = query.offset(offset).limit(limit).all()
    return [
        AuditLogOut(
            id=row.id,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            request_id=row.request_id,
            ip_address=row.ip_address,
            created_at=row.created_at,
            metadata=parse_event_metadata(row.metadata_json),
        )
        for row in rows
    ]

