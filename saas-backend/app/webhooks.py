from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import httpx

from sqlalchemy.orm import Session

from app.models import WebhookDelivery, WebhookEndpoint
from app.queueing import enqueue_job


def hash_webhook_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _event_matches(endpoint: WebhookEndpoint, event_type: str) -> bool:
    raw = endpoint.event_types_csv or ""
    if not raw.strip():
        return True
    allowed = {item.strip() for item in raw.split(",") if item.strip()}
    return event_type in allowed


def _delivery_signature(secret_hash: str, payload: str) -> str:
    return hmac.new(secret_hash.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _deliver(delivery_id: int, db_factory) -> None:
    db = db_factory()
    try:
        delivery = db.query(WebhookDelivery).filter(WebhookDelivery.id == delivery_id).first()
        if not delivery:
            return
        endpoint = db.query(WebhookEndpoint).filter(WebhookEndpoint.id == delivery.endpoint_id).first()
        if not endpoint or not endpoint.is_active:
            delivery.status = "failed"
            delivery.response_body = "Webhook endpoint not active"
            db.commit()
            return

        payload = delivery.payload_json
        signature = _delivery_signature(endpoint.secret_hash, payload)
        try:
            with httpx.Client(timeout=8.0) as client:
                response = client.post(
                    endpoint.url,
                    content=payload.encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "X-AICCEL-Event": delivery.event_type,
                        "X-AICCEL-Signature": signature,
                    },
                )
                status_code = response.status_code
                body = response.text[:4000]
            delivery.status = "sent" if status_code < 400 else "failed"
            delivery.response_code = status_code
            delivery.response_body = body
            delivery.attempts += 1
            if status_code >= 400:
                endpoint.last_failure_at = datetime.now(timezone.utc)
        except Exception as exc:
            delivery.status = "failed"
            delivery.response_body = str(exc)[:4000]
            delivery.attempts += 1
            delivery.next_retry_at = datetime.now(timezone.utc) + timedelta(minutes=min(60, delivery.attempts * 5))
            endpoint.last_failure_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def emit_event(
    db: Session,
    workspace_id: int,
    event_type: str,
    payload: dict,
    db_factory,
) -> int:
    endpoints = (
        db.query(WebhookEndpoint)
        .filter(WebhookEndpoint.workspace_id == workspace_id, WebhookEndpoint.is_active.is_(True))
        .all()
    )
    created = 0
    payload_json = json.dumps(payload, ensure_ascii=True)
    for endpoint in endpoints:
        if not _event_matches(endpoint, event_type):
            continue
        delivery = WebhookDelivery(
            endpoint_id=endpoint.id,
            event_type=event_type,
            payload_json=payload_json,
            status="queued",
            attempts=0,
        )
        db.add(delivery)
        db.flush()
        enqueue_job(_deliver, delivery.id, db_factory)
        created += 1
    db.commit()
    return created

