from __future__ import annotations

from datetime import date
import json
import logging

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import MeterEvent, UsageCounter, Workspace
from app.saas_constants import PLAN_LIMITS


def _period_start_today() -> date:
    today = date.today()
    return date(today.year, today.month, 1)


def record_meter_event(
    db: Session,
    workspace_id: int,
    user_id: int | None,
    api_key_id: int | None,
    feature: str,
    units: int = 1,
    tokens: int = 0,
    runtime_ms: int = 0,
    status: str = "ok",
    request_id: str | None = None,
) -> None:
    event = MeterEvent(
        workspace_id=workspace_id,
        user_id=user_id,
        api_key_id=api_key_id,
        feature=feature,
        units=max(0, units),
        tokens=max(0, tokens),
        runtime_ms=max(0, runtime_ms),
        status=status,
        request_id=request_id,
    )
    try:
        db.add(event)

        period_start = _period_start_today()
        counter = (
            db.query(UsageCounter)
            .filter(
                UsageCounter.workspace_id == workspace_id,
                UsageCounter.period_start == period_start,
                UsageCounter.period_type == "month",
            )
            .first()
        )
        if not counter:
            counter = UsageCounter(
                workspace_id=workspace_id,
                period_start=period_start,
                period_type="month",
                request_count=0,
                token_count=0,
                runtime_ms=0,
                unit_count=0,
            )
            db.add(counter)
            db.flush()

        counter.request_count += 1
        counter.token_count += max(0, tokens)
        counter.runtime_ms += max(0, runtime_ms)
        counter.unit_count += max(0, units)
        db.commit()
    except OperationalError as exc:
        logging.getLogger("aiccel.api").error(
            "Database OperationalError during async meter event commit", exc_info=exc
        )
        db.rollback()


def get_workspace_monthly_usage(db: Session, workspace_id: int) -> UsageCounter:
    period_start = _period_start_today()
    counter = (
        db.query(UsageCounter)
        .filter(
            UsageCounter.workspace_id == workspace_id,
            UsageCounter.period_start == period_start,
            UsageCounter.period_type == "month",
        )
        .first()
    )
    if counter:
        return counter
    counter = UsageCounter(
        workspace_id=workspace_id,
        period_start=period_start,
        period_type="month",
        request_count=0,
        token_count=0,
        runtime_ms=0,
        unit_count=0,
    )
    db.add(counter)
    db.commit()
    db.refresh(counter)
    return counter


def get_workspace_limits(workspace: Workspace) -> dict[str, int]:
    return PLAN_LIMITS.get(workspace.plan_tier, PLAN_LIMITS["free"])


def usage_to_dict(counter: UsageCounter) -> dict[str, int | str]:
    return {
        "period_start": counter.period_start.isoformat(),
        "period_type": counter.period_type,
        "request_count": counter.request_count,
        "token_count": counter.token_count,
        "runtime_ms": counter.runtime_ms,
        "unit_count": counter.unit_count,
    }


def parse_event_metadata(value: str) -> dict:
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
        return {}
    except Exception:
        return {}
