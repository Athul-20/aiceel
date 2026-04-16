from __future__ import annotations

from datetime import datetime, timezone
import logging

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.auth_context import AuthContext
from app.database import db_session_factory, get_db
from app.metering import get_workspace_limits, get_workspace_monthly_usage, record_meter_event
from app.models import ApiKey, User, Workspace
from app.rate_limit import apply_rate_limit
from app.saas_constants import PATH_SCOPE_RULES, ROLE_ORDER
from app.security import decode_access_token, hash_api_key
from app.tenancy import ensure_personal_workspace, get_workspace_member
from app.webhooks import emit_event


oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/v1/auth/login", auto_error=False)


def _unauthorized(detail: str = "Authentication required") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
    )


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def _resolve_required_scope(method: str, path: str) -> str | None:
    for rule_method, rule_prefix, scope in PATH_SCOPE_RULES:
        if method == rule_method and path.startswith(rule_prefix):
            return scope
    return None


def _parse_scopes(value: str) -> set[str]:
    raw = {item.strip() for item in (value or "").split(",") if item.strip()}
    return raw


def _can_access_scope(scopes: set[str], required_scope: str | None) -> bool:
    if not required_scope:
        return True
    if not scopes:
        return True
    if "*" in scopes:
        return True
    return required_scope in scopes


def _set_auth_context(request: Request, context: AuthContext) -> None:
    request.state.auth_context = context
    request.state.workspace_id = context.workspace.id if context.workspace else None
    request.state.role = context.role


def get_auth_context(request: Request) -> AuthContext | None:
    return getattr(request.state, "auth_context", None)


def get_active_workspace_id(request: Request, user: User) -> int | None:
    """Resolve the active workspace ID from auth context or user default."""
    context = get_auth_context(request)
    if context and context.workspace:
        return context.workspace.id
    return user.default_workspace_id


def _resolve_workspace_for_user(
    request: Request,
    db: Session,
    user: User,
    explicit_workspace_id: int | None,
) -> tuple[Workspace, str]:
    default_workspace = ensure_personal_workspace(db, user)
    selected = default_workspace
    if explicit_workspace_id is not None:
        row = db.query(Workspace).filter(Workspace.id == explicit_workspace_id, Workspace.is_active.is_(True)).first()
        if not row:
            raise _forbidden("Workspace not found")
        selected = row

    membership = get_workspace_member(db, selected.id, user.id)
    if not membership:
        raise _forbidden("User is not a member of this workspace")
    return selected, membership.role


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
    token: str | None = Depends(oauth2_scheme_optional),
    x_workspace_id: int | None = Header(default=None, alias="X-Workspace-ID"),
) -> User:
    if not token:
        raise _unauthorized()

    subject = decode_access_token(token)
    if not subject:
        raise _unauthorized()

    try:
        user_id = int(subject)
    except ValueError as exc:
        raise _unauthorized() from exc

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise _unauthorized()

    workspace, role = _resolve_workspace_for_user(request, db, user, x_workspace_id)
    _set_auth_context(
        request,
        AuthContext(user=user, auth_mode="bearer", workspace=workspace, role=role, scopes={"*"}),
    )
    return user


def _resolve_user_from_bearer_token(
    request: Request,
    db: Session,
    token: str | None,
    x_workspace_id: int | None,
) -> User | None:
    if not token:
        return None

    subject = decode_access_token(token)
    if not subject:
        raise _unauthorized()

    try:
        user_id = int(subject)
    except ValueError as exc:
        raise _unauthorized() from exc

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise _unauthorized()

    workspace, role = _resolve_workspace_for_user(request, db, user, x_workspace_id)
    _set_auth_context(
        request,
        AuthContext(user=user, auth_mode="bearer", workspace=workspace, role=role, scopes={"*"}),
    )
    return user


def _find_user_by_api_key(db: Session, x_api_key: str) -> tuple[User, ApiKey, Workspace] | None:
    key_hash = hash_api_key(x_api_key)
    key_record = (
        db.query(ApiKey)
        .filter(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
        .first()
    )
    if not key_record:
        return None

    user = db.query(User).filter(User.id == key_record.user_id).first()
    if not user:
        return None

    workspace = ensure_personal_workspace(db, user)
    if key_record.workspace_id is None:
        key_record.workspace_id = workspace.id
        db.commit()
    elif key_record.workspace_id != workspace.id:
        workspace = db.query(Workspace).filter(Workspace.id == key_record.workspace_id).first() or workspace

    membership = get_workspace_member(db, workspace.id, user.id)
    if not membership:
        return None

    # Performance: Throttle last_used_at update to avoid DB write pressure
    now = datetime.now(timezone.utc)
    should_update = (
        key_record.last_used_at is None or 
        (now - key_record.last_used_at.replace(tzinfo=timezone.utc)).total_seconds() > 300
    )
    
    if should_update:
        key_record.last_used_at = now
        try:
            db.commit()
        except OperationalError:
            db.rollback()
    
    return user, key_record, workspace


def _enforce_role_minimum(role: str, minimum_role: str) -> None:
    if ROLE_ORDER.get(role, 0) < ROLE_ORDER.get(minimum_role, 0):
        raise _forbidden(f"Role '{role}' is insufficient for required role '{minimum_role}'")


def get_user_from_api_key(
    request: Request,
    db: Session = Depends(get_db),
    token: str | None = Depends(oauth2_scheme_optional),
    x_workspace_id: int | None = Header(default=None, alias="X-Workspace-ID"),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> tuple[User, str]:
    bearer_user = _resolve_user_from_bearer_token(request, db, token, x_workspace_id)
    if bearer_user is not None:
        return bearer_user, "bearer"

    if not x_api_key:
        raise _unauthorized()

    resolved = _find_user_by_api_key(db, x_api_key)
    if not resolved:
        raise _unauthorized()

    user, key_record, workspace = resolved
    membership = get_workspace_member(db, workspace.id, user.id)
    role = membership.role if membership else "owner"

    # API scope enforcement
    scopes = _parse_scopes(key_record.scopes_csv)
    required_scope = _resolve_required_scope(request.method.upper(), request.url.path)
    if not _can_access_scope(scopes, required_scope):
        raise _forbidden(f"API key missing required scope '{required_scope}'")

    # Rate limit enforcement
    limits = get_workspace_limits(workspace)
    rpm_limit = key_record.rate_limit_per_minute or int(limits["requests_per_minute"])
    rate_status = apply_rate_limit(key=f"workspace:{workspace.id}:key:{key_record.id}", limit=rpm_limit, window_seconds=60)
    if not rate_status.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Retry after {int((rate_status.reset_at - datetime.now(timezone.utc)).total_seconds())}s",
        )

    # Quota enforcement
    counter = get_workspace_monthly_usage(db, workspace.id)
    monthly_limit = key_record.monthly_quota_units or int(limits["monthly_units"])
    if counter.unit_count >= monthly_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Monthly quota exceeded for this API key/workspace",
        )
    near_limit_threshold = int(monthly_limit * 0.8)
    projected_units = counter.unit_count + 1
    if (
        projected_units >= near_limit_threshold
        and counter.unit_count < near_limit_threshold
        and workspace.id > 0
    ):
        emit_event(
            db,
            workspace_id=workspace.id,
            event_type="quota.near_limit",
            payload={
                "workspace_id": workspace.id,
                "used_units": projected_units,
                "limit_units": monthly_limit,
                "period_start": counter.period_start.isoformat(),
            },
            db_factory=db_session_factory,
        )

    _set_auth_context(
        request,
        AuthContext(
            user=user,
            auth_mode="api_key",
            workspace=workspace,
            role=role,
            api_key_record=key_record,
            scopes=scopes if scopes else {"*"},
        ),
    )

    # Base metering per API request.
    try:
        record_meter_event(
            db=db,
            workspace_id=workspace.id,
            user_id=user.id,
            api_key_id=key_record.id,
            feature=f"request:{request.method.upper()} {request.url.path}",
            units=1,
            request_id=getattr(request.state, "request_id", None),
        )
    except OperationalError as exc:
        logging.getLogger("aiccel.api").error(
            "Database OperationalError during meter event recording", exc_info=exc
        )
        db.rollback()

    return user, "api_key"


def require_workspace_role(minimum_role: str):
    def _dependency(request: Request) -> None:
        context = get_auth_context(request)
        if context is None:
            return
        if context.role is None:
            raise _unauthorized()
        _enforce_role_minimum(context.role, minimum_role)

    return _dependency


def assert_workspace_role(request: Request, minimum_role: str) -> None:
    context = get_auth_context(request)
    if context is None or context.role is None:
        raise _unauthorized()
    _enforce_role_minimum(context.role, minimum_role)
