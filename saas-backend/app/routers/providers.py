from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.audit import log_audit
from app.database import get_db
from app.deps import assert_workspace_role, get_auth_context, get_user_from_api_key
from app.idempotency import run_idempotent
from app.models import ProviderCredential, User
from app.provider_store import (
    SUPPORTED_PROVIDERS,
    get_provider_record,
    is_supported_provider,
    normalize_provider,
    upsert_provider_record,
)
from app.schemas import ProviderKeyStatus, ProviderKeyStatusResponse, ProviderKeyUpsertRequest


router = APIRouter(prefix="/v1/providers", tags=["providers"])


def _provider_status_rows(db: Session, workspace_id: int) -> list[ProviderCredential]:
    return (
        db.query(ProviderCredential)
        .filter(
            ProviderCredential.workspace_id == workspace_id,
            ProviderCredential.is_active.is_(True),
        )
        .all()
    )


def _to_provider_status(provider: str, row: ProviderCredential | None) -> ProviderKeyStatus:
    if not row:
        return ProviderKeyStatus(
            provider=provider,
            workspace_id=None,
            is_configured=False,
            key_hint=None,
            updated_at=None,
        )
    return ProviderKeyStatus(
        provider=provider,
        workspace_id=row.workspace_id,
        is_configured=True,
        key_hint=f"***{row.key_last4}",
        updated_at=row.updated_at,
    )


@router.get("", response_model=ProviderKeyStatusResponse)
def list_provider_keys(
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> ProviderKeyStatusResponse:
    user, _ = user_auth
    assert_workspace_role(request, "developer")
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else user.default_workspace_id
    rows = _provider_status_rows(db, workspace_id)
    by_provider = {normalize_provider(row.provider): row for row in rows}
    items = [_to_provider_status(provider, by_provider.get(provider)) for provider in SUPPORTED_PROVIDERS]
    return ProviderKeyStatusResponse(items=items)


@router.put("/{provider}", response_model=ProviderKeyStatus)
def upsert_provider_key(
    provider: str,
    payload: ProviderKeyUpsertRequest,
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> ProviderKeyStatus:
    normalized = normalize_provider(provider)
    if not is_supported_provider(normalized):
        raise HTTPException(status_code=404, detail="Provider not supported")

    user, _ = user_auth
    assert_workspace_role(request, "developer")
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else user.default_workspace_id
    def _execute() -> ProviderKeyStatus:
        row = upsert_provider_record(
            db,
            workspace_id=workspace_id,
            user_id=user.id,
            provider=normalized,
            raw_key=payload.api_key,
        )
        log_audit(
            db,
            action="provider_key.upserted",
            workspace_id=workspace_id,
            user_id=user.id,
            target_type="provider",
            target_id=normalized,
            request=request,
        )
        return _to_provider_status(normalized, row)

    return run_idempotent(
        db=db,
        request=request,
        workspace_id=workspace_id,
        user_id=user.id,
        payload={"provider": normalized, "api_key": "***"},
        execute=_execute,
    )


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def remove_provider_key(
    provider: str,
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> None:
    normalized = normalize_provider(provider)
    if not is_supported_provider(normalized):
        raise HTTPException(status_code=404, detail="Provider not supported")

    user, _ = user_auth
    assert_workspace_role(request, "developer")
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else user.default_workspace_id
    row = get_provider_record(db, workspace_id=workspace_id, user_id=user.id, provider=normalized)
    if not row:
        raise HTTPException(status_code=404, detail="Provider key not found")

    def _execute() -> None:
        row.is_active = False
        db.commit()
        log_audit(
            db,
            action="provider_key.deleted",
            workspace_id=workspace_id,
            user_id=user.id,
            target_type="provider",
            target_id=normalized,
            request=request,
        )
        return None

    run_idempotent(
        db=db,
        request=request,
        workspace_id=workspace_id,
        user_id=user.id,
        payload={"provider": normalized},
        execute=_execute,
    )
