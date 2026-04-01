import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import {
  TOKEN_KEY, REFRESH_TOKEN_KEY, USER_KEY, ACTIVE_API_KEY_STORAGE,
  DEFAULT_SETUP, ENGINE_OPERATIONS, SECTION_TEXT, VIEW_META,
  normalizeModelForProvider, SETUP_SECTIONS,
} from "../constants";

const AppContext = createContext(null);
export const THEME_STORAGE_KEY = "aiccel_theme";

function readStorage(key, fallback = "") {
  try {
    const value = localStorage.getItem(key);
    return value ?? fallback;
  } catch {
    return fallback;
  }
}

function writeStorage(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {}
}

function removeStorage(key) {
  try {
    localStorage.removeItem(key);
  } catch {}
}

function readJsonStorage(key, fallback = null) {
  const raw = readStorage(key, "");
  if (!raw) return fallback;
  try {
    return JSON.parse(raw);
  } catch {
    removeStorage(key);
    return fallback;
  }
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}

export function AppProvider({ children }) {
  const ACTIVE_VIEW_STORAGE = "aiccel_active_view";
  const [theme, setTheme] = useState(() => {
    const storedTheme = readStorage(THEME_STORAGE_KEY, "light");
    return storedTheme === "dark" ? "dark" : "light";
  });
  const [mode, setMode] = useState("login");
  const [activeView, setActiveView] = useState(() => readStorage(ACTIVE_VIEW_STORAGE, "dashboard"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState(readStorage(TOKEN_KEY, ""));
  const [refreshToken, setRefreshToken] = useState(readStorage(REFRESH_TOKEN_KEY, ""));
  const [user, setUser] = useState(() => readJsonStorage(USER_KEY, null));
  const refreshInFlightRef = useRef(null);

  const [services, setServices] = useState([]);
  const [apiKeys, setApiKeys] = useState([]);
  const [apiKeyName, setApiKeyName] = useState("Primary Key");
  const [newRawKey, setNewRawKey] = useState("");
  const [apiKeyInput, setApiKeyInput] = useState(readStorage(ACTIVE_API_KEY_STORAGE, ""));
  const [activeApiKey, setActiveApiKey] = useState(readStorage(ACTIVE_API_KEY_STORAGE, ""));

  const [setup, setSetup] = useState(DEFAULT_SETUP);
  const [setupUpdatedAt, setSetupUpdatedAt] = useState("");
  const [featureCatalog, setFeatureCatalog] = useState([]);
  const [securityFeatures, setSecurityFeatures] = useState([]);
  const [providerStatuses, setProviderStatuses] = useState([]);
  const [providerInputs, setProviderInputs] = useState({ openai: "", groq: "", google: "" });
  const [usageSummary, setUsageSummary] = useState(null);
  const [usageEvents, setUsageEvents] = useState([]);
  const [quotaStatus, setQuotaStatus] = useState(null);
  const [auditLogs, setAuditLogs] = useState([]);
  const [webhooks, setWebhooks] = useState([]);
  const [webhookDeliveries, setWebhookDeliveries] = useState([]);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("");
  const [webhookEvents, setWebhookEvents] = useState(["workflow.completed", "workflow.failed"]);

  const [workspaces, setWorkspaces] = useState([]);
  const [activeWorkspaceId, setActiveWorkspaceId] = useState(() => readJsonStorage(USER_KEY, null)?.default_workspace_id ?? null);
  const [workspaceName, setWorkspaceName] = useState("Production Workspace");
  const [workspaceMembers, setWorkspaceMembers] = useState([]);
  const [memberEmail, setMemberEmail] = useState("");
  const [memberRole, setMemberRole] = useState("developer");

  const [agents, setAgents] = useState([]);
  const [agentName, setAgentName] = useState("Core Planner");
  const [agentRole, setAgentRole] = useState("assistant");
  const [agentProvider, setAgentProvider] = useState("openai");
  const [agentModel, setAgentModel] = useState("gpt-4o-mini");
  const [agentPrompt, setAgentPrompt] = useState("Plan deterministic tasks and keep outputs concise.");
  const [agentTools, setAgentTools] = useState("search,workflow");
  const [agentRunAgentId, setAgentRunAgentId] = useState("");
  const [agentRunService, setAgentRunService] = useState("secure-playground");
  const [agentRunObjective, setAgentRunObjective] = useState("Execute selected agent workflow");
  const [agentRunPrompt, setAgentRunPrompt] = useState("");
  const [agentRunResult, setAgentRunResult] = useState(null);
  const [singleAgentTestAgentId, setSingleAgentTestAgentId] = useState("");
  const [singleAgentTestService, setSingleAgentTestService] = useState("single-agent-lab");
  const [singleAgentTestPrompt, setSingleAgentTestPrompt] = useState("Review this request and return a safe, concise answer.");
  const [singleAgentTestResult, setSingleAgentTestResult] = useState(null);

  const [swarmObjective, setSwarmObjective] = useState("");
  const [swarmLeadId, setSwarmLeadId] = useState("");
  const [swarmCollaborators, setSwarmCollaborators] = useState([]);
  const [swarmResult, setSwarmResult] = useState(null);

  const [playgroundService, setPlaygroundService] = useState("secure-playground");
  const [playgroundAgentId, setPlaygroundAgentId] = useState("");
  const [playgroundPrompt, setPlaygroundPrompt] = useState("");
  const [playgroundResult, setPlaygroundResult] = useState(null);
  const [dashboardService, setDashboardService] = useState("secure-playground");
  const [dashboardPrompt, setDashboardPrompt] = useState("");
  const [dashboardResult, setDashboardResult] = useState(null);

  const [labLanguage, setLabLanguage] = useState("python");
  const [labInput, setLabInput] = useState("");
  const [labCode, setLabCode] = useState("print('AICCEL integration lab ready')\nprint('input:', input())");
  const [labResult, setLabResult] = useState(null);

  const [engineOperation, setEngineOperation] = useState("workflow");
  const [enginePayload, setEnginePayload] = useState(() => JSON.stringify(ENGINE_OPERATIONS.workflow.payload, null, 2));
  const [engineResult, setEngineResult] = useState(null);
  const [engineRequestMeta, setEngineRequestMeta] = useState(null);
  const [engineManifest, setEngineManifest] = useState(null);
  const [lastVaultEncryptedBlob, setLastVaultEncryptedBlob] = useState("");
  const [lastVaultPassphrase, setLastVaultPassphrase] = useState("");

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [authError, setAuthError] = useState("");
  const [authNotice, setAuthNotice] = useState("");

  const isLoggedIn = useMemo(() => Boolean(token && user), [token, user]);
  const activePrefix = useMemo(() => activeApiKey.slice(0, 12), [activeApiKey]);
  const hasActiveKey = useMemo(() => apiKeys.some((i) => i.is_active && i.key_prefix === activePrefix), [apiKeys, activePrefix]);
  const selectedRunAgent = useMemo(() => agents.find((i) => String(i.id) === String(agentRunAgentId)) || null, [agents, agentRunAgentId]);
  const metrics = useMemo(() => [
    ["Services", services.length], ["Features", featureCatalog.length],
    ["Agents", agents.length], ["Security Controls", securityFeatures.length],
    ["Usage Units", usageSummary?.usage?.unit_count ?? 0], ["Webhooks", webhooks.length],
  ], [services, featureCatalog, agents, securityFeatures, usageSummary, webhooks]);
  const activeViewMeta = useMemo(() => {
    if (SECTION_TEXT[activeView]) return SECTION_TEXT[activeView];
    return VIEW_META[activeView] || VIEW_META.dashboard;
  }, [activeView]);
  const activeWorkspace = useMemo(() => workspaces.find((i) => i.id === activeWorkspaceId) || null, [workspaces, activeWorkspaceId]);

  // ── Auth helpers ─────────────────────────────
  function applySession(payload) {
    const t = payload?.access_token || "";
    const r = payload?.refresh_token || "";
    const u = payload?.user || null;
    setToken(t); setRefreshToken(r); setUser(u);
    writeStorage(TOKEN_KEY, t);
    writeStorage(REFRESH_TOKEN_KEY, r);
    if (u) writeStorage(USER_KEY, JSON.stringify(u));
    else removeStorage(USER_KEY);
    setError(""); setNotice(""); setAuthError(""); setAuthNotice("");
  }

  function clearSession(message = "") {
    setToken(""); setRefreshToken(""); setUser(null);
    setApiKeys([]); setActiveApiKey(""); setApiKeyInput("");
    removeStorage(TOKEN_KEY);
    removeStorage(REFRESH_TOKEN_KEY);
    removeStorage(USER_KEY);
    removeStorage(ACTIVE_API_KEY_STORAGE);
    setError("");
    setNotice("");
    setAuthNotice("");
    setAuthError(message);
  }

  async function refreshAccessToken() {
    if (!refreshToken) { clearSession("Session expired."); return null; }
    if (refreshInFlightRef.current) return refreshInFlightRef.current;
    refreshInFlightRef.current = (async () => {
      try {
        const data = await api.refresh(refreshToken);
        applySession(data);
        return data.access_token;
      } catch { clearSession("Session expired. Please log in again."); return null; }
      finally { refreshInFlightRef.current = null; }
    })();
    return refreshInFlightRef.current;
  }

  async function withBearerRetry(operation, currentToken = token) {
    try { return await operation(currentToken); }
    catch (err) {
      if (err.status === 401 || err.status === 403) {
        const newToken = await refreshAccessToken();
        if (!newToken) throw err;
        return operation(newToken);
      }
      throw err;
    }
  }

  // ── Data loaders ─────────────────────────────
  async function refreshApiKeys(t = token) {
    try {
      const keys = await withBearerRetry((tok) => api.listApiKeys(tok, activeWorkspaceId), t);
      setApiKeys(keys);
    } catch (err) { console.error("Failed to refresh API keys:", err); }
  }

  async function loadWorkspaces(t = token) {
    try {
      const ws = await withBearerRetry((tok) => api.listWorkspaces(tok), t);
      setWorkspaces(ws);
    } catch (err) { console.error("Failed to load workspaces:", err); }
  }

  async function loadWorkspaceMembers(wsId, t = token) {
    try {
      const m = await withBearerRetry((tok) => api.listWorkspaceMembers(tok, wsId), t);
      setWorkspaceMembers(m);
    } catch (err) { console.error("Failed to load workspace members:", err); }
  }

  async function loadSecuredContext(key) {
    try {
      const results = await Promise.allSettled([
        api.listProviderKeys(key), api.getPlatformFeatures(key), api.getSecurityFeatures(key),
        api.getPlatformSetup(key), api.getUsageSummary(key), api.listUsageEvents(key),
        api.getQuotaStatus(key), api.listAuditLogs(key), api.listWebhooks(key), api.listWebhookDeliveries(key),
      ]);
      const [prov, feat, sec, setup_, usage_, events, quota_, audit_, wh, whd] = results;

      // If every call was rejected with 401, the stored API key is stale — clear it
      const allUnauthorized = results.every((r) => r.status === "rejected" && r.reason?.status === 401);
      if (allUnauthorized) {
        console.warn("Stored API key is invalid or expired — clearing it.");
        setActiveApiKey(""); setApiKeyInput("");
        writeStorage(ACTIVE_API_KEY_STORAGE, "");
        return;
      }

      if (prov.status === "fulfilled") setProviderStatuses(prov.value?.items || prov.value || []);
      if (feat.status === "fulfilled") setFeatureCatalog(feat.value);
      if (sec.status === "fulfilled") setSecurityFeatures(sec.value);
      if (setup_.status === "fulfilled") {
        const d = setup_.value;
        setSetup((prev) => ({ ...prev, ...d.setup }));
        if (d.updated_at) setSetupUpdatedAt(d.updated_at);
      }
      if (usage_.status === "fulfilled") setUsageSummary(usage_.value);
      if (events.status === "fulfilled") setUsageEvents(events.value);
      if (quota_.status === "fulfilled") setQuotaStatus(quota_.value);
      if (audit_.status === "fulfilled") setAuditLogs(audit_.value);
      if (wh.status === "fulfilled") setWebhooks(wh.value);
      if (whd.status === "fulfilled") setWebhookDeliveries(whd.value);
    } catch (err) { console.error("Failed to load secured context:", err); }
  }

  async function loadOpsContext(key = activeApiKey, targetView = activeView) {
    try {
      if (targetView === "agents" || targetView === "swarm") {
        const a = await api.listAgents(key); setAgents(a);
      }
      if (targetView === "usage") {
        const [s, e] = await Promise.all([api.getUsageSummary(key), api.listUsageEvents(key)]);
        setUsageSummary(s); setUsageEvents(e);
      }
      if (targetView === "quotas") { const q = await api.getQuotaStatus(key); setQuotaStatus(q); }
      if (targetView === "audit") { const a = await api.listAuditLogs(key); setAuditLogs(a); }
      if (targetView === "webhooks") {
        const [w, d] = await Promise.all([api.listWebhooks(key), api.listWebhookDeliveries(key)]);
        setWebhooks(w); setWebhookDeliveries(d);
      }
      if (targetView === "workspaces") { await loadWorkspaces(); }
      if (targetView === "providers") { const p = await api.listProviderKeys(key); setProviderStatuses(p?.items || p || []); }
      if (targetView === "feature_apis") {
        try { const m = await api.getEngineManifest(key); setEngineManifest(m); } catch (err) { console.error(err); }
      }
    } catch (err) { console.error("Failed to load ops context:", err); }
  }

  // ── Auth actions ─────────────────────────────
  async function authSubmit(e) {
    e.preventDefault(); setBusy(true); setError(""); setNotice(""); setAuthError(""); setAuthNotice("");
    try {
      const data = mode === "register" ? await api.register(email, password) : await api.login(email, password);
      if (mode === "register" && !data.access_token) { setAuthNotice("Registered. Please sign in."); setMode("login"); }
      else applySession(data);
    } catch (err) { setAuthError(err.message); }
    finally { setBusy(false); }
  }

  // ── API Key actions ──────────────────────────
  async function createKey(e) {
    e.preventDefault(); setBusy(true); setError(""); setNotice("");
    try {
      const data = await withBearerRetry((tok) => api.createApiKey(tok, apiKeyName, activeWorkspaceId));
      setNewRawKey(data.api_key || "");
      if (data.api_key) { setApiKeyInput(data.api_key); setActiveApiKey(data.api_key); writeStorage(ACTIVE_API_KEY_STORAGE, data.api_key); }
      setNotice("API key created.");
      await refreshApiKeys();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  function activateKey(e) {
    e.preventDefault();
    const k = apiKeyInput.trim();
    if (!k) return;
    setActiveApiKey(k); writeStorage(ACTIVE_API_KEY_STORAGE, k);
    setNotice(`Key ${k.slice(0, 12)}... activated.`);
  }

  async function revokeKey(id) {
    setBusy(true); setError("");
    try {
      await withBearerRetry((tok) => api.revokeApiKey(tok, id, activeWorkspaceId));
      setNotice("Key revoked.");
      await refreshApiKeys();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  // ── Provider actions ─────────────────────────
  function setProviderInput(provider, value) { setProviderInputs((p) => ({ ...p, [provider]: value })); }
  async function refreshProviders(k = activeApiKey) {
    try { const p = await api.listProviderKeys(k); setProviderStatuses(p?.items || p || []); } catch (err) { console.error(err); }
  }
  async function saveProviderKey(provider) {
    const value = providerInputs[provider]?.trim();
    if (!value) return;
    setBusy(true); setError("");
    try {
      await api.upsertProviderKey(activeApiKey, provider, { api_key: value });
      setNotice(`${provider} key saved.`);
      setProviderInput(provider, "");
      await refreshProviders();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function deleteProviderKey(provider) {
    setBusy(true); setError("");
    try {
      await api.removeProviderKey(activeApiKey, provider);
      setNotice(`${provider} key deleted.`);
      await refreshProviders();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  // ── Agent actions ────────────────────────────
  function handleAgentProviderChange(nextProvider) {
    setAgentProvider(nextProvider);
    setAgentModel(normalizeModelForProvider(nextProvider, agentModel));
  }
  async function createAgent(e) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      await api.createAgent(activeApiKey, { name: agentName, role: agentRole, provider: agentProvider, model: agentModel, system_prompt: agentPrompt, tools: agentTools.split(",").map((t) => t.trim()).filter(Boolean) });
      setNotice("Agent created.");
      const a = await api.listAgents(activeApiKey); setAgents(a);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function deleteAgent(id) {
    setBusy(true); setError("");
    try {
      await api.deleteAgent(activeApiKey, id);
      setNotice("Agent deleted.");
      const a = await api.listAgents(activeApiKey); setAgents(a);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function runAgentFromStudio(e) {
    e.preventDefault(); setBusy(true); setError(""); setAgentRunResult(null);
    try {
      const agent = agents.find((a) => String(a.id) === String(agentRunAgentId));
      const selectedServiceSlug = agentRunService || "secure-playground";
      const payload = { objective: agentRunObjective, prompt: agentRunPrompt || agentRunObjective, service_slug: agentRunService, provider: agent?.provider || "openai", model: agent?.model || "gpt-4o-mini", lead_agent_id: agent ? Number(agent.id) : null, collaborator_agent_ids: [], runtime_modules: ["planner", "security", "orchestrator", "secure-playground"] };
      payload.service_slug = selectedServiceSlug;
      payload.runtime_modules = ["planner", "security", "orchestrator", selectedServiceSlug];
      const result = await api.runAgentWorkflow(activeApiKey, payload);
      setAgentRunResult(result);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  // ── Swarm ────────────────────────────────────
  function toggleCollaborator(id) { setSwarmCollaborators((prev) => prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]); }
  async function runSwarm(e) {
    e.preventDefault(); setBusy(true); setError(""); setSwarmResult(null);
    try {
      const payload = { 
        objective: swarmObjective, 
        lead_agent_id: swarmLeadId ? Number(swarmLeadId) : null, 
        collaborator_agent_ids: swarmCollaborators.map(Number) 
      };
      const result = await api.runSwarm(activeApiKey, payload);
      setSwarmResult(result);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  // ── Playground ───────────────────────────────
  async function runPlayground(e) {
    e.preventDefault(); setBusy(true); setError(""); setPlaygroundResult(null);
    try {
      const result = await api.runPlayground({ apiKey: activeApiKey, serviceSlug: playgroundService, prompt: playgroundPrompt, agentId: playgroundAgentId ? Number(playgroundAgentId) : null });
      setPlaygroundResult(result);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function runDashboardPlayground(e) {
    e.preventDefault(); setBusy(true); setError(""); setDashboardResult(null);
    try {
      const result = await api.runPlayground({ apiKey: activeApiKey, serviceSlug: dashboardService, prompt: dashboardPrompt });
      setDashboardResult(result);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  // ── Lab ──────────────────────────────────────
  async function runLab(e) {
    e.preventDefault(); setBusy(true); setLabResult(null);
    try {
      const result = await api.runIntegrationLab(activeApiKey, { language: labLanguage, code: labCode, input_text: labInput });
      setLabResult(result);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  // ── Engine Feature API ───────────────────────
  async function runFeatureApi(e) {
    e.preventDefault(); setBusy(true); setEngineResult(null); setEngineRequestMeta(null); setError("");
    const op = ENGINE_OPERATIONS[engineOperation];
    if (!op) { setBusy(false); return; }
    try {
      let payload = {};
      try { payload = JSON.parse(enginePayload); } catch { payload = op.payload; }
      const started = performance.now();
      const { data, status } = await api.runConsoleRequest(activeApiKey, {
        method: op.method,
        path: op.path,
        payload,
      });
      const durationMs = Math.max(1, Math.round(performance.now() - started));

      if (engineOperation === "vault_encrypt" && data?.encrypted_blob) {
        setLastVaultEncryptedBlob(data.encrypted_blob);
        setLastVaultPassphrase(payload.passphrase || "");
      }

      setEngineResult(data);
      setEngineRequestMeta({
        status,
        duration_ms: durationMs,
        method: op.method,
        path: op.path,
        at: new Date().toISOString(),
      });
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function runSingleAgentTest(e) {
    e.preventDefault();
    if (!singleAgentTestAgentId) {
      setError("Select an agent before running single-agent test.");
      return;
    }
    setBusy(true); setError(""); setSingleAgentTestResult(null);
    try {
      const result = await api.runPlayground({
        apiKey: activeApiKey,
        serviceSlug: singleAgentTestService,
        prompt: singleAgentTestPrompt,
        agentId: Number(singleAgentTestAgentId),
      });
      setSingleAgentTestResult(result);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  // ── Webhook actions ──────────────────────────
  async function createWebhook(e) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      await api.createWebhook(activeApiKey, { url: webhookUrl, secret: webhookSecret || undefined, events: webhookEvents });
      setNotice("Webhook created.");
      const w = await api.listWebhooks(activeApiKey); setWebhooks(w);
      setWebhookUrl(""); setWebhookSecret("");
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function removeWebhook(id) {
    setBusy(true);
    try {
      await api.deleteWebhook(activeApiKey, id);
      setNotice("Webhook deleted.");
      const w = await api.listWebhooks(activeApiKey); setWebhooks(w);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  function toggleWebhookEvent(name) { setWebhookEvents((prev) => prev.includes(name) ? prev.filter((e) => e !== name) : [...prev, name]); }

  // ── Workspace actions ────────────────────────
  async function createWorkspace(e) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      await withBearerRetry((tok) => api.createWorkspace(tok, { name: workspaceName }));
      setNotice("Workspace created.");
      await loadWorkspaces();
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function switchWorkspace(wsId) {
    setBusy(true); setError("");
    try {
      await withBearerRetry((tok) => api.switchWorkspace(tok, wsId));
      setActiveWorkspaceId(wsId);
      setNotice("Workspace switched.");
      await refreshApiKeys();
      if (activeApiKey) await loadSecuredContext(activeApiKey);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  async function addWorkspaceMember(e) {
    e.preventDefault(); setBusy(true); setError("");
    try {
      await withBearerRetry((tok) => api.addWorkspaceMember(tok, activeWorkspaceId, { email: memberEmail, role: memberRole }));
      setNotice("Member added/updated.");
      setMemberEmail("");
      if (activeWorkspaceId) await loadWorkspaceMembers(activeWorkspaceId);
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  // ── Setup section actions ────────────────────
  function setSection(section, field, value) { setSetup((prev) => ({ ...prev, [section]: { ...prev[section], [field]: value } })); }
  async function saveSection(section) {
    setBusy(true); setError("");
    try {
      const fn = { runtime: api.updateRuntimeSetup, cognitive: api.updateCognitiveSetup, security: api.updateSecuritySetup, orchestration: api.updateOrchestrationSetup, observability: api.updateObservabilitySetup, integrations: api.updateIntegrationsSetup }[section];
      if (fn) { await fn(activeApiKey, setup[section]); setNotice(`${section} saved.`); }
    } catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }

  // ── PII Masking dedicated ────────────────────
  async function runPiiMasking(text, reversible = true, options = {}) {
    setBusy(true); setError("");
    try {
      const result = await api.runEngineSecurity(activeApiKey, { text, reversible, ...options });
      return result;
    } catch (err) { setError(err.message); return null; }
    finally { setBusy(false); }
  }

  async function runPdfMasking(file, options = {}) {
    setBusy(true); setError("");
    try {
      const result = await api.runPdfMasking(activeApiKey, file, options);
      return result;
    } catch (err) { setError(err.message); return null; }
    finally { setBusy(false); }
  }

  async function runBiomedMasking(text, threshold = 0.5, labels = null) {
    setBusy(true); setError("");
    try {
      const result = await api.runBiomedMasking(activeApiKey, { text, threshold, labels });
      return result;
    } catch (err) { setError(err.message); return null; }
    finally { setBusy(false); }
  }

  async function runBiomedPdfMasking(file, threshold = 0.5, labels = null) {
    setBusy(true); setError("");
    try {
      const result = await api.runBiomedPdfMasking(activeApiKey, file, threshold, labels);
      return result;
    } catch (err) { setError(err.message); return null; }
    finally { setBusy(false); }
  }

  // ── Jailbreak detection dedicated ────────────
  async function runJailbreakCheck(text) {
    setBusy(true); setError("");
    try {
      const result = await api.runEngineSecurity(activeApiKey, { text, reversible: false });
      return result;
    } catch (err) { setError(err.message); return null; }
    finally { setBusy(false); }
  }

  // ── Vault dedicated ──────────────────────────
  async function vaultEncrypt(plaintext, passphrase) {
    setBusy(true); setError("");
    try {
      const result = await api.runVaultEncrypt(activeApiKey, { plaintext, passphrase });
      if (result?.encrypted_blob) { setLastVaultEncryptedBlob(result.encrypted_blob); setLastVaultPassphrase(passphrase); }
      return result;
    } catch (err) { setError(err.message); return null; }
    finally { setBusy(false); }
  }
  async function vaultDecrypt(blob, passphrase) {
    setBusy(true); setError("");
    try { return await api.runVaultDecrypt(activeApiKey, { encrypted_blob: blob, passphrase }); }
    catch (err) { setError(err.message); return null; }
    finally { setBusy(false); }
  }

  function logout() { clearSession(); setActiveView("dashboard"); }
  function toggleTheme() {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  }
  function copyText(text) {
    navigator.clipboard.writeText(text).then(() => {
      setNotice("");
      setTimeout(() => setNotice("Copied!"), 0);
    });
  }

  // ── Effects ──────────────────────────────────
  useEffect(() => { api.getServices().then(setServices).catch((err) => setError(err.message)); }, []);
  useEffect(() => {
    if (!services.length) return;
    const preferredService = services.find((s) => s.slug === "single-agent-lab")
      || services.find((s) => s.slug === "secure-playground")
      || services[0];
    const allowedAgentTestSlugs = new Set(["single-agent-lab", "secure-playground"]);

    if (!services.some((s) => s.slug === playgroundService)) setPlaygroundService(services[0].slug);
    if (!services.some((s) => s.slug === dashboardService)) setDashboardService(services[0].slug);
    if (!services.some((s) => s.slug === agentRunService) || !allowedAgentTestSlugs.has(agentRunService)) setAgentRunService(preferredService.slug);
    if (!services.some((s) => s.slug === singleAgentTestService) || !allowedAgentTestSlugs.has(singleAgentTestService)) setSingleAgentTestService(preferredService.slug);
  }, [services]);
  useEffect(() => { if (token) { refreshApiKeys(token); loadWorkspaces(token); } }, [token]);
  useEffect(() => { if (isLoggedIn && activeApiKey) loadSecuredContext(activeApiKey); }, [isLoggedIn, activeApiKey]);
  useEffect(() => {
    if (activeView) writeStorage(ACTIVE_VIEW_STORAGE, activeView);
  }, [activeView]);
  useEffect(() => {
    writeStorage(THEME_STORAGE_KEY, theme);
    if (typeof document !== "undefined") {
      document.documentElement.dataset.theme = theme;
      document.documentElement.style.colorScheme = theme;
    }
  }, [theme]);
  useEffect(() => {
    if (isLoggedIn && activeApiKey) loadOpsContext(activeApiKey, activeView);
  }, [isLoggedIn, activeApiKey, activeView]);
  useEffect(() => { if (user?.default_workspace_id) setActiveWorkspaceId(user.default_workspace_id); }, [user]);

  const value = {
    // Theme
    theme, setTheme, toggleTheme,
    // Auth
    mode, setMode, email, setEmail, password, setPassword, token, user, isLoggedIn, authError, authNotice,
    authSubmit, logout, applySession, clearSession,
    // Views
    activeView, setActiveView, activeViewMeta, metrics,
    // API Keys
    apiKeys, apiKeyName, setApiKeyName, newRawKey, setNewRawKey, apiKeyInput, setApiKeyInput,
    activeApiKey, hasActiveKey, activePrefix,
    createKey, activateKey, revokeKey,
    // Providers
    providerStatuses, providerInputs, setProviderInput,
    saveProviderKey, deleteProviderKey, refreshProviders,
    // Setup
    setup, setupUpdatedAt, setSection, saveSection,
    // Features data
    services, featureCatalog, securityFeatures,
    // Agents
    agents, agentName, setAgentName, agentRole, setAgentRole,
    agentProvider, setAgentProvider, agentModel, setAgentModel,
    agentPrompt, setAgentPrompt, agentTools, setAgentTools,
    agentRunAgentId, setAgentRunAgentId, agentRunService, setAgentRunService,
    agentRunObjective, setAgentRunObjective, agentRunPrompt, setAgentRunPrompt,
    agentRunResult, selectedRunAgent, handleAgentProviderChange,
    singleAgentTestAgentId, setSingleAgentTestAgentId,
    singleAgentTestService, setSingleAgentTestService,
    singleAgentTestPrompt, setSingleAgentTestPrompt,
    singleAgentTestResult, createAgent, deleteAgent, runAgentFromStudio, runSingleAgentTest,
    // Swarm
    swarmObjective, setSwarmObjective, swarmLeadId, setSwarmLeadId,
    swarmCollaborators, setSwarmCollaborators, swarmResult,
    toggleCollaborator, runSwarm,
    // Playground
    playgroundService, setPlaygroundService, playgroundAgentId, setPlaygroundAgentId,
    playgroundPrompt, setPlaygroundPrompt, playgroundResult, runPlayground,
    // Dashboard
    dashboardService, setDashboardService, dashboardPrompt, setDashboardPrompt,
    dashboardResult, runDashboardPlayground,
    // Lab
    labLanguage, setLabLanguage, labInput, setLabInput, labCode, setLabCode, labResult, runLab,
    // Engine
    engineOperation, setEngineOperation, enginePayload, setEnginePayload,
    engineResult, engineRequestMeta, engineManifest, lastVaultEncryptedBlob, lastVaultPassphrase, runFeatureApi,
    // PII / Jailbreak / Vault dedicated
    runPiiMasking, runPdfMasking, runBiomedMasking, runBiomedPdfMasking, runJailbreakCheck, vaultEncrypt, vaultDecrypt,
    // Usage/Quotas/Audit
    usageSummary, usageEvents, quotaStatus, auditLogs,
    // Webhooks
    webhooks, webhookDeliveries, webhookUrl, setWebhookUrl,
    webhookSecret, setWebhookSecret, webhookEvents, setWebhookEvents,
    createWebhook, removeWebhook, toggleWebhookEvent,
    // Workspaces
    workspaces, activeWorkspaceId, activeWorkspace,
    workspaceName, setWorkspaceName, workspaceMembers,
    memberEmail, setMemberEmail, memberRole, setMemberRole,
    createWorkspace, switchWorkspace, addWorkspaceMember, loadWorkspaceMembers,
    // Misc
    busy, error, setError, notice, setNotice, copyText, loadOpsContext,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}
