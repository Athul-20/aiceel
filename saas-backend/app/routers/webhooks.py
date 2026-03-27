from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from app.audit import log_audit
from app.database import get_db
from app.deps import assert_workspace_role, get_auth_context, get_user_from_api_key
from app.idempotency import run_idempotent
from app.models import User, WebhookDelivery, WebhookEndpoint
from app.saas_constants import WEBHOOK_EVENTS
from app.schemas import WebhookCreateRequest, WebhookDeliveryOut, WebhookOut
from app.webhooks import hash_webhook_secret


router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


def _normalize_events(raw: list[str]) -> list[str]:
    values = sorted({item.strip() for item in raw if item.strip()})
    if not values:
        return []
    invalid = [item for item in values if item not in WEBHOOK_EVENTS]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unsupported webhook event(s): {', '.join(invalid)}")
    return values


def _to_webhook_out(row: WebhookEndpoint) -> WebhookOut:
    return WebhookOut(
        id=row.id,
        url=row.url,
        event_types=[item.strip() for item in (row.event_types_csv or "").split(",") if item.strip()],
        is_active=row.is_active,
        created_at=row.created_at,
        last_failure_at=row.last_failure_at,
    )


@router.get("", response_model=list[WebhookOut])
def list_webhooks(
    request: Request,
    response: Response,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100000),
) -> list[WebhookOut]:
    user, _ = user_auth
    assert_workspace_role(request, "admin")
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else user.default_workspace_id
    if workspace_id is None:
        return []

    query = db.query(WebhookEndpoint).filter(WebhookEndpoint.workspace_id == workspace_id)
    total = query.count()
    response.headers["X-Total-Count"] = str(total)
    rows = query.order_by(WebhookEndpoint.created_at.desc()).offset(offset).limit(limit).all()
    return [_to_webhook_out(row) for row in rows]


@router.post("", response_model=WebhookOut, status_code=status.HTTP_201_CREATED)
def create_webhook(
    payload: WebhookCreateRequest,
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> WebhookOut:
    user, _ = user_auth
    assert_workspace_role(request, "admin")
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else user.default_workspace_id
    if workspace_id is None:
        raise HTTPException(status_code=400, detail="No workspace selected")
    events = _normalize_events(payload.event_types)

    def _execute() -> WebhookOut:
        row = WebhookEndpoint(
            workspace_id=workspace_id,
            url=payload.url.strip(),
            secret_hash=hash_webhook_secret(payload.secret),
            event_types_csv=",".join(events),
            is_active=True,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        log_audit(
            db,
            action="webhook.created",
            workspace_id=workspace_id,
            user_id=user.id,
            target_type="webhook",
            target_id=str(row.id),
            request=request,
            metadata={"event_types": events, "url": payload.url},
        )
        return _to_webhook_out(row)

    return run_idempotent(
        db=db,
        request=request,
        workspace_id=workspace_id,
        user_id=user.id,
        payload={"url": payload.url, "event_types": events},
        execute=_execute,
    )


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_webhook(
    webhook_id: int,
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> None:
    user, _ = user_auth
    assert_workspace_role(request, "admin")
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else user.default_workspace_id
    if workspace_id is None:
        raise HTTPException(status_code=400, detail="No workspace selected")

    def _execute() -> None:
        row = (
            db.query(WebhookEndpoint)
            .filter(
                WebhookEndpoint.id == webhook_id,
                WebhookEndpoint.workspace_id == workspace_id,
                WebhookEndpoint.is_active.is_(True),
            )
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="Webhook not found")
        row.is_active = False
        db.commit()
        log_audit(
            db,
            action="webhook.deleted",
            workspace_id=workspace_id,
            user_id=user.id,
            target_type="webhook",
            target_id=str(webhook_id),
            request=request,
        )
        return None

    run_idempotent(
        db=db,
        request=request,
        workspace_id=workspace_id,
        user_id=user.id,
        payload={"webhook_id": webhook_id},
        execute=_execute,
    )


@router.get("/deliveries", response_model=list[WebhookDeliveryOut])
def list_webhook_deliveries(
    request: Request,
    response: Response,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
    endpoint_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100000),
) -> list[WebhookDeliveryOut]:
    user, _ = user_auth
    assert_workspace_role(request, "viewer")
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else user.default_workspace_id
    if workspace_id is None:
        return []

    endpoint_ids_query = db.query(WebhookEndpoint.id).filter(WebhookEndpoint.workspace_id == workspace_id)
    if endpoint_id is not None:
        endpoint_ids_query = endpoint_ids_query.filter(WebhookEndpoint.id == endpoint_id)
    endpoint_ids = [int(row[0]) for row in endpoint_ids_query.all()]
    if not endpoint_ids:
        response.headers["X-Total-Count"] = "0"
        return []

    query = db.query(WebhookDelivery).filter(WebhookDelivery.endpoint_id.in_(endpoint_ids))
    total = query.count()
    response.headers["X-Total-Count"] = str(total)
    rows = query.order_by(WebhookDelivery.created_at.desc()).offset(offset).limit(limit).all()
    return [
        WebhookDeliveryOut(
            id=row.id,
            event_type=row.event_type,
            status=row.status,
            attempts=row.attempts,
            response_code=row.response_code,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]

