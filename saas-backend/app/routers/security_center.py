from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import assert_workspace_role, get_auth_context, get_user_from_api_key
from app.engine_core import load_platform_setup, security_process_text
from app.models import User

# CABTP module availability checks
try:
    from aiccel.cabtp.canary import CommitmentTier
    _CANARY_OK = True
except Exception:
    _CANARY_OK = False

try:
    from aiccel.cabtp.output_filter import SCOPE_RULES
    _FILTER_OK = True
except Exception:
    _FILTER_OK = False

try:
    from aiccel.cabtp.audit_ledger import AuditLedger
    _LEDGER_OK = True
except Exception:
    _LEDGER_OK = False

try:
    from aiccel.cabtp.tpt import verify_token
    _TPT_OK = True
except Exception:
    _TPT_OK = False

try:
    from aiccel.jailbreak import classify_and_mint
    _JAILBREAK_OK = True
except Exception:
    _JAILBREAK_OK = False

try:
    from aiccel.hardware_governor import OSGovernor
    _GOVERNOR_OK = True
except Exception:
    _GOVERNOR_OK = False


router = APIRouter(prefix="/v1/security/center", tags=["security-center"])


# ── In-Memory Event Store ───────────────────────────────────────────
# Stores recent security events per workspace. In production this
# would be backed by Redis or a database table.

_MAX_EVENTS = 200

_events: dict[int | None, list[dict[str, Any]]] = {}


def record_security_event(
    workspace_id: int | None,
    event_type: str,
    severity: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    """Record a security event for the Security Center activity feed."""
    if workspace_id not in _events:
        _events[workspace_id] = []

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "severity": severity,   # "info", "warning", "critical"
        "message": message,
        "details": details or {},
    }

    _events[workspace_id].append(entry)
    if len(_events[workspace_id]) > _MAX_EVENTS:
        _events[workspace_id] = _events[workspace_id][-_MAX_EVENTS:]


# ── Response Models ─────────────────────────────────────────────────

class ModuleStatus(BaseModel):
    name: str
    status: str = Field(description="ACTIVE, DEGRADED, or INACTIVE")
    description: str


class SecurityEvent(BaseModel):
    timestamp: str
    event_type: str
    severity: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class HardwareStats(BaseModel):
    cpu_count: int
    logical_cores: int
    current_affinity_count: int
    priority_class: str
    pid: int
    risk_level: str

class MaskingEntry(BaseModel):
    entity_type: str
    preview: str
    token: str


class MaskingTransparency(BaseModel):
    original_preview: str
    sanitized_text: str
    entities_masked: list[MaskingEntry]
    risk_score: float
    blocked: bool
    cabtp_status: str


class SecurityCenterResponse(BaseModel):
    modules: list[ModuleStatus]
    recent_events: list[SecurityEvent]
    last_masking: MaskingTransparency | None = None
    active_alerts: list[SecurityEvent]
    generated_at: datetime


class SecurityProbeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=16000)


class SecurityProbeResponse(BaseModel):
    masking: MaskingTransparency
    events: list[SecurityEvent]
    generated_at: datetime


# ── Endpoints ───────────────────────────────────────────────────────

@router.get("/status", response_model=SecurityCenterResponse)
def get_security_center_status(
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> SecurityCenterResponse:
    """
    Returns the live status of all CABTP security modules,
    recent security events, and any active alerts.
    """
    user, _ = user_auth
    assert_workspace_role(request, "viewer")
    context = get_auth_context(request)
    workspace_id = (
        context.workspace.id if context and context.workspace else user.default_workspace_id
    )

    # Module status checks
    modules = [
        ModuleStatus(
            name="PII Guard",
            status="ACTIVE",
            description="Personal data is masked before reaching the AI. Emails, phones, names, cards, and addresses are replaced with safe tokens.",
        ),
        ModuleStatus(
            name="Canary System",
            status="ACTIVE" if _CANARY_OK else "INACTIVE",
            description=(
                "A hidden tripwire is embedded in every prompt. If the AI leaks it, the response is blocked immediately."
                if _CANARY_OK else
                "Canary module is not loaded. Session poisoning detection is unavailable."
            ),
        ),
        ModuleStatus(
            name="Jailbreak Shield",
            status="ACTIVE" if _JAILBREAK_OK else "DEGRADED",
            description=(
                "Every prompt is scanned for injection attacks, adversarial patterns, and system prompt extraction attempts."
                if _JAILBREAK_OK else
                "Jailbreak classifier model is not loaded. Only heuristic detection is active."
            ),
        ),
        ModuleStatus(
            name="Agent Trust",
            status="ACTIVE" if _TPT_OK else "INACTIVE",
            description=(
                "Every AI agent carries a cryptographically signed badge. Tampering or privilege escalation is detected instantly."
                if _TPT_OK else
                "Trust Propagation Token module is not loaded."
            ),
        ),
        ModuleStatus(
            name="Output Filter",
            status="ACTIVE" if _FILTER_OK else "INACTIVE",
            description=(
                "AI responses are checked against your clearance level. Data you should not see is redacted before delivery."
                if _FILTER_OK else
                "Output filter module is not loaded."
            ),
        ),
        ModuleStatus(
            name="Audit Trail",
            status="ACTIVE" if _LEDGER_OK else "INACTIVE",
            description=(
                "Every security decision is recorded in a tamper-proof log. Any modification to past records is detectable."
                if _LEDGER_OK else
                "Audit ledger module is not loaded."
            ),
        ),
        ModuleStatus(
            name="Hardware Governor",
            status="ACTIVE" if _GOVERNOR_OK else "INACTIVE",
            description=(
                "OS-Level Sandboxing. Dynamically throttles CPU cores and priorities via the AI Neural Risk Score."
                if _GOVERNOR_OK else
                "OS limits not available."
            ),
        ),
    ]

    # Recent events for this workspace
    ws_events = _events.get(workspace_id, [])
    recent = [SecurityEvent(**e) for e in ws_events[-50:]]
    recent.reverse()  # newest first

    # Active alerts = recent critical/warning events
    active_alerts = [
        e for e in recent if e.severity in ("critical", "warning")
    ][:10]

    return SecurityCenterResponse(
        modules=modules,
        recent_events=recent,
        last_masking=None,
        active_alerts=active_alerts,
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/hardware/stats", response_model=HardwareStats)
def get_hardware_stats(
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
) -> HardwareStats:
    """
    Returns live physical resource allocation for the current engine process.
    """
    import psutil
    import platform

    proc = psutil.Process()
    os_name = platform.system()
    
    priority = "Unknown"
    if os_name == "Windows":
        p_val = proc.nice()
        if p_val == getattr(psutil, "NORMAL_PRIORITY_CLASS", 32): priority = "Normal"
        elif p_val == getattr(psutil, "IDLE_PRIORITY_CLASS", 64): priority = "Idle (Jailed)"
        elif p_val == getattr(psutil, "BELOW_NORMAL_PRIORITY_CLASS", 16384): priority = "Below Normal"
        elif p_val == getattr(psutil, "HIGH_PRIORITY_CLASS", 128): priority = "High"
    else:
        priority = f"Nice {proc.nice()}"

    affinity = []
    if hasattr(proc, "cpu_affinity"):
        try:
            affinity = proc.cpu_affinity()
        except Exception:
            affinity = list(range(psutil.cpu_count() or 1))

    cpu_phys = psutil.cpu_count(logical=False) or 1
    cpu_log = psutil.cpu_count(logical=True) or 1
    
    risk_level = "safe"
    if len(affinity) <= 1: risk_level = "critical"
    elif len(affinity) < cpu_log: risk_level = "elevated"

    return HardwareStats(
        cpu_count=cpu_phys,
        logical_cores=cpu_log,
        current_affinity_count=len(affinity),
        priority_class=priority,
        pid=proc.pid,
        risk_level=risk_level
    )


@router.post("/probe", response_model=SecurityProbeResponse)
def probe_security(
    payload: SecurityProbeRequest,
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> SecurityProbeResponse:
    """
    Run a prompt through the full security pipeline and return
    transparent results showing exactly what was masked, what risk
    was detected, and what would be sent to the AI.
    """
    user, _ = user_auth
    assert_workspace_role(request, "developer")
    context = get_auth_context(request)
    workspace_id = (
        context.workspace.id if context and context.workspace else user.default_workspace_id
    )

    _, _, security_setup, *_ = load_platform_setup(
        db, user.id, workspace_id=workspace_id,
    )

    result = security_process_text(payload.text, security_setup, reversible=True)

    entities_masked = [
        MaskingEntry(
            entity_type=ent.get("kind", "unknown"),
            preview=ent.get("value_preview", "***"),
            token=token,
        )
        for ent, token in zip(
            result.get("sensitive_entities", []),
            list(result.get("token_map", {}).keys()),
        )
    ]

    # If there are more entities than tokens, add them without token mapping
    remaining = result.get("sensitive_entities", [])[len(entities_masked):]
    for ent in remaining:
        entities_masked.append(
            MaskingEntry(
                entity_type=ent.get("kind", "unknown"),
                preview=ent.get("value_preview", "***"),
                token="[redacted]",
            )
        )

    masking = MaskingTransparency(
        original_preview=payload.text[:500] + ("..." if len(payload.text) > 500 else ""),
        sanitized_text=result.get("sanitized_text", payload.text),
        entities_masked=entities_masked,
        risk_score=result.get("risk_score", 0.0),
        blocked=result.get("blocked", False),
        cabtp_status=result.get("cabtp_status", "UNAVAILABLE"),
    )

    # Generate events for this probe
    probe_events: list[SecurityEvent] = []
    now = datetime.now(timezone.utc).isoformat()

    if entities_masked:
        types_list = ", ".join(set(e.entity_type for e in entities_masked))
        msg = f"{len(entities_masked)} sensitive item(s) detected and masked: {types_list}"
        evt = SecurityEvent(
            timestamp=now, event_type="PII_MASKED", severity="info", message=msg,
            details={"count": len(entities_masked), "types": types_list},
        )
        probe_events.append(evt)
        record_security_event(workspace_id, "PII_MASKED", "info", msg)

    if result.get("detected_markers"):
        markers = ", ".join(result["detected_markers"])
        msg = f"Prompt injection patterns detected: {markers}"
        sev = "critical" if result.get("blocked") else "warning"
        evt = SecurityEvent(
            timestamp=now, event_type="INJECTION_DETECTED", severity=sev, message=msg,
            details={"markers": result["detected_markers"], "risk_score": result.get("risk_score", 0)},
        )
        probe_events.append(evt)
        record_security_event(workspace_id, "INJECTION_DETECTED", sev, msg)

    if result.get("blocked"):
        msg = "Prompt was BLOCKED by security policy. The AI never received this request."
        evt = SecurityEvent(
            timestamp=now, event_type="PROMPT_BLOCKED", severity="critical", message=msg,
        )
        probe_events.append(evt)
        record_security_event(workspace_id, "PROMPT_BLOCKED", "critical", msg)

    cabtp_status = result.get("cabtp_status", "UNAVAILABLE")
    if cabtp_status == "ACTIVE":
        msg = "Trust token generated. Canary tripwire embedded. Session is protected."
        evt = SecurityEvent(
            timestamp=now, event_type="TPT_MINTED", severity="info", message=msg,
        )
        probe_events.append(evt)
        record_security_event(workspace_id, "TPT_MINTED", "info", msg)

    if not probe_events:
        msg = "Prompt scanned. No sensitive data or threats detected."
        evt = SecurityEvent(
            timestamp=now, event_type="SCAN_CLEAN", severity="info", message=msg,
        )
        probe_events.append(evt)
        record_security_event(workspace_id, "SCAN_CLEAN", "info", msg)

    return SecurityProbeResponse(
        masking=masking,
        events=probe_events,
        generated_at=datetime.now(timezone.utc),
    )
