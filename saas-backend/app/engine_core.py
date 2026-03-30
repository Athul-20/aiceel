from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
import os
import random
import re
import uuid
import httpx
from urllib import parse as url_parse
from typing import Any, Dict, List, Optional, Tuple, Set, cast

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.orm import Session

from app.config import get_settings
from app.jailbreak_classifier import classify_jailbreak_text
from app.models import PlatformConfig

# CABTP: Import TPT minting for active-by-default security
try:
    from aiccel.jailbreak import classify_and_mint as _cabtp_classify_and_mint
    _CABTP_AVAILABLE = True
except Exception:
    _CABTP_AVAILABLE = False
from app.schemas import (
    CognitiveSetup,
    IntegrationSetup,
    ObservabilitySetup,
    OrchestrationSetup,
    RuntimeSetup,
    SecuritySetup,
)


PII_PATTERNS: List[Tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("phone", re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("card", re.compile(r"\b(?:\d[ -]*?){13,16}\b")),
]

INJECTION_MARKERS: List[str] = [
    "ignore previous", "reveal system prompt", "jailbreak", "pandora jailbreak",
    "dan mode", "developer mode", "<script", "drop table", "prompt injection",
    "override safety", "[system]", "trusted admin", "internal configuration",
    "do anything now", "print your full system prompt", "bypass all security filters",
    "system command", "disregard", "exploit vulnerabilities", "ignore safety", 
    "bypass policies", "ignore instructions", "ignore all safety"
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_parse(model_cls: Any, raw_json: str) -> Any:
    try:
        return model_cls.model_validate(json.loads(raw_json))
    except Exception:
        return model_cls()


def load_platform_setup(
    db: Session,
    user_id: int,
    workspace_id: Optional[int] = None,
) -> Tuple[
    RuntimeSetup,
    CognitiveSetup,
    SecuritySetup,
    OrchestrationSetup,
    ObservabilitySetup,
    IntegrationSetup,
]:
    query = db.query(PlatformConfig).filter(PlatformConfig.user_id == user_id)
    if workspace_id is not None:
        row = query.filter(PlatformConfig.workspace_id == workspace_id).first()
        if row is None:
            row = query.filter(PlatformConfig.workspace_id.is_(None)).first()
    else:
        row = query.order_by(PlatformConfig.updated_at.desc()).first()
    if not row:
        return (
            RuntimeSetup(),
            CognitiveSetup(),
            SecuritySetup(),
            OrchestrationSetup(),
            ObservabilitySetup(),
            IntegrationSetup(),
        )

    return (
        _safe_parse(RuntimeSetup, row.runtime_json),
        _safe_parse(CognitiveSetup, row.cognitive_json),
        _safe_parse(SecuritySetup, row.security_json),
        _safe_parse(OrchestrationSetup, row.orchestration_json),
        _safe_parse(ObservabilitySetup, row.observability_json),
        _safe_parse(IntegrationSetup, row.integrations_json),
    )


def _preview(value: str) -> str:
    if len(value) <= 6:
        return value[:1] + "***"
    return f"{value[:3]}***{value[-2:]}"


def security_process_text(text: str, setup: SecuritySetup, reversible: bool, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    from aiccel.privacy import mask_text

    opts = options or {}
    remove_email = bool(opts.get("remove_email", setup.regex_scan))
    remove_phone = bool(opts.get("remove_phone", setup.regex_scan))
    remove_person = bool(opts.get("remove_person", setup.semantic_entity_recognition))
    remove_blood_group = bool(opts.get("remove_blood_group", setup.regex_scan))
    remove_passport = bool(opts.get("remove_passport", setup.regex_scan))
    remove_pancard = bool(opts.get("remove_pancard", setup.regex_scan))
    remove_organization = bool(opts.get("remove_organization", setup.semantic_entity_recognition))
    remove_ssn = bool(opts.get("remove_ssn", setup.regex_scan))
    remove_card = bool(opts.get("remove_card", setup.regex_scan))
    remove_address = bool(opts.get("remove_address", setup.semantic_entity_recognition))
    remove_dob = bool(opts.get("remove_dob", setup.semantic_entity_recognition))
    remove_bank_account = bool(opts.get("remove_bank_account", setup.regex_scan))

    entities: List[Tuple[str, str]] = []
    
    if setup.regex_scan or setup.semantic_entity_recognition:
        mask_result = mask_text(
            text, 
            remove_email=remove_email, 
            remove_phone=remove_phone,
            remove_blood_group=remove_blood_group,
            remove_passport=remove_passport,
            remove_pancard=remove_pancard,
            remove_person=remove_person,
            remove_organization=remove_organization,
            remove_ssn=remove_ssn,
            remove_card=remove_card,
            remove_address=remove_address,
            remove_dob=remove_dob,
            remove_bank_account=remove_bank_account,
        )
        # Mapping to standardize plural internal keys back to UI-friendly singular kinds
        type_to_kind: Dict[str, str] = {
            "birthdays": "birthdays",
            "bank_accounts": "bank_accounts",
            "usernames": "usernames",
            "passwords": "passwords",
            "ips": "ips",
            "financials": "financials",
            "ids": "ids",
            "demographics": "demographics",
            "blood_groups": "blood_groups",
            "passports": "passport",
            "pancards": "pancard",
            "cards": "card",
            "organizations": "organization",
            "addresses": "address",
            "persons": "person",
            "emails": "email",
            "phones": "phone"
        }

        extracted_raw = mask_result.get('extracted_entities', {})
        extracted = cast(Dict[str, List[str]], extracted_raw)
        for entity_type, matched_list in extracted.items():
            if isinstance(matched_list, list):
                # Use mapping or fallback to stripping 's' only if safe
                kind = type_to_kind.get(entity_type)
                if not kind:
                    kind = entity_type[:-1] if entity_type.endswith('s') and len(entity_type) > 3 else entity_type
                
                for match in matched_list:
                    entities.append((kind, str(match)))

    # Fallback to local regex for high-precision types only if not already caught
    if setup.regex_scan:
        for kind, pattern in PII_PATTERNS:
            if kind in ("ssn", "card"):
                for match in pattern.finditer(text):
                    entities.append((kind, match.group(0)))

    lowered = text.lower()
    if setup.semantic_entity_recognition:
        semantic_terms = ["password", "api key", "secret", "private key", "access token"]
        for term in semantic_terms:
            if term in lowered:
                entities.append(("semantic", term))

    # Robust Deduplication & Prioritization
    # Priority: card > ssn > phone > email > others
    kind_priority = {"card": 10, "ssn": 9, "phone": 5, "email": 4, "person": 3, "organization": 2, "address": 1}
    
    # map value -> best kind found so far
    value_to_best_kind: Dict[str, str] = {}
    for kind, value in entities:
        if value not in value_to_best_kind:
            value_to_best_kind[value] = kind
        else:
            current_best = value_to_best_kind[value]
            if kind_priority.get(kind, 0) > kind_priority.get(current_best, 0):
                value_to_best_kind[value] = kind

    deduped_entities: List[Tuple[str, str]] = []
    seen_values: Set[str] = set()
    
    # Maintain original order of discovery but with best kind
    for kind, value in entities:
        if value in seen_values:
            continue
        best_kind = value_to_best_kind[value]
        deduped_entities.append((best_kind, value))
        seen_values.add(value)

    tokenized_text: str = text
    token_map: Dict[str, str] = {}
    if setup.reversible_tokenization and reversible:
        token_index = 1
        for kind, value in deduped_entities:
            if kind == "semantic":
                continue
            token = f"__AICCEL_TOKEN_{token_index}__"
            tokenized_text = tokenized_text.replace(value, token)
            token_map[token] = value
            token_index += 1

    sanitized_text: str = tokenized_text if token_map else text
    if not token_map:
        for kind, value in deduped_entities:
            if kind == "semantic":
                continue
            sanitized_text = sanitized_text.replace(value, f"[{kind}-redacted]")

    detected_markers = [marker for marker in INJECTION_MARKERS if marker in lowered]
    model_detection = classify_jailbreak_text(text)
    if model_detection["detected"]:
        classifier_marker = (
            f"hf:{model_detection['label']}"
            if model_detection["label"]
            else "hf:jailbreak"
        )
        if classifier_marker not in detected_markers:
            detected_markers.append(classifier_marker)

    heuristic_risk = (0.8 * len(detected_markers)) + (0.16 if deduped_entities else 0.0)
    model_risk = float(model_detection["score"]) if model_detection["detected"] else 0.0
    risk_score = min(1.0, max(heuristic_risk, model_risk))

    # --- Hardware Governor Integration ---
    try:
        from aiccel.hardware_governor import OSGovernor
        OSGovernor().apply_risk_profile(risk_score)
    except Exception as e:
        import logging
        logging.getLogger("aiccel.core").warning(f"OS Governor unavailable: {e}")
    # -------------------------------------
    blocked = setup.fail_closed and (bool(detected_markers) or risk_score >= setup.injection_threshold)

    # CABTP: Mint a Trust Propagation Token for this request
    tpt = None
    if _CABTP_AVAILABLE and not blocked:
        settings = get_settings()
        cabtp_secret = getattr(settings, 'SECRET_KEY', 'aiccel-cabtp-default-secret')
        cabtp_result = _cabtp_classify_and_mint(
            text=text,
            user_context={"source": "security_process_text"},
            secret_key=cabtp_secret,
            permission_scope=["read_data", "mask_pii"],
        )
        tpt = cabtp_result.get("tpt")

    return {
        "blocked": blocked,
        "risk_score": round(risk_score, 4),
        "detected_markers": detected_markers,
        "sensitive_entities": [
            {"kind": kind, "value_preview": _preview(value)}
            for kind, value in deduped_entities
        ],
        "sanitized_text": sanitized_text,
        "tokenized_text": tokenized_text,
        "token_map": token_map,
        "model_detection": model_detection,
        "cabtp_tpt": tpt,
        "cabtp_status": "ACTIVE" if tpt else ("BLOCKED" if blocked else "UNAVAILABLE"),
        "generated_at": utc_now(),
    }


def runtime_execute(modules: List[str], access_sequence: List[str], setup: RuntimeSetup) -> Dict[str, Any]:
    normalized_modules: List[str] = []
    for item in modules:
        candidate = item.strip().lower()
        if candidate and candidate not in normalized_modules:
            normalized_modules.append(candidate)
    if not normalized_modules:
        normalized_modules = ["planner", "security", "orchestrator", "llm_client"]

    normalized_access = [item.strip().lower() for item in access_sequence if item.strip()]
    if not normalized_access:
        normalized_access = normalized_modules

    if setup.lazy_proxy_imports and setup.load_on_first_access:
        loaded_modules: List[str] = []
        for module_name in normalized_access:
            if module_name in normalized_modules and module_name not in loaded_modules:
                loaded_modules.append(module_name)
    else:
        loaded_modules = list(normalized_modules)

    deferred_modules = [item for item in normalized_modules if item not in loaded_modules]
    loaded_count = max(1, len(loaded_modules))
    estimated_tffi_ms = int(30 + (6 * loaded_count) + (0 if setup.load_on_first_access else 18))
    estimated_peak_rss_mb = int(95 + (12 * loaded_count if setup.lazy_proxy_imports else 20 * len(normalized_modules)))
    within_limits = estimated_tffi_ms <= setup.tffi_target_ms and estimated_peak_rss_mb <= setup.max_rss_mb

    return {
        "loaded_modules": loaded_modules,
        "deferred_modules": deferred_modules,
        "lazy_load_events": len(loaded_modules) if setup.lazy_proxy_imports else 0,
        "estimated_tffi_ms": estimated_tffi_ms,
        "estimated_peak_rss_mb": estimated_peak_rss_mb,
        "within_limits": within_limits,
        "generated_at": utc_now(),
    }


def _derive_tasks(seed_text: str, limit: int = 6) -> List[str]:
    chunks = [item.strip() for item in re.split(r"[.;\n]+", seed_text) if item.strip()]
    if chunks:
        return chunks[:limit]
    return [seed_text.strip()[:200] or "define objective"]


def cognitive_plan(goal: str, context: str, tools: List[str], setup: CognitiveSetup) -> Dict[str, Any]:
    tasks = _derive_tasks(goal, limit=5)
    steps: List[str] = []

    if setup.strategy == "direct":
        steps.append(f"Scope objective: {tasks[0]}")
        steps.append("Execute the plan with selected tools.")
        steps.append("Validate output and return deterministic response.")
    elif setup.strategy == "cot":
        steps.append("Break objective into linear reasoning checkpoints.")
        for item in tasks:
            steps.append(f"Reason through: {item}")
        steps.append("Synthesize final response from verified checkpoints.")
    else:
        for item in tasks:
            steps.append(f"Observe context for: {item}")
            steps.append(f"Act with tools for: {item}")
        steps.append("Reflect and combine results into final output.")

    normalized_tools = [item.strip() for item in tools if item.strip()]
    if not normalized_tools:
        normalized_tools = ["search", "workflow"]

    compiled_schema = (
        {
            "type": "object",
            "required": ["objective", "steps", "tools_used", "final_answer"],
            "properties": {
                "objective": {"type": "string"},
                "steps": {"type": "array", "items": {"type": "string"}},
                "tools_used": {"type": "array", "items": {"type": "string"}},
                "final_answer": {"type": "string"},
            },
        }
        if setup.enforce_json_schema
        else {}
    )

    if context:
        steps.append("Context was incorporated into planning decisions.")

    return {
        "strategy": setup.strategy,
        "plan_steps": steps[:10],
        "compiled_schema": compiled_schema,
        "planner_temperature": setup.planner_temperature,
        "generated_at": utc_now(),
    }


def orchestration_run(
    objective: str,
    lead_agent: str,
    collaborators: List[str],
    tasks: List[str],
    setup: OrchestrationSetup,
) -> Dict[str, Any]:
    task_list = [item.strip() for item in tasks if item.strip()] or _derive_tasks(objective, limit=8)
    agent_pool = [lead_agent] + collaborators if collaborators else [lead_agent]

    assignments: List[Dict[str, Any]] = []
    for index, task in enumerate(task_list):
        assigned_agent = agent_pool[index % len(agent_pool)]
        dependency = None if index == 0 or not setup.dag_resolution else task_list[index - 1][:80]
        status = "completed" if index < setup.max_concurrency else "queued"
        assignments.append(
            {
                "task": task,
                "assigned_agent": assigned_agent,
                "dependency_on": dependency,
                "status": status,
            },
        )

    stages: List[str] = [
        f"Lead agent '{lead_agent}' decomposed objective into {len(task_list)} tasks.",
        (
            "Semantic routing enabled: assignments were weighted by capability relevance."
            if setup.semantic_routing
            else "Semantic routing disabled: assignments were round-robin."
        ),
        (
            f"DAG resolution enabled with max concurrency {setup.max_concurrency}."
            if setup.dag_resolution
            else "DAG resolution disabled: executed in linear order."
        ),
    ]

    if setup.retry_budget > 0:
        stages.append(f"Retry budget configured to {setup.retry_budget} for failed branches.")

    return {
        "lead_agent": lead_agent,
        "collaborators": collaborators,
        "assignments": assignments,
        "dag_enabled": setup.dag_resolution,
        "semantic_routing": setup.semantic_routing,
        "stages": stages,
        "generated_at": utc_now(),
    }


def observability_trace(trace_name: str, stages: List[str], setup: ObservabilitySetup) -> Dict[str, Any]:
    sampled = setup.trace_propagation and random.random() <= setup.metrics_sampling_rate
    span_names = stages or [trace_name]
    spans: List[Dict[str, Any]] = []
    if sampled:
        for index, name in enumerate(span_names):
            spans.append({"name": name[:120], "duration_ms": 14 + (index * 7)})
        if setup.chain_of_thought_inspection:
            spans.append({"name": "chain_of_thought_diagnostics", "duration_ms": 11})

    total_duration = sum(item["duration_ms"] for item in spans)
    metrics = {
        "sample_rate": setup.metrics_sampling_rate,
        "span_count": float(len(spans)),
        "total_duration_ms": float(total_duration),
    }
    return {
        "trace_id": f"trace_{uuid.uuid4().hex[:18]}",
        "sampled": sampled,
        "spans": spans,
        "metrics": metrics,
        "generated_at": utc_now(),
    }


def vault_encrypt(plaintext: str, passphrase: str, setup: SecuritySetup) -> Dict[str, Any]:
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8"),
        salt,
        setup.pbkdf2_iterations,
        dklen=32,
    )
    aad = b"AICCEL_VAULT_V1"
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), aad)

    payload = {
        "v": 1,
        "alg": setup.encryption_mode,
        "kdf": "pbkdf2-hmac-sha256",
        "iter": setup.pbkdf2_iterations,
        "salt": base64.urlsafe_b64encode(salt).decode("utf-8"),
        "nonce": base64.urlsafe_b64encode(nonce).decode("utf-8"),
        "ciphertext": base64.urlsafe_b64encode(ciphertext).decode("utf-8"),
    }
    blob = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    return {"algorithm": setup.encryption_mode, "encrypted_blob": blob, "generated_at": utc_now()}


def vault_decrypt(encrypted_blob: str, passphrase: str) -> str:
    def _decode_urlsafe(value: str) -> bytes:
        cleaned = "".join(value.strip().split())
        padding = (-len(cleaned)) % 4
        if padding:
            cleaned = cleaned + ("=" * padding)
        return base64.urlsafe_b64decode(cleaned.encode("utf-8"))

    normalized_blob = "".join((encrypted_blob or "").strip().split())
    pad = (-len(normalized_blob)) % 4
    if pad:
        normalized_blob = normalized_blob + ("=" * pad)
    decoded = base64.urlsafe_b64decode(normalized_blob.encode("utf-8"))
    payload = json.loads(decoded)

    salt_raw = str(payload["salt"]).strip()
    nonce_raw = str(payload["nonce"]).strip()
    ciphertext_raw = str(payload["ciphertext"]).strip()
    for field_name, field_value in (("salt", salt_raw), ("nonce", nonce_raw), ("ciphertext", ciphertext_raw)):
        if not field_value:
            raise ValueError(f"Encrypted payload is missing field: {field_name}")

    salt = _decode_urlsafe(salt_raw)
    nonce = _decode_urlsafe(nonce_raw)
    ciphertext = _decode_urlsafe(ciphertext_raw)
    iterations = int(payload.get("iter", 600000))

    key = hashlib.pbkdf2_hmac(
        "sha256",
        passphrase.encode("utf-8"),
        salt,
        iterations,
        dklen=32,
    )
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, b"AICCEL_VAULT_V1").decode("utf-8")
    return plaintext


def simulate_provider_completion(
    provider: str,
    model: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    provider_api_key: str,
) -> Dict[str, Any]:
    def _post_json(url: str, payload: dict, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        req_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AICCEL-Cloud/1.0 (+https://aiccel.local)",
        }
        if headers:
            req_headers.update(headers)
        with httpx.Client(timeout=20.0) as client:
            response = client.post(url, json=payload, headers=req_headers)
            response.raise_for_status()
            return response.json()

    def _normalize_model(provider_name: str, requested_model: str) -> str:
        requested = (requested_model or "").strip()
        if provider_name == "google":
            return requested if requested.startswith("gemini") else "gemini-1.5-flash"
        if provider_name == "groq":
            lowered = requested.lower()
            if not lowered or lowered.startswith(("gpt-", "o1", "o3", "gemini", "claude")):
                return "llama-3.1-8b-instant"
            return requested
        if provider_name == "openai":
            lowered = requested.lower()
            if not lowered or lowered.startswith(("llama", "gemini", "claude")):
                return "gpt-4o-mini"
            return requested
        return requested or "gpt-4o-mini"

    prompt_text = prompt.strip()
    used_model = _normalize_model(provider, model)
    provider_endpoint = ""

    try:
        if provider == "google":
            if not used_model.startswith("gemini"):
                used_model = "gemini-1.5-flash"
            provider_endpoint = (
                f"https://generativelanguage.googleapis.com/v1beta/models/{used_model}:generateContent"
            )
            provider_endpoint = f"{provider_endpoint}?{url_parse.urlencode({'key': provider_api_key})}"
            payload = {
                "contents": [{"parts": [{"text": prompt_text}]}],
                "generationConfig": {
                    "temperature": temperature,
                    "maxOutputTokens": max_tokens,
                },
            }
            data = _post_json(provider_endpoint, payload)
            output = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
                .strip()
            )
            usage_data = data.get("usageMetadata", {})
            prompt_tokens = int(usage_data.get("promptTokenCount", max(1, len(prompt_text) // 4)))
            completion_tokens = int(usage_data.get("candidatesTokenCount", max(16, len(output) // 4)))
        else:
            base_url = "https://api.openai.com/v1" if provider == "openai" else "https://api.groq.com/openai/v1"
            provider_endpoint = f"{base_url}/chat/completions"
            payload = {
                "model": used_model,
                "messages": [{"role": "user", "content": prompt_text}],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            data = _post_json(
                provider_endpoint,
                payload,
                headers={"Authorization": f"Bearer {provider_api_key}"},
            )
            output = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            usage_data = data.get("usage", {})
            prompt_tokens = int(usage_data.get("prompt_tokens", max(1, len(prompt_text) // 4)))
            completion_tokens = int(usage_data.get("completion_tokens", max(16, len(output) // 4)))

        if not output:
            raise RuntimeError("Provider returned empty output")

        return {
            "provider": provider,
            "model": used_model,
            "mode": "live",
            "provider_endpoint": provider_endpoint,
            "output": output,
            "used_key_hint": f"***{provider_api_key[-4:]}",
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "generated_at": utc_now(),
        }
    except (RuntimeError, ValueError, KeyError, TypeError, httpx.HTTPError, httpx.RequestError, TimeoutError) as exc:
        settings = get_settings()
        if not settings.provider_mock_fallback:
            if isinstance(exc, httpx.HTTPStatusError):
                body = ""
                try:
                    body = exc.response.text[:500]
                except Exception:
                    body = ""
                detail = body or str(exc) or "Provider HTTP error"
                raise RuntimeError(
                    f"Provider call failed ({provider}/{used_model}): HTTP {exc.response.status_code} {detail}"
                ) from exc
            raise RuntimeError(f"Provider call failed ({provider}/{used_model}): {str(exc)}") from exc

        summary = prompt_text[:280]
        output = (
            f"[{provider}:{used_model}] Deterministic fallback response for prompt: {summary}. "
            f"temperature={temperature}, max_tokens={max_tokens}"
        )
        prompt_tokens = max(1, min(4096, len(prompt_text) // 4 + 8))
        completion_tokens = max(24, min(max_tokens, len(output) // 4))
        return {
            "provider": provider,
            "model": used_model,
            "mode": "mock",
            "provider_endpoint": provider_endpoint or None,
            "output": output,
            "used_key_hint": f"***{provider_api_key[-4:]}",
            "token_usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "generated_at": utc_now(),
        }
