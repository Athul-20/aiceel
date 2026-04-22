from datetime import datetime, timezone
import json

from fastapi import APIRouter, Depends, HTTPException, Request

from app.errors import provider_error_to_http
from app.audit import log_audit
import logging

_pg_logger = logging.getLogger("aiccel.cabtp.playground")

# CABTP: Canary injection + scan for playground LLM calls
try:
    from aiccel.cabtp.canary import inject_canary, scan_response as canary_scan
    _CANARY_AVAILABLE = True
except Exception:
    _CANARY_AVAILABLE = False
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.catalog import SERVICES
from app.database import get_db
from app.deps import assert_workspace_role, get_auth_context, get_user_from_api_key
from app.engine_core import (
    cognitive_plan,
    load_platform_setup,
    observability_trace,
    orchestration_run,
    restore_sensitive_data,
    runtime_execute,
    security_process_text,
    simulate_provider_completion,
)
from app.models import AgentProfile, User
from app.metering import record_meter_event
from app.provider_store import get_provider_secret
from app.schemas import PlaygroundRequest, PlaygroundResponse, SecurityReport


router = APIRouter(prefix="/v1/playground", tags=["playground"])


def _pretty_json(value: object) -> str:
    return json.dumps(jsonable_encoder(value), ensure_ascii=True, indent=2)




def _resolve_provider_for_playground(
    db: Session,
    *,
    workspace_id: int | None,
    user_id: int,
) -> tuple[str, str]:
    for provider in ("openai", "groq", "google"):
        secret = get_provider_secret(db, workspace_id=workspace_id, user_id=user_id, provider=provider)
        if secret:
            return provider, secret
    raise HTTPException(
        status_code=400,
        detail="No provider key configured. Add at least one in /v1/providers (openai, groq, or google).",
    )


@router.post("/run", response_model=PlaygroundResponse)
def run_playground(
    payload: PlaygroundRequest,
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> PlaygroundResponse:
    user, auth_mode = user_auth
    assert_workspace_role(request, "developer")
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else user.default_workspace_id
    selected = next((service for service in SERVICES if service["slug"] == payload.service_slug), None)
    if not selected:
        raise HTTPException(status_code=404, detail="Service not found")

    agent_name = None
    selected_agent: AgentProfile | None = None
    if payload.agent_id is not None:
        selected_agent = (
            db.query(AgentProfile)
            .filter(
                AgentProfile.id == payload.agent_id,
                AgentProfile.user_id == user.id,
                AgentProfile.workspace_id == workspace_id,
                AgentProfile.is_active.is_(True),
            )
            .first()
        )
        if not selected_agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        agent_name = selected_agent.name

    runtime_setup, cognitive_setup, security_setup, orchestration_setup, observability_setup, integration_setup = (
        load_platform_setup(db, user.id, workspace_id=workspace_id)
    )
    security_result = security_process_text(payload.prompt, security_setup, reversible=True)
    notes: list[str] = []
    if security_result["detected_markers"]:
        notes.append(f"Jailbreak markers detected: {', '.join(security_result['detected_markers'])}")
    model_signal = security_result.get("model_detection", {})
    if isinstance(model_signal, dict) and model_signal.get("detected"):
        label = str(model_signal.get("label", "")).strip() or "jailbreak"
        score = float(model_signal.get("score", 0.0))
        notes.append(f"Model classifier flagged prompt as {label} (score={score:.3f}).")
    if security_result["token_map"]:
        notes.append("PII was tokenized using reversible privacy mapping.")
    if not notes:
        notes.append("No policy issues detected.")

    security_report = SecurityReport(
        blocked=bool(security_result["blocked"]),
        prompt_injection_detected=bool(security_result["detected_markers"]),
        pii_masked=bool(security_result["sensitive_entities"]),
        risk_score=float(security_result["risk_score"]),
        detected_markers=security_result["detected_markers"],
        sensitive_entities=security_result["sensitive_entities"],
        notes=notes,
        sanitized_prompt=security_result["sanitized_text"],
        tokenized_prompt=security_result["tokenized_text"],
        token_map=security_result["token_map"],
    )
    if security_report.blocked:
        markers_str = ", ".join(security_report.detected_markers) or "risk threshold exceeded"
        block_metadata = {
            "detected_markers": security_report.detected_markers,
            "risk_score": security_report.risk_score,
            "model_detection": {
                k: v for k, v in (security_result.get("model_detection") or {}).items()
                if k in ("detected", "label", "score", "risk_band")
            },
            "prompt_preview": payload.prompt[:200],
            "service_slug": payload.service_slug,
            "agent_name": agent_name,
        }
        log_audit(
            db,
            action="PLAYGROUND_INJECTION_BLOCKED",
            workspace_id=workspace_id,
            user_id=user.id,
            target_type="playground",
            request=request,
            metadata=block_metadata,
        )
        raise HTTPException(
            status_code=400,
            detail=f"Prompt blocked by security policy. Detected: {markers_str}",
        )

    config_snapshot = {
        "runtime.lazy_proxy_imports": str(runtime_setup.lazy_proxy_imports),
        "runtime.max_rss_mb": str(runtime_setup.max_rss_mb),
        "cognitive.strategy": str(cognitive_setup.strategy),
        "cognitive.parallel_tool_execution": str(cognitive_setup.parallel_tool_execution),
        "integrations.rest_api": str(integration_setup.rest_api),
        "integrations.sse_streaming": str(integration_setup.sse_streaming),
    }

    prompt_text = security_report.sanitized_prompt
    output_text: str
    runtime_ms = 35
    token_count = 0

    if payload.service_slug == "runtime-engine":
        runtime_result = runtime_execute(
            modules=["planner", "security", "orchestrator", "llm_client"],
            access_sequence=["planner", "llm_client"],
            setup=runtime_setup,
        )
        output_text = _pretty_json(runtime_result)
        runtime_ms = int(runtime_result.get("estimated_tffi_ms", 35))
    elif payload.service_slug == "cognitive-execution":
        tool_list = []
        if selected_agent and selected_agent.tools_csv:
            tool_list = [item.strip() for item in selected_agent.tools_csv.split(",") if item.strip()]
        cognitive_result = cognitive_plan(
            goal=prompt_text,
            context=f"service={payload.service_slug}",
            tools=tool_list or ["search", "workflow"],
            setup=cognitive_setup,
        )
        output_text = _pretty_json(cognitive_result)
        runtime_ms = 32
    elif payload.service_slug == "security-middleware":
        output_text = _pretty_json(security_report.model_dump(mode="json"))
        runtime_ms = 18
    elif payload.service_slug == "multi-agent-orchestration":
        tasks = [item for item in security_report.sanitized_prompt.split(".") if item.strip()]
        orchestration_result = orchestration_run(
            objective=security_report.sanitized_prompt,
            lead_agent=agent_name or "lead-agent",
            collaborators=[],
            tasks=tasks[:6],
            setup=orchestration_setup,
        )
        output_text = _pretty_json(orchestration_result)
        runtime_ms = 44
    elif payload.service_slug == "observability":
        trace_result = observability_trace(
            trace_name="playground_trace",
            stages=["security_gate", "execution", "response"],
            setup=observability_setup,
        )
        output_text = _pretty_json(trace_result)
        runtime_ms = 12
    elif payload.service_slug == "integrations":
        integration_state = {
            "rest_api": integration_setup.rest_api,
            "sse_streaming": integration_setup.sse_streaming,
            "mcp_interop": integration_setup.mcp_interop,
            "webhook_forwarding": integration_setup.webhook_forwarding,
            "webhook_url": integration_setup.webhook_url,
        }
        output_text = _pretty_json(integration_state)
        runtime_ms = 8
    else:
        if selected_agent and selected_agent.provider:
            provider = selected_agent.provider
            provider_secret = get_provider_secret(
                db,
                workspace_id=workspace_id,
                user_id=user.id,
                provider=provider,
            )
            if not provider_secret:
                raise HTTPException(
                    status_code=400,
                    detail=f"Provider key for '{provider}' is not configured. Add it in /v1/providers/{provider}.",
                )
        else:
            provider, provider_secret = _resolve_provider_for_playground(
                db,
                workspace_id=workspace_id,
                user_id=user.id,
            )
        model_name = selected_agent.model if selected_agent else "gpt-4o-mini"

        # CABTP: Inject canary into prompt before LLM call
        canary_prompt = prompt_text
        tpt = security_result.get("cabtp_tpt")
        if _CANARY_AVAILABLE and tpt is not None:
            canary_prompt = inject_canary(canary_prompt, tpt.canary_token)
            _pg_logger.debug("Canary injected into playground prompt")

        try:
            completion = simulate_provider_completion(
                provider=provider,
                model=model_name,
                prompt=canary_prompt,
                temperature=cognitive_setup.planner_temperature,
                max_tokens=768,
                provider_api_key=provider_secret,
            )
            
            # Restore the original data before saving output
            unmasked_output = restore_sensitive_data(completion["output"], security_report.token_map)
            completion["output"] = unmasked_output
            
        except RuntimeError as exc:
            raise provider_error_to_http(exc) from exc

        # CABTP: Scan LLM response for canary leakage
        if _CANARY_AVAILABLE and tpt is not None:
            is_poisoned, _scan = canary_scan(completion["output"], tpt.canary_token)
            if is_poisoned:
                _pg_logger.critical(
                    "CANARY LEAK in playground | session=%s",
                    tpt.session_id,
                )
                raise HTTPException(
                    status_code=400,
                    detail="Response blocked: session integrity violation detected.",
                )

        output_text = completion["output"]
        token_count = int(completion.get("token_usage", {}).get("total_tokens", 0))
        runtime_ms = 60

    response = PlaygroundResponse(
        service_slug=selected["slug"],
        service_name=selected["name"],
        agent_name=agent_name,
        output=output_text,
        used_auth=auth_mode,
        config_snapshot=config_snapshot,
        security_report=security_report,
        generated_at=datetime.now(timezone.utc),
    )
    if workspace_id:
        record_meter_event(
            db=db,
            workspace_id=workspace_id,
            user_id=user.id,
            api_key_id=context.api_key_record.id if context and context.api_key_record else None,
            feature="playground.run",
            units=3,
            tokens=token_count or len(response.output) // 4,
            runtime_ms=runtime_ms,
            request_id=getattr(request.state, "request_id", None),
        )
    return response
