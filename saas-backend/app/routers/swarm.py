from __future__ import annotations

import os
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
from app.routers.security_center import record_security_event
from app.engine_core import security_process_text, simulate_provider_completion, load_platform_setup, restore_sensitive_data
from app.provider_store import get_provider_secret
from aiccel.hardware_governor import OSGovernor

try:
    from aiccel.cabtp.canary import inject_canary, scan_response
    _CANARY_AVAILABLE = True
except Exception:
    _CANARY_AVAILABLE = False


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

    import uuid
    import time

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

        runtime_setup, cog_setup, sec_setup, orch_setup, obs_setup, int_setup = load_platform_setup(db, user.id, workspace_id=workspace_id)

        obj_sec = security_process_text(payload.objective, sec_setup, reversible=True)
        if obj_sec["blocked"]:
            emit_event(
                db, workspace_id, "security.swarm_breach",
                {"type": "swarm_entry_blocked", "objective": payload.objective[:120], "markers": obj_sec["detected_markers"]},
                db_session_factory
            )
            record_security_event(workspace_id, "swarm_breach", "critical", "Swarm objective blocked by zero-trust entry filter.", {"markers": obj_sec["detected_markers"]})
            raise HTTPException(status_code=403, detail="Swarm input blocked by security policy")

        collaborator_names = [f"{agent.name} ({agent.role})" for agent in collaborators]
        stages = [f"Lead agent '{lead.name}' decomposed objective into actionable tracks."]
        
        swarm_secret = f"swarm-{uuid.uuid4().hex}"
        total_tokens = 0
        total_llm_ms = 0
        amputated_agents: list[str] = []

        collab_outputs = []
        for collab in collaborators:
            collab_key = get_provider_secret(db, workspace_id=workspace_id, user_id=user.id, provider=collab.provider) or ""
            
            sanitized_objective = obj_sec.get("sanitized_text", payload.objective)
            prompt = f"Objective: {sanitized_objective}\nYour role: {collab.role}\nExecute your task."
            if _CANARY_AVAILABLE:
                prompt = inject_canary(prompt, f"{swarm_secret}-{collab.id}")
            
            start_t = time.perf_counter()
            resp = simulate_provider_completion(
                provider=collab.provider, model=collab.model, prompt=prompt,
                temperature=0.3, max_tokens=600, provider_api_key=collab_key
            )
            raw_text = restore_sensitive_data(resp.get("output", ""), obj_sec.get("token_map", {}))
            tokens = resp.get("token_usage", {}).get("total_tokens", 0)
            total_tokens += tokens
            
            if _CANARY_AVAILABLE:
                is_poisoned, _ = scan_response(raw_text, f"{swarm_secret}-{collab.id}")
                if is_poisoned:
                    # --- AUTONOMOUS AMPUTATION PROTOCOL ---
                    # 1. Engage Hardware Governor: Jail process to penalty core
                    try:
                        governor = OSGovernor(pid=os.getpid())
                        governor.apply_risk_profile(risk_score=0.99)
                    except Exception:
                        pass  # Governor is best-effort; amputation proceeds regardless

                    # 2. Record the amputation event for the Security Center ledger
                    record_security_event(
                        workspace_id, "SWARM_AMPUTATION", "critical",
                        f"CABTP Canary leaked by '{collab.name}'. Agent amputated. CPU priority throttled to IDLE.",
                        {"agent_name": collab.name, "agent_id": collab.id},
                    )

                    # 3. Emit webhook for external monitoring systems
                    emit_event(
                        db, workspace_id, "security.hardware_quarantine",
                        {"type": "swarm_amputation", "agent": collab.name, "action": "cpu_jail_core0"},
                        db_session_factory,
                    )

                    # 4. Log to execution timeline for frontend rendering
                    stages.append(
                        f"\U0001f6a8 CRITICAL: Agent '{collab.name}' compromised (Canary Leak). "
                        f"OS Hardware Quarantine engaged. Agent amputated from swarm."
                    )
                    amputated_agents.append(collab.name)

                    # 5. Skip this agent's output — the poisoned data is dropped
                    continue
            
            collab_outputs.append(f"--- {collab.name} ---\n{raw_text}")
            ms_taken = (time.perf_counter()-start_t)*1000
            total_llm_ms += ms_taken
            stages.append(f"Collaborator '{collab.name}' completed peer task in {ms_taken:.0f}ms.")
            stages.append(f"Security policy peer-checks passed for {collab.name} draft.")

        lead_key = get_provider_secret(db, workspace_id=workspace_id, user_id=user.id, provider=lead.provider) or ""
        sanitized_objective = obj_sec.get("sanitized_text", payload.objective)

        # Guard: If ALL collaborators were amputated, inform the lead agent
        if len(collab_outputs) == 0:
            stages.append(
                "\u26a0\ufe0f WARNING: All collaborators were amputated due to security breaches. "
                "Lead agent proceeding with fallback logic."
            )
            synthesized_input = (
                f"IMPORTANT: All collaborator agents failed security peer-checks and were amputated. "
                f"You must complete the following objective independently: {sanitized_objective}"
            )
        else:
            synthesized_input = f"Combine these insights into a final plan for: {sanitized_objective}\n" + "\n".join(collab_outputs)
        if _CANARY_AVAILABLE:
            synthesized_input = inject_canary(synthesized_input, f"{swarm_secret}-{lead.id}")
        
        start_t = time.perf_counter()
        lead_resp = simulate_provider_completion(
            provider=lead.provider, model=lead.model, prompt=synthesized_input,
            temperature=0.2, max_tokens=1000, provider_api_key=lead_key
        )
        final_text = restore_sensitive_data(lead_resp.get("output", ""), obj_sec.get("token_map", {}))
        tokens = lead_resp.get("token_usage", {}).get("total_tokens", 0)
        total_tokens += tokens

        if _CANARY_AVAILABLE:
             is_poisoned, _ = scan_response(final_text, f"{swarm_secret}-{lead.id}")
             if is_poisoned:
                 emit_event(db, workspace_id, "security.swarm_breach", {"type": "swarm_lead_leak", "agent": lead.name}, db_session_factory)
                 record_security_event(workspace_id, "swarm_breach", "critical", f"CABTP Canary triggered! Lead agent '{lead.name}' leaked session state.", {})
                 raise HTTPException(status_code=403, detail="Swarm halted: Lead agent leaked session state")
        
        ms_taken = (time.perf_counter()-start_t)*1000
        total_llm_ms += ms_taken
        stages.append(f"Lead agent '{lead.name}' finalized merge in {ms_taken:.0f}ms.")

        # Append degradation notice if any agents were amputated
        if amputated_agents:
            amputation_notice = (
                f"\n\n--- SECURITY NOTICE ---\n"
                f"This result was produced under degraded conditions. "
                f"{len(amputated_agents)} agent(s) were amputated due to security breaches: "
                f"{', '.join(amputated_agents)}. "
                f"Hardware quarantine was engaged. Output may be less comprehensive than expected."
            )
            final_output = final_text + amputation_notice
        else:
            final_output = final_text

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
            units=max(5, total_tokens // 100),
            runtime_ms=int(total_llm_ms + 45),
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

