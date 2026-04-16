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

function authOptions(auth, workspaceIdOverride) {
  if (!auth) {
    return workspaceIdOverride ? { workspaceId: workspaceIdOverride } : {};
  }

  if (typeof auth === "string") {
    return {
      apiKey: auth,
      ...(workspaceIdOverride ? { workspaceId: workspaceIdOverride } : {}),
    };
  }

  return {
    ...(auth.token ? { token: auth.token } : {}),
    ...(auth.apiKey ? { apiKey: auth.apiKey } : {}),
    ...(workspaceIdOverride ?? auth.workspaceId) ? { workspaceId: workspaceIdOverride ?? auth.workspaceId } : {},
  };
}

function withQuery(path, params = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === "") return;
    query.set(key, String(value));
  });
  const queryString = query.toString();
  return queryString ? `${path}?${queryString}` : path;
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

  listProviderKeys: (auth) =>
    request("/v1/providers", {
      ...authOptions(auth),
    }),

  upsertProviderKey: (auth, provider, payload) =>
    request(`/v1/providers/${provider}`, {
      method: "PUT",
      ...authOptions(auth),
      body: payload,
    }),

  removeProviderKey: (auth, provider) =>
    request(`/v1/providers/${provider}`, {
      method: "DELETE",
      ...authOptions(auth),
    }),

  listAgents: (auth) =>
    request("/v1/agents", {
      ...authOptions(auth),
    }),

  createAgent: (auth, payload) =>
    request("/v1/agents", {
      method: "POST",
      ...authOptions(auth),
      body: payload,
    }),

  deleteAgent: (auth, agentId) =>
    request(`/v1/agents/${agentId}`, {
      method: "DELETE",
      ...authOptions(auth),
    }),

  runSwarm: (auth, payload) =>
    request("/v1/swarm/run", {
      method: "POST",
      ...authOptions(auth),
      body: payload,
    }),

  getSecurityFeatures: (auth) =>
    request("/v1/security/features", {
      ...authOptions(auth),
    }),

  getHardwareStats: (auth) =>
    request("/v1/security/center/hardware/stats", {
      ...authOptions(auth),
    }),

  runSecurityProbe: (auth, payload) =>
    request("/v1/security/center/probe", {
      method: "POST",
      ...authOptions(auth),
      body: payload,
    }),

  getSecurityCenterStatus: (auth) =>
    request("/v1/security/center/status", {
      ...authOptions(auth),
    }),

  getPlatformSetup: (auth) =>
    request("/v1/platform/setup", {
      ...authOptions(auth),
    }),

  getPlatformFeatures: (auth) =>
    request("/v1/platform/features", {
      ...authOptions(auth),
    }),

  updateRuntimeSetup: (auth, payload) =>
    request("/v1/platform/runtime", {
      method: "PUT",
      ...authOptions(auth),
      body: payload,
    }),

  updateCognitiveSetup: (auth, payload) =>
    request("/v1/platform/cognitive", {
      method: "PUT",
      ...authOptions(auth),
      body: payload,
    }),

  updateSecuritySetup: (auth, payload) =>
    request("/v1/platform/security", {
      method: "PUT",
      ...authOptions(auth),
      body: payload,
    }),

  updateOrchestrationSetup: (auth, payload) =>
    request("/v1/platform/orchestration", {
      method: "PUT",
      ...authOptions(auth),
      body: payload,
    }),

  updateObservabilitySetup: (auth, payload) =>
    request("/v1/platform/observability", {
      method: "PUT",
      ...authOptions(auth),
      body: payload,
    }),

  updateIntegrationsSetup: (auth, payload) =>
    request("/v1/platform/integrations", {
      method: "PUT",
      ...authOptions(auth),
      body: payload,
    }),

  runIntegrationLab: (auth, payload) =>
    request("/v1/lab/execute", {
      method: "POST",
      ...authOptions(auth),
      body: payload,
    }),

  getEngineManifest: (auth) =>
    request("/v1/engine/integrations/manifest", {
      ...authOptions(auth),
    }),

  runEngineRuntime: (auth, payload) =>
    request("/v1/engine/runtime/execute", {
      method: "POST",
      ...authOptions(auth),
      body: payload,
    }),

  runEngineCognitive: (auth, payload) =>
    request("/v1/engine/cognitive/plan", {
      method: "POST",
      ...authOptions(auth),
      body: payload,
    }),

  runPdfMasking: (auth, file, options) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("options", JSON.stringify(options));
    
    return request("/v1/engine/security/pdf/mask", {
      method: "POST",
      ...authOptions(auth),
      body: formData,
    });
  },

  runPiiMasking: (auth, payload) =>
    request("/v1/pii/mask", {
      method: "POST",
      ...authOptions(auth),
      body: payload,
    }),

  runSentinelAnalyze: (auth, payload) =>
    request("/v1/sentinel/analyze", {
      method: "POST",
      ...authOptions(auth),
      body: payload,
    }),

  runVaultEncrypt: (auth, payload) =>
    request("/v1/engine/security/vault/encrypt", {
      method: "POST",
      ...authOptions(auth),
      body: payload,
    }),

  runVaultDecrypt: (auth, payload) =>
    request("/v1/engine/security/vault/decrypt", {
      method: "POST",
      ...authOptions(auth),
      body: payload,
    }),

  runEngineOrchestration: (auth, payload) =>
    request("/v1/engine/orchestration/run", {
      method: "POST",
      ...authOptions(auth),
      body: payload,
    }),

  runEngineTrace: (auth, payload) =>
    request("/v1/engine/observability/trace", {
      method: "POST",
      ...authOptions(auth),
      body: payload,
    }),

  runAgentWorkflow: (auth, payload) =>
    request("/v1/engine/workflows/agent-run", {
      method: "POST",
      ...authOptions(auth),
      body: payload,
    }),

  runLLMDispatch: (auth, payload) =>
    request("/v1/engine/llm/complete", {
      method: "POST",
      ...authOptions(auth),
      body: payload,
    }),

  runPlayground: (auth, { serviceSlug, prompt, agentId }) =>
    request("/v1/playground/run", {
      method: "POST",
      ...authOptions(auth),
      body: { service_slug: serviceSlug, prompt, agent_id: agentId ?? null },
    }),

  getUsageSummary: (auth, options = {}) =>
    request(withQuery("/v1/usage/summary", options), {
      ...authOptions(auth),
    }),

  listUsageEvents: (auth, options = {}) =>
    request(withQuery("/v1/usage/events", { limit: 100, ...options }), {
      ...authOptions(auth),
    }),

  getQuotaStatus: (auth) =>
    request("/v1/quotas/status", {
      ...authOptions(auth),
    }),

  listAuditLogs: (auth) =>
    request("/v1/audit/logs?limit=100", {
      ...authOptions(auth),
    }),

  listWebhooks: (auth) =>
    request("/v1/webhooks?limit=100", {
      ...authOptions(auth),
    }),

  createWebhook: (auth, payload) =>
    request("/v1/webhooks", {
      method: "POST",
      ...authOptions(auth),
      body: payload,
    }),

  deleteWebhook: (auth, webhookId) =>
    request(`/v1/webhooks/${webhookId}`, {
      method: "DELETE",
      ...authOptions(auth),
    }),

  listWebhookDeliveries: (auth) =>
    request("/v1/webhooks/deliveries?limit=100", {
      ...authOptions(auth),
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

  runConsoleRequest: (auth, { method, path, payload }) =>
    request(path, {
      method: String(method || "GET").toUpperCase(),
      ...authOptions(auth),
      body: String(method || "GET").toUpperCase() === "GET" ? undefined : payload,
      returnMeta: true,
    }),
  runBiomedMasking: (auth, payload) =>
    request("/v1/biomed/mask", {
      method: "POST",
      ...authOptions(auth),
      body: payload,
    }),

  runBiomedPdfMasking: (auth, file, threshold = 0.5, labels = null) => {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("threshold", String(threshold));
    if (labels && Array.isArray(labels)) {
      formData.append("labels", JSON.stringify(labels));
    }

    return request("/v1/biomed/pdf/mask", {
      method: "POST",
      ...authOptions(auth),
      body: formData,
    });
  },
  runPandoraTransform: (auth, payload) =>
    request("/v1/engine/pandora/transform", {
      method: "POST",
      ...authOptions(auth),
      body: payload,
    }),
};
