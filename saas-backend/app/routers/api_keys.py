from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.audit import log_audit
from app.database import db_session_factory, get_db
from app.deps import get_auth_context, get_current_user
from app.idempotency import run_idempotent
from app.models import ApiKey, User
from app.saas_constants import DEFAULT_API_KEY_SCOPES
from app.schemas import ApiKeyCreateRequest, ApiKeyCreateResponse, ApiKeyOut
from app.security import create_api_key, hash_api_key
from app.webhooks import emit_event


router = APIRouter(prefix="/v1/api-keys", tags=["api-keys"])


def _to_api_key_out(item: ApiKey) -> ApiKeyOut:
    scopes = [scope.strip() for scope in (item.scopes_csv or "").split(",") if scope.strip()]
    return ApiKeyOut(
        id=item.id,
        name=item.name,
        workspace_id=item.workspace_id,
        key_prefix=item.key_prefix,
        scopes=scopes,
        rate_limit_per_minute=item.rate_limit_per_minute,
        monthly_quota_units=item.monthly_quota_units,
        is_active=item.is_active,
        created_at=item.created_at,
        last_used_at=item.last_used_at,
    )


@router.get("", response_model=list[ApiKeyOut])
def list_api_keys(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    sort: str = Query(default="created_at"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> list[ApiKeyOut]:
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else current_user.default_workspace_id

    query = db.query(ApiKey).filter(
        ApiKey.user_id == current_user.id,
        ApiKey.is_active.is_(True),
    )
    if workspace_id:
        query = query.filter(ApiKey.workspace_id == workspace_id)

    sort_column = ApiKey.created_at if sort != "name" else ApiKey.name
    query = query.order_by(sort_column.asc() if order == "asc" else sort_column.desc())
    keys = query.offset(offset).limit(limit).all()
    return [_to_api_key_out(item) for item in keys]


@router.post("", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
def create_new_api_key(
    payload: ApiKeyCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiKeyCreateResponse:
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else current_user.default_workspace_id

    def _execute() -> ApiKeyCreateResponse:
        raw_key, key_prefix = create_api_key()
        scopes = payload.scopes or DEFAULT_API_KEY_SCOPES
        scopes_csv = ",".join(sorted({scope.strip() for scope in scopes if scope.strip()}))
        key_record = ApiKey(
            user_id=current_user.id,
            workspace_id=workspace_id,
            name=payload.name.strip(),
            key_prefix=key_prefix,
            key_hash=hash_api_key(raw_key),
            scopes_csv=scopes_csv,
            rate_limit_per_minute=payload.rate_limit_per_minute,
            monthly_quota_units=payload.monthly_quota_units,
            is_active=True,
        )
        db.add(key_record)
        db.commit()
        db.refresh(key_record)
        log_audit(
            db,
            action="api_key.created",
            workspace_id=workspace_id,
            user_id=current_user.id,
            target_type="api_key",
            target_id=str(key_record.id),
            request=request,
            metadata={"scopes": scopes},
        )
        return ApiKeyCreateResponse(api_key=raw_key, key=_to_api_key_out(key_record))

    payload_for_hash = {
        "name": payload.name,
        "scopes": payload.scopes,
        "rate_limit_per_minute": payload.rate_limit_per_minute,
        "monthly_quota_units": payload.monthly_quota_units,
    }
    return run_idempotent(
        db=db,
        request=request,
        workspace_id=workspace_id,
        user_id=current_user.id,
        payload=payload_for_hash,
        execute=_execute,
    )


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else current_user.default_workspace_id

    def _execute() -> None:
        key_record = (
            db.query(ApiKey)
            .filter(
                ApiKey.id == key_id,
                ApiKey.user_id == current_user.id,
                ApiKey.workspace_id == workspace_id,
                ApiKey.is_active.is_(True),
            )
            .first()
        )
        if not key_record:
            raise HTTPException(status_code=404, detail="API key not found")

        key_record.is_active = False
        db.commit()
        log_audit(
            db,
            action="api_key.revoked",
            workspace_id=workspace_id,
            user_id=current_user.id,
            target_type="api_key",
            target_id=str(key_record.id),
            request=request,
        )
        emit_event(
            db,
            workspace_id=workspace_id,
            event_type="key.revoked",
            payload={"key_id": key_record.id, "key_prefix": key_record.key_prefix},
            db_factory=db_session_factory,
        )
        return None

    run_idempotent(
        db=db,
        request=request,
        workspace_id=workspace_id,
        user_id=current_user.id,
        payload={"key_id": key_id},
        execute=_execute,
    )

