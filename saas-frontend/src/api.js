export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request(path, { method = "GET", token, apiKey, workspaceId, idempotencyKey, body, returnMeta = false } = {}) {
  const headers = {};
  if (!(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  if (token) headers.Authorization = `Bearer ${token}`;
  if (apiKey) headers["X-API-Key"] = apiKey;
  if (workspaceId) headers["X-Workspace-ID"] = String(workspaceId);
  if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body instanceof FormData ? body : (body ? JSON.stringify(body) : undefined),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const requestError = new Error(error?.error?.message || error.detail || "Request failed");
    requestError.status = response.status;
    requestError.payload = error;
    throw requestError;
  }

  const isBlob = response.headers.get("content-type")?.includes("application/pdf");
  const data = response.status === 204 ? null : (isBlob ? await response.blob() : await response.json());
  
  if (isBlob) {
    let entities = [];
    try { entities = JSON.parse(response.headers.get("X-Entity-Summary") || "[]"); } catch {}
    return {
      blob: data,
      redactedCount: parseInt(response.headers.get("X-Redacted-Count") || "0", 10),
      entities,
    };
  }

  if (returnMeta) {
    return { data, status: response.status };
  }
  return data;
}

export const api = {
  register: (email, password) =>
    request("/v1/auth/register", {
      method: "POST",
      body: { email, password },
    }),

  login: (email, password) =>
    request("/v1/auth/login", {
      method: "POST",
      body: { email, password },
    }),

  refresh: (refreshToken) =>
    request("/v1/auth/refresh", {
      method: "POST",
      body: { refresh_token: refreshToken },
    }),

  getServices: () => request("/v1/services"),

  listApiKeys: (token, workspaceId) =>
    request("/v1/api-keys", {
      token,
      workspaceId,
    }),

  createApiKey: (token, name, workspaceId) =>
    request("/v1/api-keys", {
      method: "POST",
      token,
      workspaceId,
      body: { name },
    }),

  revokeApiKey: (token, keyId, workspaceId) =>
    request(`/v1/api-keys/${keyId}`, {
      method: "DELETE",
      token,
      workspaceId,
    }),

  listProviderKeys: (apiKey) =>
    request("/v1/providers", {
      apiKey,
    }),

  upsertProviderKey: (apiKey, provider, payload) =>
    request(`/v1/providers/${provider}`, {
      method: "PUT",
      apiKey,
      body: payload,
    }),

  removeProviderKey: (apiKey, provider) =>
    request(`/v1/providers/${provider}`, {
      method: "DELETE",
      apiKey,
    }),

  listAgents: (apiKey) =>
    request("/v1/agents", {
      apiKey,
    }),

  createAgent: (apiKey, payload) =>
    request("/v1/agents", {
      method: "POST",
      apiKey,
      body: payload,
    }),

  deleteAgent: (apiKey, agentId) =>
    request(`/v1/agents/${agentId}`, {
      method: "DELETE",
      apiKey,
    }),

  runSwarm: (apiKey, payload) =>
    request("/v1/swarm/run", {
      method: "POST",
      apiKey,
      body: payload,
    }),

  getSecurityFeatures: (apiKey) =>
    request("/v1/security/features", {
      apiKey,
    }),

  getSecurityCenterStatus: (apiKey) =>
    request("/v1/security/center/status", {
      apiKey,
    }),

  getHardwareStats: (apiKey) =>
    request("/v1/security/center/hardware/stats", {
      apiKey,
    }),

  runSecurityProbe: (apiKey, payload) =>
    request("/v1/security/center/probe", {
      method: "POST",
      apiKey,
      body: payload,
    }),

  getPlatformSetup: (apiKey) =>
    request("/v1/platform/setup", {
      apiKey,
    }),

  getPlatformFeatures: (apiKey) =>
    request("/v1/platform/features", {
      apiKey,
    }),

  updateRuntimeSetup: (apiKey, payload) =>
    request("/v1/platform/runtime", {
      method: "PUT",
      apiKey,
      body: payload,
    }),

  updateCognitiveSetup: (apiKey, payload) =>
    request("/v1/platform/cognitive", {
      method: "PUT",
      apiKey,
      body: payload,
    }),

  updateSecuritySetup: (apiKey, payload) =>
    request("/v1/platform/security", {
      method: "PUT",
      apiKey,
      body: payload,
    }),

  updateOrchestrationSetup: (apiKey, payload) =>
    request("/v1/platform/orchestration", {
      method: "PUT",
      apiKey,
      body: payload,
    }),

  updateObservabilitySetup: (apiKey, payload) =>
    request("/v1/platform/observability", {
      method: "PUT",
      apiKey,
      body: payload,
    }),

  updateIntegrationsSetup: (apiKey, payload) =>
    request("/v1/platform/integrations", {
      method: "PUT",
      apiKey,
      body: payload,
    }),

  runIntegrationLab: (apiKey, payload) =>
    request("/v1/lab/execute", {
      method: "POST",
      apiKey,
      body: payload,
    }),

  getEngineManifest: (apiKey) =>
    request("/v1/engine/integrations/manifest", {
      apiKey,
    }),

  runEngineRuntime: (apiKey, payload) =>
    request("/v1/engine/runtime/execute", {
      method: "POST",
      apiKey,
      body: payload,
    }),

  runEngineCognitive: (apiKey, payload) =>
    request("/v1/engine/cognitive/plan", {
      method: "POST",
      apiKey,
      body: payload,
    }),

  runPdfMasking: (apiKey, file, options) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("options", JSON.stringify(options));
    
    return request("/v1/engine/security/pdf/mask", {
      method: "POST",
      apiKey,
      body: formData,
    });
  },

  runEngineSecurity: (apiKey, payload) =>
    request("/v1/engine/security/process", {
      method: "POST",
      apiKey,
      body: payload,
    }),

  runVaultEncrypt: (apiKey, payload) =>
    request("/v1/engine/security/vault/encrypt", {
      method: "POST",
      apiKey,
      body: payload,
    }),

  runVaultDecrypt: (apiKey, payload) =>
    request("/v1/engine/security/vault/decrypt", {
      method: "POST",
      apiKey,
      body: payload,
    }),

  runEngineOrchestration: (apiKey, payload) =>
    request("/v1/engine/orchestration/run", {
      method: "POST",
      apiKey,
      body: payload,
    }),

  runEngineTrace: (apiKey, payload) =>
    request("/v1/engine/observability/trace", {
      method: "POST",
      apiKey,
      body: payload,
    }),

  runAgentWorkflow: (apiKey, payload) =>
    request("/v1/engine/workflows/agent-run", {
      method: "POST",
      apiKey,
      body: payload,
    }),

  runLLMDispatch: (apiKey, payload) =>
    request("/v1/engine/llm/complete", {
      method: "POST",
      apiKey,
      body: payload,
    }),

  runPlayground: ({ apiKey, serviceSlug, prompt, agentId }) =>
    request("/v1/playground/run", {
      method: "POST",
      apiKey,
      body: { service_slug: serviceSlug, prompt, agent_id: agentId ?? null },
    }),

  getUsageSummary: (apiKey) =>
    request("/v1/usage/summary", {
      apiKey,
    }),

  listUsageEvents: (apiKey) =>
    request("/v1/usage/events?limit=100", {
      apiKey,
    }),

  getQuotaStatus: (apiKey) =>
    request("/v1/quotas/status", {
      apiKey,
    }),

  listAuditLogs: (apiKey) =>
    request("/v1/audit/logs?limit=100", {
      apiKey,
    }),

  listWebhooks: (apiKey) =>
    request("/v1/webhooks?limit=100", {
      apiKey,
    }),

  createWebhook: (apiKey, payload) =>
    request("/v1/webhooks", {
      method: "POST",
      apiKey,
      body: payload,
    }),

  deleteWebhook: (apiKey, webhookId) =>
    request(`/v1/webhooks/${webhookId}`, {
      method: "DELETE",
      apiKey,
    }),

  listWebhookDeliveries: (apiKey) =>
    request("/v1/webhooks/deliveries?limit=100", {
      apiKey,
    }),

  listWorkspaces: (token) =>
    request("/v1/workspaces", {
      token,
    }),

  createWorkspace: (token, payload) =>
    request("/v1/workspaces", {
      method: "POST",
      token,
      body: payload,
    }),

  switchWorkspace: (token, workspaceId) =>
    request("/v1/workspaces/switch", {
      method: "PUT",
      token,
      body: { workspace_id: workspaceId },
    }),

  listWorkspaceMembers: (token, workspaceId) =>
    request(`/v1/workspaces/${workspaceId}/members`, {
      token,
    }),

  addWorkspaceMember: (token, workspaceId, payload) =>
    request(`/v1/workspaces/${workspaceId}/members`, {
      method: "POST",
      token,
      body: payload,
    }),

  runConsoleRequest: (apiKey, { method, path, payload }) =>
    request(path, {
      method: String(method || "GET").toUpperCase(),
      apiKey,
      body: String(method || "GET").toUpperCase() === "GET" ? undefined : payload,
      returnMeta: true,
    }),
  runBiomedMasking: (apiKey, payload) =>
    request("/v1/biomed/mask", {
      method: "POST",
      apiKey,
      body: payload,
    }),

  runBiomedPdfMasking: (apiKey, file, threshold = 0.5, labels = null) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("threshold", String(threshold));
    if (labels && Array.isArray(labels)) {
      formData.append("labels", JSON.stringify(labels));
    }

    return request("/v1/biomed/pdf/mask", {
      method: "POST",
      apiKey,
      body: formData,
    });
  },
};
