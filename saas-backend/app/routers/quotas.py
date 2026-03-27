from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import assert_workspace_role, get_auth_context, get_user_from_api_key
from app.metering import get_workspace_limits, get_workspace_monthly_usage
from app.models import User
from app.schemas import QuotaStatusResponse


router = APIRouter(prefix="/v1/quotas", tags=["quotas"])


@router.get("/status", response_model=QuotaStatusResponse)
def get_quota_status(
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> QuotaStatusResponse:
    user, _ = user_auth
    assert_workspace_role(request, "viewer")
    context = get_auth_context(request)
    workspace = context.workspace if context and context.workspace else None
    if workspace is None and user.default_workspace_id is not None:
        class _Workspace:
            id = user.default_workspace_id
            plan_tier = "free"
        workspace = _Workspace()
    if workspace is None:
        return QuotaStatusResponse(
            workspace_id=0,
            near_limit=False,
            limit_units=0,
            used_units=0,
            remaining_units=0,
        )

    usage = get_workspace_monthly_usage(db, workspace.id)
    limit_units = int(get_workspace_limits(workspace)["monthly_units"])
    used_units = int(usage.unit_count)
    remaining_units = max(0, limit_units - used_units)
    return QuotaStatusResponse(
        workspace_id=workspace.id,
        near_limit=used_units >= int(limit_units * 0.8),
        limit_units=limit_units,
        used_units=used_units,
        remaining_units=remaining_units,
    )

