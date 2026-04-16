from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import assert_workspace_role, get_auth_context, get_user_from_api_key
from app.metering import (
    aggregate_entity_counts,
    get_workspace_limits,
    parse_event_metadata,
)
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


def _period_bounds(month: int | None, year: int | None) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    target_month = month or now.month
    target_year = year or now.year
    period_start = datetime(target_year, target_month, 1, tzinfo=timezone.utc)
    if target_month == 12:
        period_end = datetime(target_year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        period_end = datetime(target_year, target_month + 1, 1, tzinfo=timezone.utc)
    return period_start, period_end


def _dedupe_usage_rows(rows: list[MeterEvent]) -> list[MeterEvent]:
    request_ids_with_feature = {
        row.request_id
        for row in rows
        if row.request_id and not str(row.feature or "").startswith("request:")
    }
    suppressed_request_paths = {
        "/v1/engine/security/process",
        "/v1/pii/mask",
        "/v1/sentinel/analyze",
    }
    return [
        row
        for row in rows
        if not (
            str(row.feature or "").startswith("request:")
            and (
                any(path in str(row.feature or "") for path in suppressed_request_paths)
                or (row.request_id and row.request_id in request_ids_with_feature)
            )
        )
    ]


@router.get("/summary", response_model=UsageSummaryResponse)
def get_usage_summary(
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
    source: str = Query(default="all", pattern="^(all|workspace|api)$"),
    api_key_id: int | None = Query(default=None, ge=1),
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None, ge=2000, le=2100),
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
    period_start, period_end = _period_bounds(month, year)
    filtered_rows = _dedupe_usage_rows(
        _usage_query(
            db,
            workspace_id=workspace.id,
            source=source,
            api_key_id=api_key_id,
        ).filter(
            MeterEvent.created_at >= period_start,
            MeterEvent.created_at < period_end,
        ).all()
    )
    entity_counts = aggregate_entity_counts([
        parse_event_metadata(row.metadata_json or "{}")
        for row in filtered_rows
    ])
    usage_dict = {
        "period_start": period_start.date().isoformat(),
        "period_type": "month",
        "request_count": len(filtered_rows),
        "token_count": sum(int(row.tokens or 0) for row in filtered_rows),
        "runtime_ms": sum(int(row.runtime_ms or 0) for row in filtered_rows),
        "unit_count": sum(int(row.units or 0) for row in filtered_rows),
    }
    return UsageSummaryResponse(
        workspace_id=workspace.id,
        plan_tier=workspace.plan_tier,
        limits=limits,
        usage=usage_dict,
        entity_counts=entity_counts,
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
    month: int | None = Query(default=None, ge=1, le=12),
    year: int | None = Query(default=None, ge=2000, le=2100),
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
    period_start, period_end = _period_bounds(month, year)
    query = query.filter(
        MeterEvent.created_at >= period_start,
        MeterEvent.created_at < period_end,
    )

    sort_column = {
        "created_at": MeterEvent.created_at,
        "units": MeterEvent.units,
        "tokens": MeterEvent.tokens,
        "runtime_ms": MeterEvent.runtime_ms,
    }[sort]
    query = query.order_by(sort_column.asc() if order == "asc" else sort_column.desc())
    rows = _dedupe_usage_rows(query.all())
    response.headers["X-Total-Count"] = str(len(rows))
    rows = rows[offset:offset + limit]
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
            entity_counts=aggregate_entity_counts([parse_event_metadata(row.metadata_json or "{}")]),
            created_at=row.created_at,
        )
        for row in rows
    ]

