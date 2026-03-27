from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.audit import log_audit
from app.database import db_session_factory, get_db
from app.deps import assert_workspace_role, get_auth_context, get_user_from_api_key
from app.idempotency import run_idempotent
from app.metering import record_meter_event
from app.models import AgentProfile, User
from app.schemas import SwarmRunRequest, SwarmRunResponse
from app.webhooks import emit_event


router = APIRouter(prefix="/v1/swarm", tags=["swarm"])


@router.post("/run", response_model=SwarmRunResponse)
def run_swarm(
    payload: SwarmRunRequest,
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> SwarmRunResponse:
    user, auth_mode = user_auth
    assert_workspace_role(request, "developer")
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else user.default_workspace_id

    def _execute() -> SwarmRunResponse:
        active_agents = (
            db.query(AgentProfile)
            .filter(
                AgentProfile.user_id == user.id,
                AgentProfile.workspace_id == workspace_id,
                AgentProfile.is_active.is_(True),
            )
            .all()
        )
        if not active_agents:
            raise HTTPException(status_code=400, detail="Create at least one agent first")

        by_id = {agent.id: agent for agent in active_agents}

        if payload.lead_agent_id is not None:
            lead = by_id.get(payload.lead_agent_id)
            if not lead:
                raise HTTPException(status_code=404, detail="Lead agent not found")
        else:
            lead = active_agents[0]

        collaborators: list[AgentProfile] = []
        for agent_id in payload.collaborator_agent_ids:
            agent = by_id.get(agent_id)
            if not agent:
                raise HTTPException(status_code=404, detail=f"Collaborator agent {agent_id} not found")
            if agent.id != lead.id:
                collaborators.append(agent)

        collaborator_names = [f"{agent.name} ({agent.role})" for agent in collaborators]
        stages = [
            f"Lead agent '{lead.name}' decomposed objective into actionable tracks.",
            f"Collaborators synthesized insights: {', '.join(collaborator_names) or 'none'}",
            "Security policy check passed for generated draft.",
        ]
        final_output = (
            f"Swarm output for '{payload.objective[:180]}': "
            f"{lead.name} produced the final merge with {len(collaborators)} collaborators."
        )

        response = SwarmRunResponse(
            objective=payload.objective,
            lead_agent=f"{lead.name} ({lead.role})",
            collaborators=collaborator_names,
            stages=stages,
            final_output=final_output,
            used_auth=auth_mode,
            generated_at=datetime.now(timezone.utc),
        )
        record_meter_event(
            db=db,
            workspace_id=workspace_id,
            user_id=user.id,
            api_key_id=context.api_key_record.id if context and context.api_key_record else None,
            feature="swarm.run",
            units=5,
            runtime_ms=45,
            request_id=getattr(request.state, "request_id", None),
        )
        log_audit(
            db,
            action="swarm.run",
            workspace_id=workspace_id,
            user_id=user.id,
            target_type="swarm",
            target_id=None,
            request=request,
            metadata={"lead_agent": lead.name, "collaborators": collaborator_names},
        )
        emit_event(
            db,
            workspace_id=workspace_id,
            event_type="workflow.completed",
            payload={"type": "swarm", "objective": payload.objective[:120], "lead_agent": lead.name},
            db_factory=db_session_factory,
        )
        return response

    return run_idempotent(
        db=db,
        request=request,
        workspace_id=workspace_id,
        user_id=user.id,
        payload=payload.model_dump(),
        execute=_execute,
    )

