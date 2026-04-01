from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import assert_workspace_role, get_auth_context, get_user_from_api_key
from app.metering import get_workspace_limits, get_workspace_monthly_usage, usage_to_dict
from app.models import MeterEvent, User
from app.schemas import UsageEventOut, UsageSummaryResponse


router = APIRouter(prefix="/v1/usage", tags=["usage"])


def _usage_query(
    db: Session,
    *,
    workspace_id: int,
    feature: str | None = None,
    status_filter: str | None = None,
    source: str = "all",
    api_key_id: int | None = None,
):
    query = db.query(MeterEvent).filter(MeterEvent.workspace_id == workspace_id)
    if feature:
        query = query.filter(MeterEvent.feature.ilike(f"%{feature.strip()}%"))
    if status_filter:
        query = query.filter(MeterEvent.status == status_filter.strip().lower())
    if source == "api":
        query = query.filter(MeterEvent.api_key_id.is_not(None))
    elif source == "workspace":
        query = query.filter(MeterEvent.api_key_id.is_(None))
    if api_key_id is not None:
        query = query.filter(MeterEvent.api_key_id == api_key_id)
    return query


@router.get("/summary", response_model=UsageSummaryResponse)
def get_usage_summary(
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
    source: str = Query(default="all", pattern="^(all|workspace|api)$"),
    api_key_id: int | None = Query(default=None, ge=1),
) -> UsageSummaryResponse:
    user, _ = user_auth
    assert_workspace_role(request, "viewer")
    context = get_auth_context(request)
    workspace = context.workspace if context else None
    if workspace is None:
        workspace_id = user.default_workspace_id
        if workspace_id is None:
            return UsageSummaryResponse(workspace_id=0, plan_tier="free", limits={}, usage={})
        # Minimal fallback; context should exist in API-key mode.
        class _Workspace:
            id = workspace_id
            plan_tier = "free"
        workspace = _Workspace()

    limits = get_workspace_limits(workspace)
    if source == "all" and api_key_id is None:
        usage = get_workspace_monthly_usage(db, workspace.id)
        usage_dict = usage_to_dict(usage)
    else:
        base_query = _usage_query(
            db,
            workspace_id=workspace.id,
            source=source,
            api_key_id=api_key_id,
        )
        month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        request_count, token_count, runtime_ms, unit_count = (
            base_query.filter(MeterEvent.created_at >= month_start).with_entities(
                func.count(MeterEvent.id),
                func.coalesce(func.sum(MeterEvent.tokens), 0),
                func.coalesce(func.sum(MeterEvent.runtime_ms), 0),
                func.coalesce(func.sum(MeterEvent.units), 0),
            ).one()
        )
        usage_dict = {
            "period_start": get_workspace_monthly_usage(db, workspace.id).period_start.isoformat(),
            "period_type": "month",
            "request_count": int(request_count or 0),
            "token_count": int(token_count or 0),
            "runtime_ms": int(runtime_ms or 0),
            "unit_count": int(unit_count or 0),
        }
    return UsageSummaryResponse(
        workspace_id=workspace.id,
        plan_tier=workspace.plan_tier,
        limits=limits,
        usage=usage_dict,
    )


@router.get("/events", response_model=list[UsageEventOut])
def list_usage_events(
    request: Request,
    response: Response,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100000),
    feature: str | None = Query(default=None, min_length=1, max_length=120),
    status_filter: str | None = Query(default=None, alias="status", min_length=1, max_length=20),
    source: str = Query(default="all", pattern="^(all|workspace|api)$"),
    api_key_id: int | None = Query(default=None, ge=1),
    sort: str = Query(default="created_at", pattern="^(created_at|units|tokens|runtime_ms)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> list[UsageEventOut]:
    user, _ = user_auth
    assert_workspace_role(request, "viewer")
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else user.default_workspace_id
    if workspace_id is None:
        return []

    query = _usage_query(
        db,
        workspace_id=workspace_id,
        feature=feature,
        status_filter=status_filter,
        source=source,
        api_key_id=api_key_id,
    )

    total = query.count()
    response.headers["X-Total-Count"] = str(total)

    sort_column = {
        "created_at": MeterEvent.created_at,
        "units": MeterEvent.units,
        "tokens": MeterEvent.tokens,
        "runtime_ms": MeterEvent.runtime_ms,
    }[sort]
    query = query.order_by(sort_column.asc() if order == "asc" else sort_column.desc())
    rows = query.offset(offset).limit(limit).all()
    return [
        UsageEventOut(
            id=row.id,
            feature=row.feature,
            units=row.units,
            tokens=row.tokens,
            runtime_ms=row.runtime_ms,
            status=row.status,
            api_key_id=row.api_key_id,
            request_id=row.request_id,
            created_at=row.created_at,
        )
        for row in rows
    ]

