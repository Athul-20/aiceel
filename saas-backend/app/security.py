"""Authentication helpers: passwords, JWTs, API keys, and encryption.

All heavy objects (password context, crypto ciphers) are created lazily
so that importing this module has no side-effects and tests can set
environment overrides before anything is initialised.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import base64
import hashlib
import secrets
from functools import lru_cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import get_settings


JWT_ALGORITHM = "HS256"


@lru_cache(maxsize=1)
def _get_password_context() -> CryptContext:
    """Build the password hashing context lazily (once)."""
    settings = get_settings()
    if settings.app_env == "test":
        return CryptContext(
            schemes=["pbkdf2_sha256"],
            deprecated="auto",
            pbkdf2_sha256__default_rounds=2000,
            pbkdf2_sha256__min_rounds=1000,
        )
    return CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return _get_password_context().hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _get_password_context().verify(password, password_hash)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    ttl = expires_minutes or settings.access_token_expire_minutes
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl)
    payload = {"sub": subject, "exp": expires_at, "typ": "access"}
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str | None:
    settings = get_settings()
    candidate_secrets = [settings.secret_key] + list(settings.previous_secret_keys)
    for secret in candidate_secrets:
        try:
            payload = jwt.decode(token, secret, algorithms=[JWT_ALGORITHM])
            if payload.get("typ") not in (None, "access"):
                continue
            subject = payload.get("sub")
            if isinstance(subject, str):
                return subject
        except JWTError:
            continue
    return None


def create_refresh_token() -> str:
    return f"rt_{secrets.token_urlsafe(48)}"


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def refresh_expiry() -> datetime:
    settings = get_settings()
    return datetime.now(timezone.utc) + timedelta(minutes=settings.refresh_token_expire_minutes)


def create_api_key() -> tuple[str, str]:
    raw_token = f"ak_live_{secrets.token_urlsafe(36)}"
    return raw_token, raw_token[:12]


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _service_key() -> bytes:
    settings = get_settings()
    return hashlib.sha256(settings.secret_key.encode("utf-8")).digest()


def encrypt_secret(value: str) -> str:
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(_service_key()).encrypt(nonce, value.encode("utf-8"), b"AICCEL_SECRET_V1")
    return base64.urlsafe_b64encode(nonce + encrypted).decode("utf-8")


def decrypt_secret(value: str) -> str:
    raw = base64.urlsafe_b64decode(value.encode("utf-8"))
    nonce = raw[:12]
    encrypted = raw[12:]
    cipher = AESGCM(_service_key())
    for aad in (b"AICCEL_SECRET_V1", b"AICCEL_PROVIDER_KEY_V1"):
        try:
            plaintext = cipher.decrypt(nonce, encrypted, aad)
            return plaintext.decode("utf-8")
        except Exception:
            continue
    raise ValueError("Unable to decrypt secret with configured service keys")
