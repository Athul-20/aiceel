import { useApp } from "../context/AppContext";
import { Field, FeaturePageHeader, ResultBadge } from "./Shared";
import * as Icons from "./Icons";

export default function Settings() {
  const {
    activeView, apiKeys, apiKeyName, setApiKeyName, newRawKey, setNewRawKey, apiKeyInput, setApiKeyInput,
    activeApiKey, createKey, activateKey, revokeKey, busy, copyText, // Keys
    providerStatuses, providerInputs, setProviderInput, saveProviderKey, deleteProviderKey, // Providers
    usageSummary, usageEvents, quotaStatus, // Usage
    webhooks, webhookDeliveries, webhookUrl, setWebhookUrl, webhookSecret, setWebhookSecret,
    webhookEvents, toggleWebhookEvent, createWebhook, removeWebhook, // Webhooks
    workspaces, activeWorkspace, workspaceName, setWorkspaceName, workspaceMembers,
    memberEmail, setMemberEmail, memberRole, setMemberRole, createWorkspace, switchWorkspace, addWorkspaceMember // Workspaces
  } = useApp();
  const orderedUsageEvents = [...(usageEvents || [])].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );

  // Determine title and description based on active setting view
  let title = "", desc = "", icon = null;
  if (activeView === "keys") { title = "API Keys"; desc = "Provision and manage API authentication tokens."; icon = <Icons.IconKey />; }
  if (activeView === "providers") { title = "LLM Providers"; desc = "Manage credentials for OpenAI, Groq, and Google."; icon = <Icons.IconProvider />; }
  if (activeView === "usage") { title = "Usage & Quotas"; desc = "Monitor requests, tokens, and billing capacity."; icon = <Icons.IconUsage />; }
  if (activeView === "webhooks") { title = "Webhooks"; desc = "Configure endpoint callbacks for system events."; icon = <Icons.IconWebhook />; }
  if (activeView === "workspaces") { title = "Workspaces"; desc = "Manage team resources and RBAC roles."; icon = <Icons.IconWorkspace />; }

  return (
    <>
      <div className="feature-page">
      <FeaturePageHeader icon={icon} iconBg="var(--surface)" title={title} desc={desc} />

      {activeView === "keys" && (
        <div className="feature-split">
          <section className="card">
            <div className="card-head">
              <h3>Create Key</h3>
              <p>Generate a new environment key.</p>
            </div>
            <form className="form-grid" onSubmit={createKey}>
              <Field label="Key Name"><input value={apiKeyName} onChange={(e) => setApiKeyName(e.target.value)} required /></Field>
              <button className="btn-primary" disabled={busy} type="submit">{busy ? "Creating..." : "Generate Key"}</button>
            </form>
            <hr style={{ border: "1px solid var(--border)", margin: "1.5rem 0" }} />
            
            <div className="card-head">
              <h3>Active Local Key</h3>
              <p>The key currently used by this frontend dashboard.</p>
            </div>
            <form className="form-grid" onSubmit={activateKey}>
              <Field label="API Key">
                <input type="password" value={apiKeyInput} onChange={(e) => setApiKeyInput(e.target.value)} required placeholder="acc_live_..." />
              </Field>
              <button className="btn-ghost btn-full" type="submit">Activate Local Key</button>
            </form>
          </section>

          <section className="card">
            <div className="card-head">
              <h3>Active Keys</h3>
              <p>Keys configured in your workspace.</p>
            </div>
            <div className="sublist stagger-children">
              {apiKeys.map((k) => (
                <article className="sublist-item row" key={k.id}>
                  <div>
                    <h4>{k.name}</h4>
                    <p className="sublist-meta">{k.key_prefix}... • {new Date(k.created_at).toLocaleDateString()}</p>
                    {activeApiKey.startsWith(k.key_prefix) && <ResultBadge type="safe" style={{ marginTop: "0.4rem" }}>Currently Active</ResultBadge>}
                  </div>
                  <button className="btn-danger btn-sm" onClick={() => revokeKey(k.id)}>Revoke</button>
                </article>
              ))}
              {!apiKeys.length && <p className="muted">No active keys.</p>}
            </div>
          </section>
        </div>
      )}

      {activeView === "providers" && (
        <div className="provider-grid stagger-children">
          {providerStatuses.map((p) => (
            <section className="card compact" key={p.provider}>
              <div className="card-head">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <h3 style={{ textTransform: "capitalize" }}>{p.provider}</h3>
                  <ResultBadge type={p.is_configured ? "safe" : "neutral"}>{p.is_configured ? "Configured" : "Missing"}</ResultBadge>
                </div>
                {p.is_configured && <p className="muted" style={{ marginTop: "0.2rem" }}>Active Key: {p.prefix}...</p>}
              </div>
              <form className="form-grid" onSubmit={(e) => { e.preventDefault(); saveProviderKey(p.provider); }}>
                <Field label="API Key">
                  <input type="password" value={providerInputs[p.provider] || ""} onChange={(e) => setProviderInput(p.provider, e.target.value)} placeholder="sk-..." required />
                </Field>
                <div className="row">
                  <button className="btn-primary" disabled={busy} type="submit">Save</button>
                  {p.is_configured && <button className="btn-danger" disabled={busy} type="button" onClick={() => deleteProviderKey(p.provider)}>Delete</button>}
                </div>
              </form>
            </section>
          ))}
        </div>
      )}

      {activeView === "usage" && (
        <div className="usage-layout">
          <section className="card usage-summary-card">
            <div className="card-head">
              <h3>Monthly Aggregation</h3>
              <p>Current billing period usage.</p>
            </div>
            {usageSummary ? (
              <div className="stats-row">
                <article className="stat-card"><span>Total Units</span><strong>{usageSummary.usage.unit_count}</strong></article>
                <article className="stat-card"><span>Tokens Used</span><strong>{usageSummary.usage.token_count}</strong></article>
                <article className="stat-card"><span>Requests Executed</span><strong>{usageSummary.usage.request_count}</strong></article>
                <article className="stat-card"><span>Plan Quota</span><strong>{quotaStatus?.quota?.monthly_usage_budget ?? "∞"}</strong></article>
                <article className="stat-card"><span>Overage Enforced</span><strong>{quotaStatus?.quota?.enforce_limits ? "Yes" : "No"}</strong></article>
              </div>
            ) : <p className="muted">Loading usage statistics...</p>}
          </section>
          <section className="card usage-events-card">
            <div className="card-head usage-events-head">
              <h3>Recent Traffic</h3>
              <p>{orderedUsageEvents.length} events</p>
            </div>
            <div className="usage-events-scroll">
              <div className="sublist stagger-children">
                {orderedUsageEvents.map((e) => (
                  <article className="sublist-item row" key={e.id}>
                    <div>
                      <h4>{e.feature}</h4>
                      <p className="sublist-meta">units={e.units} | tokens={e.tokens} | {e.runtime_ms}ms</p>
                    </div>
                    <p className="muted">{new Date(e.created_at).toLocaleString()}</p>
                  </article>
                ))}
              </div>
              {!orderedUsageEvents.length && <p className="muted">No usage events recorded yet.</p>}
            </div>
          </section>
        </div>
      )}

      {activeView === "webhooks" && (
        <div className="feature-split">
          <section className="card">
            <div className="card-head">
              <h3>Add Webhook</h3>
              <p>Configure an endpoint to receive system events.</p>
            </div>
            <form className="form-grid" onSubmit={createWebhook}>
              <Field label="URL Protocol">
                <input type="url" value={webhookUrl} onChange={(e) => setWebhookUrl(e.target.value)} required placeholder="https://..." />
              </Field>
              <Field label="Signing Secret (Optional)">
                <input value={webhookSecret} onChange={(e) => setWebhookSecret(e.target.value)} />
              </Field>
              <div className="field">
                <span>Subscribed Events</span>
                <div className="chip-grid">
                  {["workflow.completed", "workflow.failed", "quota.warning", "security.threat"].map((ev) => (
                    <label className="chip" key={ev}>
                      <input type="checkbox" checked={webhookEvents.includes(ev)} onChange={() => toggleWebhookEvent(ev)} />
                      <span>{ev}</span>
                    </label>
                  ))}
                </div>
              </div>
              <button className="btn-primary" disabled={busy} type="submit">Create Hook</button>
            </form>
          </section>

          <section className="card">
            <div className="card-head"><h3>Active Endpoints</h3></div>
            <div className="sublist stagger-children">
              {webhooks.map((w) => (
                <article className="sublist-item row" key={w.id}>
                  <div>
                    <h4>{w.url}</h4>
                    <p className="sublist-meta">Events: {w.events.join(", ")}</p>
                  </div>
                  <button className="btn-danger btn-sm" onClick={() => removeWebhook(w.id)}>Remove</button>
                </article>
              ))}
              {!webhooks.length && <p className="muted">No webhooks attached.</p>}
            </div>
            
            <div className="card-head" style={{ marginTop: "1.5rem" }}><h3>Recent Deliveries</h3></div>
            <div className="sublist stagger-children">
              {webhookDeliveries.map((w) => (
                <article className="sublist-item row" key={w.id}>
                  <div>
                    <h4>{w.event}</h4>
                    <p className="sublist-meta">Code: {w.status_code} • {new Date(w.created_at).toLocaleString()}</p>
                  </div>
                  <ResultBadge type={w.status_code === 200 ? "safe" : "danger"}>HTTP {w.status_code}</ResultBadge>
                </article>
              ))}
              {!webhookDeliveries.length && <p className="muted">No delivery logs tracked yet.</p>}
            </div>
          </section>
        </div>
      )}

      {activeView === "workspaces" && (
        <div className="feature-split">
          <section className="card">
            <div className="card-head">
              <h3>Active Context</h3>
              <p>You are managing resources in <strong style={{ color: "var(--accent)" }}>{activeWorkspace?.name || "Unknown"}</strong>.</p>
            </div>
            <form className="form-grid" onSubmit={createWorkspace}>
              <Field label="New Workspace Name">
                <input value={workspaceName} onChange={(e) => setWorkspaceName(e.target.value)} required />
              </Field>
              <button className="btn-primary" disabled={busy} type="submit">Create Hub</button>
            </form>
            
            <div className="card-head" style={{ marginTop: "1rem" }}>
              <h3>Available Workspaces</h3>
            </div>
            <div className="sublist stagger-children">
              {workspaces.map((w) => (
                <article className="sublist-item row" key={w.id}>
                  <div>
                    <h4>{w.name}</h4>
                    <p className="sublist-meta">ID: {w.id}</p>
                  </div>
                  {activeWorkspace?.id === w.id ? (
                    <ResultBadge type="safe">Active</ResultBadge>
                  ) : (
                    <button className="btn-ghost btn-sm" onClick={() => switchWorkspace(w.id)}>Switch Context</button>
                  )}
                </article>
              ))}
            </div>
          </section>

          <section className="card">
            <div className="card-head">
              <h3>Invite Member</h3>
              <p>Add people to <strong style={{color: "var(--accent)"}}>{activeWorkspace?.name}</strong>.</p>
            </div>
            <form className="form-grid" onSubmit={addWorkspaceMember}>
              <Field label="Identity">
                <input type="email" value={memberEmail} onChange={(e) => setMemberEmail(e.target.value)} required placeholder="user@domain.com" />
              </Field>
              <Field label="RBAC Policy">
                <select value={memberRole} onChange={(e) => setMemberRole(e.target.value)}>
                  <option value="owner">Owner (Full Admin)</option>
                  <option value="admin">Admin (Keys & Billing)</option>
                  <option value="developer">Developer (Playground Access)</option>
                  <option value="viewer">Viewer (Read Logs)</option>
                </select>
              </Field>
              <button className="btn-primary" disabled={busy} type="submit">Grant Access</button>
            </form>
            
            <div className="card-head" style={{ marginTop: "1rem" }}>
              <h3>Current Access Matrix</h3>
            </div>
            <div className="sublist stagger-children">
              {workspaceMembers.map((m) => (
                <article className="sublist-item row" key={m.id}>
                  <div>
                    <h4>{m.email}</h4>
                    <p className="sublist-meta" style={{ textTransform: "uppercase" }}>{m.role}</p>
                  </div>
                </article>
              ))}
              {!workspaceMembers.length && <p className="muted">No explicit members in matrix. Owner overrides apply.</p>}
            </div>
          </section>
        </div>
      )}
    </div>

      {newRawKey && (
        <div className="popup-overlay">
          <div className="popup-box">
            <h2>Save Your New API Key</h2>
            <p>This key will only be shown once. Please store it somewhere safe immediately. It has been automatically activated for your local session.</p>
            <div className="key-display">{newRawKey}</div>
            <div style={{ display: "flex", gap: "1rem" }}>
              <button className="btn-ghost btn-full" onClick={() => copyText(newRawKey)}>Copy to Clipboard</button>
              <button className="btn-primary btn-full" onClick={() => setNewRawKey("")}>I Have Saved It</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
