import json
import shutil
import subprocess
import sys
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import assert_workspace_role, get_auth_context, get_user_from_api_key
from app.metering import record_meter_event
from app.models import PlatformConfig, User
from app.schemas import IntegrationLabRequest, IntegrationLabResponse, SecuritySetup


router = APIRouter(prefix="/v1/lab", tags=["lab"])

MAX_OUTPUT_CHARS = 8000
EXEC_TIMEOUT_SEC = 4


def _truncate(value: str) -> str:
    if len(value) <= MAX_OUTPUT_CHARS:
        return value
    return value[:MAX_OUTPUT_CHARS] + "\n[truncated]"


def _validate_code(language: str, code: str) -> None:
    if len(code) > 4000:
        raise HTTPException(status_code=400, detail="Code exceeds max length")
    lowered = code.lower()
    deny_patterns = {
        "python": [
            "import os",
            "import subprocess",
            "from subprocess",
            "open(",
            "socket",
            "requests.",
            "httpx.",
            "__import__",
        ],
        "javascript": [
            "require('fs')",
            "require(\"fs\")",
            "child_process",
            "process.env",
            "fetch(",
            "xmlhttprequest",
            "import(",
        ],
    }
    targets = deny_patterns["javascript"] if language == "javascript" else deny_patterns["python"]
    if any(pattern in lowered for pattern in targets):
        raise HTTPException(status_code=400, detail="Code contains restricted operations for integration lab")


def _sandbox_enabled_for_user(db: Session, user_id: int, workspace_id: int | None) -> bool:
    query = db.query(PlatformConfig).filter(PlatformConfig.user_id == user_id)
    if workspace_id is not None:
        row = query.filter(PlatformConfig.workspace_id == workspace_id).first()
        if row is None:
            row = query.filter(PlatformConfig.workspace_id.is_(None)).first()
    else:
        row = query.first()
    if not row:
        return True
    try:
        security = SecuritySetup.model_validate(json.loads(row.security_json))
        return security.sandbox_enabled
    except Exception:
        return True


@router.post("/execute", response_model=IntegrationLabResponse)
def execute_integration_lab(
    payload: IntegrationLabRequest,
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> IntegrationLabResponse:
    user, _ = user_auth
    assert_workspace_role(request, "developer")
    context = get_auth_context(request)
    workspace_id = context.workspace.id if context and context.workspace else user.default_workspace_id
    if not _sandbox_enabled_for_user(db, user.id, workspace_id):
        raise HTTPException(status_code=403, detail="Sandbox is disabled in security setup")

    language = "javascript" if payload.language == "js" else payload.language
    _validate_code(language, payload.code)

    if language == "javascript":
        node_exec = shutil.which("node")
        if not node_exec:
            raise HTTPException(status_code=400, detail="Node.js runtime is not available on server")
        cmd = [node_exec, "-e", payload.code]
    else:
        cmd = [sys.executable, "-c", payload.code]

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            cmd,
            input=payload.input_text or "",
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT_SEC,
            shell=False,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        response = IntegrationLabResponse(
            language=language,
            stdout=_truncate(completed.stdout or ""),
            stderr=_truncate(completed.stderr or ""),
            exit_code=completed.returncode,
            timed_out=False,
            duration_ms=duration_ms,
        )
        if context and context.workspace:
            record_meter_event(
                db=db,
                workspace_id=context.workspace.id,
                user_id=user.id,
                api_key_id=context.api_key_record.id if context.api_key_record else None,
                feature="lab.execute",
                units=2,
                runtime_ms=duration_ms,
                status="ok" if completed.returncode == 0 else "error",
                request_id=getattr(request.state, "request_id", None),
            )
        return response
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        response = IntegrationLabResponse(
            language=language,
            stdout=_truncate(exc.stdout or ""),
            stderr=_truncate((exc.stderr or "") + "\nExecution timed out"),
            exit_code=124,
            timed_out=True,
            duration_ms=duration_ms,
        )
        if context and context.workspace:
            record_meter_event(
                db=db,
                workspace_id=context.workspace.id,
                user_id=user.id,
                api_key_id=context.api_key_record.id if context.api_key_record else None,
                feature="lab.execute",
                units=2,
                runtime_ms=duration_ms,
                status="timeout",
                request_id=getattr(request.state, "request_id", None),
            )
        return response
