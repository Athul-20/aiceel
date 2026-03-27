from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.audit import log_audit
from app.database import get_db
from app.deps import get_current_user
from app.models import Organization, User, Workspace, WorkspaceMember
from app.schemas import (
    WorkspaceCreateRequest,
    WorkspaceMemberCreateRequest,
    WorkspaceMemberOut,
    WorkspaceOut,
    WorkspaceSwitchRequest,
)
from app.tenancy import ensure_personal_workspace, get_workspace_member, slugify


router = APIRouter(prefix="/v1/workspaces", tags=["workspaces"])


def _to_workspace_out(row: Workspace, role: str) -> WorkspaceOut:
    return WorkspaceOut(
        id=row.id,
        organization_id=row.organization_id,
        name=row.name,
        slug=row.slug,
        plan_tier=row.plan_tier,
        is_active=row.is_active,
        role=role,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _workspace_role_for_user(db: Session, workspace_id: int, user_id: int) -> str:
    membership = get_workspace_member(db, workspace_id, user_id)
    if membership is None:
        raise HTTPException(status_code=403, detail="User is not a member of this workspace")
    return membership.role


@router.get("", response_model=list[WorkspaceOut])
def list_workspaces(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WorkspaceOut]:
    ensure_personal_workspace(db, current_user)
    memberships = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.user_id == current_user.id)
        .order_by(WorkspaceMember.created_at.asc())
        .all()
    )
    if not memberships:
        return []
    workspace_ids = [row.workspace_id for row in memberships]
    role_map = {row.workspace_id: row.role for row in memberships}
    rows = db.query(Workspace).filter(Workspace.id.in_(workspace_ids), Workspace.is_active.is_(True)).all()
    return [_to_workspace_out(row, role_map.get(row.id, "viewer")) for row in rows]


@router.post("", response_model=WorkspaceOut, status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: WorkspaceCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceOut:
    default_workspace = ensure_personal_workspace(db, current_user)
    actor_role = _workspace_role_for_user(db, default_workspace.id, current_user.id)
    if actor_role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Insufficient role to create workspace")

    org = (
        db.query(Organization)
        .filter(Organization.id == default_workspace.organization_id)
        .first()
    )
    if org is None:
        raise HTTPException(status_code=400, detail="Organization not found")

    base_slug = slugify(payload.name)
    existing = {row.slug for row in db.query(Workspace.slug).filter(Workspace.organization_id == org.id).all()}
    slug = base_slug
    index = 2
    while slug in existing:
        slug = f"{base_slug}-{index}"
        index += 1

    row = Workspace(
        organization_id=org.id,
        name=payload.name.strip(),
        slug=slug,
        plan_tier=default_workspace.plan_tier,
        is_active=True,
    )
    db.add(row)
    db.flush()
    db.add(WorkspaceMember(workspace_id=row.id, user_id=current_user.id, role="owner"))
    db.commit()
    db.refresh(row)
    log_audit(
        db,
        action="workspace.created",
        workspace_id=row.id,
        user_id=current_user.id,
        target_type="workspace",
        target_id=str(row.id),
        request=request,
        metadata={"name": row.name},
    )
    return _to_workspace_out(row, "owner")


@router.get("/{workspace_id}/members", response_model=list[WorkspaceMemberOut])
def list_workspace_members(
    workspace_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WorkspaceMemberOut]:
    role = _workspace_role_for_user(db, workspace_id, current_user.id)
    if role not in {"owner", "admin", "developer", "viewer"}:
        raise HTTPException(status_code=403, detail="Insufficient role")

    rows = (
        db.query(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .filter(WorkspaceMember.workspace_id == workspace_id)
        .all()
    )
    return [
        WorkspaceMemberOut(user_id=user.id, email=user.email, role=member.role, created_at=member.created_at)
        for member, user in rows
    ]


@router.post("/{workspace_id}/members", response_model=WorkspaceMemberOut, status_code=status.HTTP_201_CREATED)
def add_workspace_member(
    workspace_id: int,
    payload: WorkspaceMemberCreateRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceMemberOut:
    actor_role = _workspace_role_for_user(db, workspace_id, current_user.id)
    if actor_role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Only owner/admin can manage members")
    if actor_role == "admin" and payload.role in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Admin cannot grant owner/admin role")

    user = db.query(User).filter(User.email == payload.email.lower()).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    row = (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user.id)
        .first()
    )
    if row:
        row.role = payload.role
    else:
        row = WorkspaceMember(workspace_id=workspace_id, user_id=user.id, role=payload.role)
        db.add(row)
    db.commit()
    db.refresh(row)
    log_audit(
        db,
        action="workspace.member.updated",
        workspace_id=workspace_id,
        user_id=current_user.id,
        target_type="workspace_member",
        target_id=f"{workspace_id}:{user.id}",
        request=request,
        metadata={"role": payload.role},
    )
    return WorkspaceMemberOut(user_id=user.id, email=user.email, role=row.role, created_at=row.created_at)


@router.put("/switch", response_model=WorkspaceOut)
def switch_workspace(
    payload: WorkspaceSwitchRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkspaceOut:
    role = _workspace_role_for_user(db, payload.workspace_id, current_user.id)
    row = db.query(Workspace).filter(Workspace.id == payload.workspace_id, Workspace.is_active.is_(True)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    current_user.default_workspace_id = row.id
    db.commit()
    log_audit(
        db,
        action="workspace.switched",
        workspace_id=row.id,
        user_id=current_user.id,
        target_type="workspace",
        target_id=str(row.id),
        request=request,
    )
    return _to_workspace_out(row, role)
