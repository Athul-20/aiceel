from __future__ import annotations

ROLE_ORDER = {
    "viewer": 10,
    "developer": 20,
    "admin": 30,
    "owner": 40,
}

PLAN_LIMITS = {
    "free": {"monthly_units": 5000, "requests_per_minute": 180},
    "pro": {"monthly_units": 50000, "requests_per_minute": 300},
    "enterprise": {"monthly_units": 1_000_000_000, "requests_per_minute": 2000},
}

DEFAULT_API_KEY_SCOPES = [
    "services.read",
    "platform.read",
    "platform.write",
    "providers.read",
    "providers.write",
    "agents.read",
    "agents.write",
    "swarm.run",
    "security.read",
    "security.process",
    "playground.run",
    "lab.execute",
    "engine.runtime",
    "engine.cognitive",
    "engine.security",
    "engine.vault",
    "engine.orchestration",
    "engine.observability",
    "engine.llm",
    "engine.workflow",
    "usage.read",
    "audit.read",
    "webhooks.manage",
    "workspaces.read",
    "workspaces.manage",
]

# Simple path-prefix based scope map. If a key has explicit scopes and no matching scope exists for path+method,
# access is denied by default to avoid accidental privilege expansion.
PATH_SCOPE_RULES: list[tuple[str, str, str]] = [
    ("GET", "/v1/services", "services.read"),
    ("GET", "/v1/platform/", "platform.read"),
    ("PUT", "/v1/platform/", "platform.write"),
    ("GET", "/v1/providers", "providers.read"),
    ("PUT", "/v1/providers/", "providers.write"),
    ("DELETE", "/v1/providers/", "providers.write"),
    ("GET", "/v1/agents", "agents.read"),
    ("POST", "/v1/agents", "agents.write"),
    ("DELETE", "/v1/agents/", "agents.write"),
    ("POST", "/v1/swarm/run", "swarm.run"),
    ("GET", "/v1/security/features", "security.read"),
    ("POST", "/v1/lab/execute", "lab.execute"),
    ("POST", "/v1/playground/run", "playground.run"),
    ("GET", "/v1/engine/integrations/manifest", "services.read"),
    ("POST", "/v1/engine/runtime/execute", "engine.runtime"),
    ("POST", "/v1/engine/cognitive/plan", "engine.cognitive"),
    ("POST", "/v1/engine/security/process", "engine.security"),
    ("POST", "/v1/engine/security/vault/", "engine.vault"),
    ("POST", "/v1/engine/orchestration/run", "engine.orchestration"),
    ("POST", "/v1/engine/observability/trace", "engine.observability"),
    ("POST", "/v1/engine/llm/complete", "engine.llm"),
    ("POST", "/v1/engine/workflows/agent-run", "engine.workflow"),
    ("GET", "/v1/engine/workflows/jobs/", "engine.workflow"),
    ("GET", "/v1/audit/logs", "audit.read"),
    ("GET", "/v1/usage/", "usage.read"),
    ("GET", "/v1/quotas/status", "usage.read"),
    ("GET", "/v1/webhooks", "webhooks.manage"),
    ("POST", "/v1/webhooks", "webhooks.manage"),
    ("DELETE", "/v1/webhooks/", "webhooks.manage"),
    ("GET", "/v1/workspaces", "workspaces.read"),
    ("POST", "/v1/workspaces", "workspaces.manage"),
    ("PUT", "/v1/workspaces/", "workspaces.manage"),
]

WEBHOOK_EVENTS = {
    "workflow.completed",
    "workflow.failed",
    "quota.near_limit",
    "key.revoked",
}
