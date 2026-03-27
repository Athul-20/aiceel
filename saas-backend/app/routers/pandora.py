"""
Pandora Data Lab — Backend Router
==================================

Accepts CSV data + natural language instruction,
uses the configured LLM provider to generate pandas code,
then executes in a sandbox and returns output.
"""

from __future__ import annotations

import io
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from aiccel.sandbox import SandboxExecutor
from app.database import get_db
from app.deps import assert_workspace_role, get_auth_context, get_user_from_api_key
from app.engine_core import simulate_provider_completion
from app.metering import record_meter_event
from app.models import User
from app.provider_store import get_provider_secret

router = APIRouter(prefix="/v1/engine/pandora", tags=["pandora"])


# ── Schemas ──────────────────────────────────────────────────────────

class PandoraTransformRequest(BaseModel):
    csv_data: str = Field(min_length=2, max_length=500_000)
    instruction: str = Field(min_length=4, max_length=4000)
    provider: str = Field(default="", pattern=r"^(openai|groq|google|)$")
    model: str = Field(default="", max_length=120)


class PandoraTransformResponse(BaseModel):
    transformed_csv: str
    row_count: int
    column_count: int
    columns: list[str]
    generated_code: str
    provider: str
    model: str
    generated_at: datetime


# ── Helpers ──────────────────────────────────────────────────────────

_PANDORA_SYSTEM = """You are PANDORA, an elite Data Engineer AI.
Your goal: Transform the pandas DataFrame `df` based on the User Instruction.

LIBRARIES AVAILABLE:
pandas (pd), numpy (np), re, random, string, datetime, math, json.

SECURITY RULES (IMPORTANT):
1. Do NOT use eval(), exec(), compile(), or __import__
2. Do NOT access file system (no open(), no Path operations)
3. Do NOT make network requests
4. Do NOT access private attributes (starting with _)
5. Only use the libraries listed above

CODE RULES:
1. The input dataframe is in the global variable `df`.
2. You MUST modify `df` in place or assign the result back to `df`.
3. Do NOT use markdown or ```python``` blocks. Just raw code.
4. Ensure `df` remains a pandas DataFrame at the end.
5. Do NOT print anything. Just transform `df`.

Start your code now:"""


def _extract_code(text: str) -> str:
    text = text.strip()
    match = re.search(r"```(?:python)?\n(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def _build_profile(csv_data: str) -> str:
    """Build a schema-only profile — NO actual data values are sent to the LLM.

    The AI only sees column names, inferred dtypes, and row count.
    This ensures user data privacy: the LLM never sees real values.
    """
    import pandas as pd

    try:
        df = pd.read_csv(io.StringIO(csv_data))
        col_info = []
        for col in df.columns:
            col_info.append(f"  - {col} (dtype: {df[col].dtype})")
        cols_str = "\n".join(col_info)
        return f"Rows: {len(df)}\nColumns ({len(df.columns)}):\n{cols_str}"
    except Exception:
        # Fallback: parse header line only
        lines = csv_data.strip().split("\n")
        header = lines[0] if lines else ""
        row_count = max(0, len(lines) - 1)
        return f"Rows: {row_count}\nColumn names: {header}"


def _pick_provider(db, workspace_id, user_id, preferred):
    """Find a configured provider. Prefers the one requested, falls back to any available."""
    providers_order = [preferred] if preferred else []
    for p in ["google", "openai", "groq"]:
        if p not in providers_order:
            providers_order.append(p)

    for prov in providers_order:
        secret = get_provider_secret(db, workspace_id=workspace_id, user_id=user_id, provider=prov)
        if secret:
            return prov, secret
    return None, None


def _execute_sandboxed(code: str, csv_data: str) -> tuple[str, int, int, list[str]]:
    """Execute generated code in a restricted sandbox."""
    import pandas as pd

    df = pd.read_csv(io.StringIO(csv_data))

    scope = {
        "df": df,
    }

    validation = _PANDORA_SANDBOX.validate_code(code)
    if not validation["valid"]:
        raise ValueError(f"Code failed sandbox validation: {'; '.join(validation['errors'])}")

    run = _PANDORA_SANDBOX.execute(code, globals_dict=scope, validate=False)
    if not run["success"]:
        raise ValueError(f"Sandbox execution failed: {run['error']}")

    result_df = run["globals"].get("df")
    if result_df is None or not hasattr(result_df, "to_csv"):
        raise ValueError("Variable 'df' is not a DataFrame after execution")

    out = io.StringIO()
    result_df.to_csv(out, index=False)
    return out.getvalue(), len(result_df), len(result_df.columns), list(result_df.columns)


# ── Default model per provider ───────────────────────────────────────

_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "groq": "llama-3.1-8b-instant",
    "google": "gemini-1.5-flash",
}

_PANDORA_SANDBOX = SandboxExecutor(timeout=8.0)


# ── Endpoint ─────────────────────────────────────────────────────────

@router.post("/transform", response_model=PandoraTransformResponse)
def pandora_transform(
    payload: PandoraTransformRequest,
    request: Request,
    user_auth: tuple[User, str] = Depends(get_user_from_api_key),
    db: Session = Depends(get_db),
) -> PandoraTransformResponse:
    user, _ = user_auth
    assert_workspace_role(request, "developer")
    context = get_auth_context(request)
    workspace_id = (
        context.workspace.id if context and context.workspace else user.default_workspace_id
    )

    # Find a provider
    provider_name, provider_secret = _pick_provider(
        db, workspace_id, user.id, payload.provider or None
    )
    if not provider_name or not provider_secret:
        raise HTTPException(
            status_code=400,
            detail="No LLM provider key configured. Add an OpenAI, Groq, or Google key in Settings → Providers first.",
        )

    use_model = payload.model.strip() or _DEFAULT_MODELS.get(provider_name, "gpt-4o-mini")

    # Build prompt
    profile = _build_profile(payload.csv_data)
    prompt = f"""{_PANDORA_SYSTEM}

DATA PROFILE:
{profile}

USER INSTRUCTION:
"{payload.instruction}"
"""

    # Call LLM
    try:
        llm_result = simulate_provider_completion(
            provider=provider_name,
            model=use_model,
            prompt=prompt,
            temperature=0.0,
            max_tokens=2048,
            provider_api_key=provider_secret,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"LLM call failed: {exc}") from exc

    raw_code = llm_result.get("output", "")
    code = _extract_code(raw_code)

    if not code.strip():
        raise HTTPException(status_code=500, detail="LLM returned empty code")

    # Execute in sandbox
    try:
        csv_out, row_count, col_count, columns = _execute_sandboxed(code, payload.csv_data)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Pandora execution failed: {exc.__class__.__name__}: {exc}",
        ) from exc

    # Meter
    if workspace_id:
        api_key_id = None
        request_id = getattr(request.state, "request_id", None)
        if context and context.api_key_record:
            api_key_id = context.api_key_record.id
        record_meter_event(
            db=db,
            workspace_id=workspace_id,
            user_id=user.id,
            api_key_id=api_key_id,
            feature="engine.pandora",
            units=5,
            tokens=llm_result.get("token_usage", {}).get("total_tokens", 0),
            runtime_ms=100,
            status="ok",
            request_id=request_id,
        )

    return PandoraTransformResponse(
        transformed_csv=csv_out,
        row_count=row_count,
        column_count=col_count,
        columns=columns,
        generated_code=code,
        provider=provider_name,
        model=use_model,
        generated_at=datetime.now(timezone.utc),
    )
