from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models import Organization, User, Workspace, WorkspaceMember


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    lowered = re.sub(r"[^a-z0-9]+", "-", lowered)
    lowered = re.sub(r"-{2,}", "-", lowered).strip("-")
    return lowered or "workspace"


def _unique_slug(base: str, existing: set[str]) -> str:
    if base not in existing:
        return base
    idx = 2
    while f"{base}-{idx}" in existing:
        idx += 1
    return f"{base}-{idx}"


def ensure_personal_workspace(db: Session, user: User) -> Workspace:
    if user.default_workspace_id:
        workspace = db.query(Workspace).filter(Workspace.id == user.default_workspace_id).first()
        if workspace:
            membership = (
                db.query(WorkspaceMember)
                .filter(WorkspaceMember.workspace_id == workspace.id, WorkspaceMember.user_id == user.id)
                .first()
            )
            if not membership:
                db.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
                db.commit()
            return workspace

    email_prefix = user.email.split("@", 1)[0]
    org_base = slugify(email_prefix) or f"user-{user.id}"

    existing_org_slugs = {row.slug for row in db.query(Organization.slug).all()}
    org_slug = _unique_slug(org_base, existing_org_slugs)
    org = Organization(name=f"{email_prefix} Organization", slug=org_slug)
    db.add(org)
    db.commit()
    db.refresh(org)

    existing_ws_slugs = {row.slug for row in db.query(Workspace.slug).all()}
    ws_slug = _unique_slug(f"{org_slug}-default", existing_ws_slugs)
    workspace = Workspace(organization_id=org.id, name="Default Workspace", slug=ws_slug, plan_tier="free", is_active=True)
    db.add(workspace)
    db.commit()
    db.refresh(workspace)

    member = WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner")
    db.add(member)
    user.default_workspace_id = workspace.id
    db.commit()
    return workspace


def get_workspace_member(db: Session, workspace_id: int, user_id: int) -> WorkspaceMember | None:
    return (
        db.query(WorkspaceMember)
        .filter(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.user_id == user_id)
        .first()
    )

