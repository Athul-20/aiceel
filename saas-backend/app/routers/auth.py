from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.audit import log_audit
from app.auth_protection import check_blocked, clear_attempts, register_failed_attempt
from app.database import get_db
from app.models import RefreshToken, User
from app.schemas import RefreshTokenRequest, TokenResponse, UserAuthRequest, UserOut
from app.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_expiry,
    verify_password,
)
from app.tenancy import ensure_personal_workspace


router = APIRouter(prefix="/v1/auth", tags=["auth"])


def _client_ip(request: Request) -> str | None:
    if request.client is None:
        return None
    return request.client.host


def _issue_refresh_token(db: Session, user_id: int) -> str:
    raw = create_refresh_token()
    row = RefreshToken(
        user_id=user_id,
        token_hash=hash_refresh_token(raw),
        expires_at=refresh_expiry(),
        revoked_at=None,
    )
    db.add(row)
    db.commit()
    return raw


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserAuthRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    ip = _client_ip(request)
    if check_blocked(payload.email, ip):
        raise HTTPException(status_code=429, detail="Too many authentication attempts. Try again later.")

    existing = db.query(User).filter(User.email == payload.email.lower()).first()
    if existing:
        register_failed_attempt(payload.email, ip)
        log_audit(
            db,
            action="auth.register.failed",
            user_id=existing.id,
            target_type="user",
            target_id=str(existing.id),
            request=request,
            metadata={"reason": "email_exists"},
        )
        raise HTTPException(status_code=409, detail="Email already exists")

    user = User(email=payload.email.lower(), password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    workspace = ensure_personal_workspace(db, user)

    token = create_access_token(str(user.id))
    refresh_token = _issue_refresh_token(db, user.id)
    clear_attempts(payload.email, ip)
    log_audit(
        db,
        action="auth.register.success",
        workspace_id=workspace.id,
        user_id=user.id,
        target_type="user",
        target_id=str(user.id),
        request=request,
    )
    return TokenResponse(access_token=token, refresh_token=refresh_token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(payload: UserAuthRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    ip = _client_ip(request)
    if check_blocked(payload.email, ip):
        raise HTTPException(status_code=429, detail="Too many authentication attempts. Try again later.")

    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        register_failed_attempt(payload.email, ip)
        log_audit(
            db,
            action="auth.login.failed",
            user_id=user.id if user else None,
            target_type="user",
            target_id=str(user.id) if user else None,
            request=request,
            metadata={"reason": "invalid_credentials"},
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    workspace = ensure_personal_workspace(db, user)
    token = create_access_token(str(user.id))
    refresh_token = _issue_refresh_token(db, user.id)
    clear_attempts(payload.email, ip)
    log_audit(
        db,
        action="auth.login.success",
        workspace_id=workspace.id,
        user_id=user.id,
        target_type="user",
        target_id=str(user.id),
        request=request,
    )
    return TokenResponse(access_token=token, refresh_token=refresh_token, user=UserOut.model_validate(user))


@router.post("/refresh", response_model=TokenResponse)
def refresh_session(payload: RefreshTokenRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    token_hash = hash_refresh_token(payload.refresh_token)
    row = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked_at.is_(None),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        row.revoked_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh token expired")

    user = db.query(User).filter(User.id == row.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    workspace = ensure_personal_workspace(db, user)

    row.revoked_at = datetime.now(timezone.utc)
    db.commit()

    access_token = create_access_token(str(user.id))
    refresh_token = _issue_refresh_token(db, user.id)
    log_audit(
        db,
        action="auth.refresh.success",
        workspace_id=workspace.id,
        user_id=user.id,
        target_type="refresh_token",
        target_id=str(row.id),
        request=request,
    )
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, user=UserOut.model_validate(user))
