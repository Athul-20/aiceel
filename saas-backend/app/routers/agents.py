from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.audit import log_audit
from app.database import get_db
from app.deps import assert_workspace_role, get_auth_context, get_user_from_api_key
from app.idempotency import run_idempotent
from app.models import AgentProfile, User
from app.schemas import AgentCreateRequest, AgentOut


router = APIRouter(prefix="/v1/agents", tags=["agents"])


def _to_agent_out(row: AgentProfile) -> AgentOut:
    tools = [item.strip() for item in row.tools_csv.split(",") if item.strip()]
    return AgentOut(
        id=row.id,
        name=row.name,
        role=row.role,
        provider=row.provider,
        model=row.model,
        system_prompt=row.system_prompt,
        tools=tools,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[AgentOut])
def list_agents(
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=10000),
    sort: str = Query(default="updated_at"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
) -> list[AgentOut]:
    user, _ = user_auth
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else user.default_workspace_id
    assert_workspace_role(request, "viewer")

    query = db.query(AgentProfile).filter(
        AgentProfile.user_id == user.id,
        AgentProfile.workspace_id == workspace_id,
        AgentProfile.is_active.is_(True),
    )
    sort_column = AgentProfile.updated_at if sort != "name" else AgentProfile.name
    query = query.order_by(sort_column.asc() if order == "asc" else sort_column.desc())
    rows = query.offset(offset).limit(limit).all()
    return [_to_agent_out(row) for row in rows]


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(
    payload: AgentCreateRequest,
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> AgentOut:
    user, _ = user_auth
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else user.default_workspace_id
    assert_workspace_role(request, "developer")

    def _execute() -> AgentOut:
        tools_csv = ",".join(sorted({item.strip() for item in payload.tools if item.strip()}))
        row = AgentProfile(
            user_id=user.id,
            workspace_id=workspace_id,
            name=payload.name.strip(),
            role=payload.role.strip(),
            provider=payload.provider.strip(),
            model=payload.model.strip(),
            system_prompt=payload.system_prompt.strip(),
            tools_csv=tools_csv,
            is_active=True,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        log_audit(
            db,
            action="agent.created",
            workspace_id=workspace_id,
            user_id=user.id,
            target_type="agent",
            target_id=str(row.id),
            request=request,
            metadata={"name": row.name},
        )
        return _to_agent_out(row)

    return run_idempotent(
        db=db,
        request=request,
        workspace_id=workspace_id,
        user_id=user.id,
        payload=payload.model_dump(),
        execute=_execute,
    )


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(
    agent_id: int,
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> None:
    user, _ = user_auth
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else user.default_workspace_id
    assert_workspace_role(request, "developer")

    def _execute() -> None:
        row = (
            db.query(AgentProfile)
            .filter(
                AgentProfile.id == agent_id,
                AgentProfile.user_id == user.id,
                AgentProfile.workspace_id == workspace_id,
                AgentProfile.is_active.is_(True),
            )
            .first()
        )
        if not row:
            raise HTTPException(status_code=404, detail="Agent not found")
        row.is_active = False
        db.commit()
        log_audit(
            db,
            action="agent.deleted",
            workspace_id=workspace_id,
            user_id=user.id,
            target_type="agent",
            target_id=str(agent_id),
            request=request,
        )
        return None

    run_idempotent(
        db=db,
        request=request,
        workspace_id=workspace_id,
        user_id=user.id,
        payload={"agent_id": agent_id},
        execute=_execute,
    )
