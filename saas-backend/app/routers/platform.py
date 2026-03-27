from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.audit import log_audit
from app.database import get_db
from app.deps import assert_workspace_role, get_auth_context, get_user_from_api_key
from app.idempotency import run_idempotent
from app.models import PlatformConfig, User
from app.schemas import (
    CognitiveSetup,
    IntegrationSetup,
    ObservabilitySetup,
    OrchestrationSetup,
    PlatformFeature,
    PlatformFeaturesResponse,
    PlatformSetupResponse,
    RuntimeSetup,
    SecuritySetup,
)


router = APIRouter(prefix="/v1/platform", tags=["platform"])

FEATURE_CATALOG = [
    PlatformFeature(
        subsystem="runtime",
        title="Runtime Engine",
        description="Lazy-loading runtime for reduced memory footprint and low time-to-first-instruction.",
        capabilities=[
            "Virtual proxy import interception",
            "Lazy resolution on attribute access",
            "Memory-constrained operation profile",
        ],
    ),
    PlatformFeature(
        subsystem="cognitive",
        title="Cognitive Execution Engine",
        description="Deterministic control flow by separating planning from side-effect execution.",
        capabilities=[
            "Planner strategies: direct, ReAct, chain-of-thought",
            "Rigid JSON schema compilation",
            "Parallel tool execution via orchestrator",
        ],
    ),
    PlatformFeature(
        subsystem="security",
        title="Security Middleware Suite",
        description="Mandatory privacy and adversarial filtering before runtime execution.",
        capabilities=[
            "Regex + semantic privacy scanning",
            "Adversarial heuristic gating with fail-closed default",
            "Cryptographic vault policy configuration",
            "Sandbox execution limits",
        ],
    ),
    PlatformFeature(
        subsystem="orchestration",
        title="Multi-Agent Orchestration",
        description="Concurrency-safe orchestration with semantic routing and DAG resolution.",
        capabilities=[
            "Embedding-driven semantic routing",
            "Dependency graph decomposition",
            "Parallel execution for independent branches",
        ],
    ),
    PlatformFeature(
        subsystem="observability",
        title="Observability",
        description="Trace propagation and runtime diagnostics for internal behavior visibility.",
        capabilities=[
            "End-to-end trace propagation",
            "Chain-of-thought inspection toggle",
            "Metrics sampling controls",
        ],
    ),
    PlatformFeature(
        subsystem="integrations",
        title="Integration Interfaces",
        description="Operational APIs for ecosystem interoperability and app integration.",
        capabilities=[
            "REST interface",
            "Server-Sent Events streaming",
            "Model Context Protocol interoperability",
        ],
    ),
]


def _safe_parse(model_cls, raw_json: str):
    try:
        payload = json.loads(raw_json)
        return model_cls.model_validate(payload)
    except Exception:
        return model_cls()


def _ensure_platform_config(db: Session, user_id: int, workspace_id: int | None) -> PlatformConfig:
    query = db.query(PlatformConfig).filter(PlatformConfig.user_id == user_id)
    if workspace_id is not None:
        row = query.filter(PlatformConfig.workspace_id == workspace_id).first()
        if row is None:
            row = query.filter(PlatformConfig.workspace_id.is_(None)).first()
    else:
        row = query.order_by(PlatformConfig.updated_at.desc()).first()
    if row:
        if row.workspace_id is None and workspace_id is not None:
            row.workspace_id = workspace_id
            db.commit()
        return row

    row = PlatformConfig(
        user_id=user_id,
        workspace_id=workspace_id,
        runtime_json=RuntimeSetup().model_dump_json(),
        cognitive_json=CognitiveSetup().model_dump_json(),
        security_json=SecuritySetup().model_dump_json(),
        orchestration_json=OrchestrationSetup().model_dump_json(),
        observability_json=ObservabilitySetup().model_dump_json(),
        integrations_json=IntegrationSetup().model_dump_json(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _to_setup_response(row: PlatformConfig) -> PlatformSetupResponse:
    return PlatformSetupResponse(
        runtime=_safe_parse(RuntimeSetup, row.runtime_json),
        cognitive=_safe_parse(CognitiveSetup, row.cognitive_json),
        security=_safe_parse(SecuritySetup, row.security_json),
        orchestration=_safe_parse(OrchestrationSetup, row.orchestration_json),
        observability=_safe_parse(ObservabilitySetup, row.observability_json),
        integrations=_safe_parse(IntegrationSetup, row.integrations_json),
        updated_at=row.updated_at,
    )


@router.get("/features", response_model=PlatformFeaturesResponse)
def get_platform_features(
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
) -> PlatformFeaturesResponse:
    _user, _ = user_auth
    assert_workspace_role(request, "viewer")
    return PlatformFeaturesResponse(items=FEATURE_CATALOG)


@router.get("/setup", response_model=PlatformSetupResponse)
def get_platform_setup(
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> PlatformSetupResponse:
    user, _ = user_auth
    assert_workspace_role(request, "viewer")
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else user.default_workspace_id
    row = _ensure_platform_config(db, user.id, workspace_id)
    return _to_setup_response(row)


def _update_section(
    *,
    request: Request,
    db: Session,
    user: User,
    section: str,
    payload,
) -> object:
    assert_workspace_role(request, "developer")
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else user.default_workspace_id
    row = _ensure_platform_config(db, user.id, workspace_id)

    def _execute():
        if section == "runtime":
            row.runtime_json = payload.model_dump_json()
        elif section == "cognitive":
            row.cognitive_json = payload.model_dump_json()
        elif section == "security":
            row.security_json = payload.model_dump_json()
        elif section == "orchestration":
            row.orchestration_json = payload.model_dump_json()
        elif section == "observability":
            row.observability_json = payload.model_dump_json()
        elif section == "integrations":
            row.integrations_json = payload.model_dump_json()
        db.commit()
        log_audit(
            db,
            action=f"platform.{section}.updated",
            workspace_id=workspace_id,
            user_id=user.id,
            target_type="platform_config",
            target_id=str(row.id),
            request=request,
        )
        return payload

    return run_idempotent(
        db=db,
        request=request,
        workspace_id=workspace_id,
        user_id=user.id,
        payload=payload.model_dump(),
        execute=_execute,
    )


@router.put("/runtime", response_model=RuntimeSetup)
def update_runtime_setup(
    payload: RuntimeSetup,
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> RuntimeSetup:
    user, _ = user_auth
    return _update_section(request=request, db=db, user=user, section="runtime", payload=payload)


@router.put("/cognitive", response_model=CognitiveSetup)
def update_cognitive_setup(
    payload: CognitiveSetup,
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> CognitiveSetup:
    user, _ = user_auth
    return _update_section(request=request, db=db, user=user, section="cognitive", payload=payload)


@router.put("/security", response_model=SecuritySetup)
def update_security_setup(
    payload: SecuritySetup,
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> SecuritySetup:
    user, _ = user_auth
    return _update_section(request=request, db=db, user=user, section="security", payload=payload)


@router.put("/orchestration", response_model=OrchestrationSetup)
def update_orchestration_setup(
    payload: OrchestrationSetup,
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> OrchestrationSetup:
    user, _ = user_auth
    return _update_section(request=request, db=db, user=user, section="orchestration", payload=payload)


@router.put("/observability", response_model=ObservabilitySetup)
def update_observability_setup(
    payload: ObservabilitySetup,
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> ObservabilitySetup:
    user, _ = user_auth
    return _update_section(request=request, db=db, user=user, section="observability", payload=payload)


@router.put("/integrations", response_model=IntegrationSetup)
def update_integrations_setup(
    payload: IntegrationSetup,
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> IntegrationSetup:
    user, _ = user_auth
    return _update_section(request=request, db=db, user=user, section="integrations", payload=payload)
