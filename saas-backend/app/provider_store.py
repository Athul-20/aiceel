from __future__ import annotations

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import ProviderCredential
from app.security import decrypt_secret, encrypt_secret


SUPPORTED_PROVIDERS = ("openai", "groq", "google")


def normalize_provider(provider: str) -> str:
    return provider.strip().lower()


def is_supported_provider(provider: str) -> bool:
    return normalize_provider(provider) in SUPPORTED_PROVIDERS


def get_provider_record(
    db: Session,
    *,
    workspace_id: int | None,
    user_id: int,
    provider: str,
) -> ProviderCredential | None:
    normalized = normalize_provider(provider)
    query = db.query(ProviderCredential).filter(
        ProviderCredential.provider == normalized,
        ProviderCredential.is_active.is_(True),
    )
    if workspace_id:
        query = query.filter(
            or_(ProviderCredential.workspace_id == workspace_id, ProviderCredential.user_id == user_id),
        )
    else:
        query = query.filter(ProviderCredential.user_id == user_id)
    return query.order_by(ProviderCredential.updated_at.desc()).first()


def upsert_provider_record(
    db: Session,
    *,
    workspace_id: int | None,
    user_id: int,
    provider: str,
    raw_key: str,
) -> ProviderCredential:
    normalized = normalize_provider(provider)
    key = raw_key.strip()
    row = get_provider_record(db, workspace_id=workspace_id, user_id=user_id, provider=normalized)
    if row:
        row.encrypted_key = encrypt_secret(key)
        row.key_last4 = key[-4:]
        row.is_active = True
        row.workspace_id = workspace_id or row.workspace_id
        db.commit()
        db.refresh(row)
        return row

    row = ProviderCredential(
        workspace_id=workspace_id,
        user_id=user_id,
        provider=normalized,
        encrypted_key=encrypt_secret(key),
        key_last4=key[-4:],
        is_active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_provider_secret(
    db: Session,
    *,
    workspace_id: int | None,
    user_id: int,
    provider: str,
) -> str | None:
    row = get_provider_record(db, workspace_id=workspace_id, user_id=user_id, provider=provider)
    if not row:
        return None
    try:
        return decrypt_secret(row.encrypted_key)
    except Exception:
        return None

