import { useEffect, useMemo, useState } from "react";
import { useApp } from "../context/AppContext";
import { Field, FeaturePageHeader, ResultBadge } from "./Shared";
import * as Icons from "./Icons";

const USAGE_CHART_COLORS = ["#2563eb", "#f59e0b", "#16a34a"];

function titleCase(value) {
  return String(value || "")
    .split(/[\s._/-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function getUsageCategory(feature) {
  const raw = String(feature || "");
  if (raw.startsWith("request:")) {
    const path = raw.split(" ")[1] || "";
    const segments = path.split("/").filter(Boolean);
    const section = segments[1] || segments[0] || "api";
    return `${titleCase(section)} API`;
  }
  return `${titleCase(raw.split(".")[0] || "other")} Features`;
}

function formatBucketLabel(timestamp, totalSpanMs) {
  const date = new Date(timestamp);
  const timeLabel = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  if (totalSpanMs >= 24 * 60 * 60 * 1000) {
    return `${date.toLocaleDateString([], { month: "short", day: "numeric" })} ${timeLabel}`;
  }
  return timeLabel;
}

function buildTimeSeries(events, keyFn, options = {}) {
  const { maxSeries = 3, bucketCount = 8 } = options;
  const orderedEvents = [...(events || [])]
    .map((event) => ({ ...event, timestamp: new Date(event.created_at).getTime() }))
    .filter((event) => Number.isFinite(event.timestamp))
    .sort((a, b) => a.timestamp - b.timestamp);

  if (!orderedEvents.length) {
    return { buckets: [], series: [], maxValue: 0 };
  }

  const totals = new Map();
  for (const event of orderedEvents) {
    const label = keyFn(event);
    const current = totals.get(label) || { label, units: 0, calls: 0 };
    current.units += Number(event.units || 0);
    current.calls += 1;
    totals.set(label, current);
  }

  const topLabels = Array.from(totals.values())
    .sort((a, b) => b.units - a.units || b.calls - a.calls)
    .slice(0, maxSeries)
    .map((item) => item.label);

  if (!topLabels.length) {
    return { buckets: [], series: [], maxValue: 0 };
  }

  const firstTimestamp = orderedEvents[0].timestamp;
  const lastTimestamp = orderedEvents[orderedEvents.length - 1].timestamp;
  const totalSpanMs = Math.max(lastTimestamp - firstTimestamp, 60 * 1000);
  const safeBucketCount = Math.min(bucketCount, Math.max(4, orderedEvents.length));
  const bucketSizeMs = Math.max(Math.ceil(totalSpanMs / safeBucketCount), 60 * 1000);
  const actualBucketCount = Math.max(1, Math.floor(totalSpanMs / bucketSizeMs) + 1);
  const bucketValues = Array.from({ length: actualBucketCount }, (_, index) => {
    const start = firstTimestamp + index * bucketSizeMs;
    return {
      key: `${start}`,
      label: formatBucketLabel(start, totalSpanMs),
      values: new Map(topLabels.map((item) => [item, 0])),
    };
  });

  for (const event of orderedEvents) {
    const label = keyFn(event);
    if (!topLabels.includes(label)) continue;
    const bucketIndex = Math.min(
      bucketValues.length - 1,
      Math.floor((event.timestamp - firstTimestamp) / bucketSizeMs)
    );
    const bucket = bucketValues[bucketIndex];
    bucket.values.set(label, (bucket.values.get(label) || 0) + Number(event.units || 0));
  }

  const series = topLabels.map((label, index) => ({
    label,
    color: USAGE_CHART_COLORS[index % USAGE_CHART_COLORS.length],
    totalUnits: totals.get(label)?.units || 0,
    values: bucketValues.map((bucket) => bucket.values.get(label) || 0),
  }));
  const maxValue = Math.max(1, ...series.flatMap((item) => item.values));

  return {
    buckets: bucketValues.map(({ key, label }) => ({ key, label })),
    series,
    maxValue,
  };
}

function UsageLineChart({ title, subtitle, data }) {
  const [selectedLabels, setSelectedLabels] = useState([]);
  const [hoveredIndex, setHoveredIndex] = useState(null);

  const visibleSeries = useMemo(
    () => (selectedLabels.length
      ? data.series.filter((series) => selectedLabels.includes(series.label))
      : data.series),
    [data.series, selectedLabels]
  );

  if (!data.series.length || !data.buckets.length) {
    return (
      <section className="usage-graph-card">
        <div className="card-head">
          <h4>{title}</h4>
          <p>{subtitle}</p>
        </div>
        <p className="muted">Not enough recent activity to plot yet.</p>
      </section>
    );
  }

  const width = 360;
  const height = 180;
  const paddingX = 18;
  const paddingTop = 14;
  const paddingBottom = 18;
  const chartWidth = width - paddingX * 2;
  const chartHeight = height - paddingTop - paddingBottom;
  const maxValue = Math.max(1, ...visibleSeries.flatMap((series) => series.values));
  const xStep = data.buckets.length > 1 ? chartWidth / (data.buckets.length - 1) : 0;
  const axisIndexes = Array.from(new Set([0, Math.floor((data.buckets.length - 1) / 2), data.buckets.length - 1]));
  const safeHoveredIndex = hoveredIndex == null ? data.buckets.length - 1 : hoveredIndex;
  const tooltipLeft = data.buckets.length === 1
    ? 50
    : (safeHoveredIndex / Math.max(1, data.buckets.length - 1)) * 100;
  const tooltipValues = visibleSeries
    .map((series) => ({
      label: series.label,
      color: series.color,
      units: series.values[safeHoveredIndex] || 0,
    }))
    .sort((a, b) => b.units - a.units);

  function toggleSeries(label) {
    setSelectedLabels((current) => (
      current.includes(label)
        ? current.filter((item) => item !== label)
        : [...current, label]
    ));
  }

  return (
    <section className="usage-graph-card">
      <div className="card-head">
        <h4>{title}</h4>
        <p>{subtitle}</p>
      </div>
      <div className="usage-line-legend">
        {data.series.map((series) => (
          <button
            className={`usage-line-legend-item ${!selectedLabels.length || selectedLabels.includes(series.label) ? "active" : "muted"}`}
            key={series.label}
            type="button"
            onClick={() => toggleSeries(series.label)}
          >
            <span className="usage-line-swatch" style={{ background: series.color }} />
            <strong title={series.label}>{series.label}</strong>
            <span>{series.totalUnits}u</span>
          </button>
        ))}
      </div>
      <div className="usage-line-shell" onMouseLeave={() => setHoveredIndex(null)}>
        {hoveredIndex != null ? (
          <div className="usage-line-tooltip" style={{ left: `${tooltipLeft}%` }}>
            <strong>{data.buckets[safeHoveredIndex]?.label}</strong>
            {tooltipValues.map((item) => (
              <span key={`${title}-${item.label}`}>
                <i style={{ background: item.color }} />
                {item.label}: {item.units}u
              </span>
            ))}
          </div>
        ) : null}
        <svg
          className="usage-line-svg"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`${title} line chart`}
        >
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
            const y = paddingTop + chartHeight - chartHeight * ratio;
            return <line className="usage-line-grid" key={ratio} x1={paddingX} y1={y} x2={width - paddingX} y2={y} />;
          })}
          {hoveredIndex != null ? (
            <line
              className="usage-line-focus"
              x1={paddingX + (data.buckets.length === 1 ? chartWidth / 2 : safeHoveredIndex * xStep)}
              y1={paddingTop}
              x2={paddingX + (data.buckets.length === 1 ? chartWidth / 2 : safeHoveredIndex * xStep)}
              y2={paddingTop + chartHeight}
            />
          ) : null}
          {visibleSeries.map((series) => {
            const points = series.values
              .map((value, index) => {
                const x = paddingX + (data.buckets.length === 1 ? chartWidth / 2 : index * xStep);
                const y = paddingTop + chartHeight - (value / maxValue) * chartHeight;
                return `${x},${y}`;
              })
              .join(" ");

            return (
              <g key={series.label}>
                <polyline className="usage-line-path" fill="none" points={points} stroke={series.color} />
                {series.values.map((value, index) => {
                  const x = paddingX + (data.buckets.length === 1 ? chartWidth / 2 : index * xStep);
                  const y = paddingTop + chartHeight - (value / maxValue) * chartHeight;
                  return (
                    <circle
                      className={`usage-line-dot ${hoveredIndex === index ? "is-active" : ""}`}
                      key={`${series.label}-${index}`}
                      cx={x}
                      cy={y}
                      r={hoveredIndex === index ? "4.5" : "3.5"}
                      fill={series.color}
                    />
                  );
                })}
              </g>
            );
          })}
          {data.buckets.map((bucket, index) => {
            const widthPerBucket = data.buckets.length === 1 ? chartWidth : chartWidth / data.buckets.length;
            const x = data.buckets.length === 1
              ? paddingX
              : paddingX + index * xStep - widthPerBucket / 2;
            return (
              <rect
                key={`${bucket.key}-hit`}
                className="usage-line-hitbox"
                x={Math.max(paddingX, x)}
                y={paddingTop}
                width={Math.max(18, widthPerBucket)}
                height={chartHeight}
                fill="transparent"
                onMouseEnter={() => setHoveredIndex(index)}
              />
            );
          })}
        </svg>
        <div className="usage-line-axis">
          {axisIndexes.map((index) => (
            <span key={`${data.buckets[index].key}-axis`}>{data.buckets[index].label}</span>
          ))}
        </div>
      </div>
    </section>
  );
}

export default function Settings() {
  const [pendingRevokeKey, setPendingRevokeKey] = useState(null);
  const [revokeConfirmationText, setRevokeConfirmationText] = useState("");
  const [usageSource, setUsageSource] = useState("workspace");
  const [selectedUsageApiKeyId, setSelectedUsageApiKeyId] = useState("all");
  const [usageLoading, setUsageLoading] = useState(false);
  const [scopedUsageSummary, setScopedUsageSummary] = useState(null);
  const [scopedUsageEvents, setScopedUsageEvents] = useState([]);
  const {
    activeView, apiKeys, apiKeyName, setApiKeyName, newRawKey, setNewRawKey,
    createKey, revokeKey, busy, copyText, // Keys
    providerStatuses, providerInputs, setProviderInput, saveProviderKey, deleteProviderKey, // Providers
    quotaStatus, fetchUsageAnalytics, // Usage
    webhooks, webhookDeliveries, webhookUrl, setWebhookUrl, webhookSecret, setWebhookSecret,
    webhookEvents, toggleWebhookEvent, createWebhook, removeWebhook, // Webhooks
    workspaces, activeWorkspace, workspaceName, setWorkspaceName, workspaceMembers,
    memberEmail, setMemberEmail, memberRole, setMemberRole, createWorkspace, switchWorkspace, addWorkspaceMember // Workspaces
  } = useApp();
  const orderedUsageEvents = [...(scopedUsageEvents || [])].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
  const revokeTextMatches = useMemo(() => revokeConfirmationText.trim() === "REVOKE", [revokeConfirmationText]);
  const selectedUsageApiKey = useMemo(
    () => apiKeys.find((item) => String(item.id) === String(selectedUsageApiKeyId)) || null,
    [apiKeys, selectedUsageApiKeyId]
  );
  const endpointUsage = useMemo(
    () => buildTimeSeries(orderedUsageEvents, (event) => event.feature),
    [orderedUsageEvents]
  );
  const categoryUsage = useMemo(
    () => buildTimeSeries(orderedUsageEvents, (event) => getUsageCategory(event.feature)),
    [orderedUsageEvents]
  );

  useEffect(() => {
    if (!pendingRevokeKey) return undefined;

    function handleKeyDown(event) {
      if (event.key === "Escape" && !busy) {
        setPendingRevokeKey(null);
        setRevokeConfirmationText("");
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [pendingRevokeKey, busy]);

  useEffect(() => {
    if (activeView !== "usage") return undefined;

    let cancelled = false;
    const options = {
      source: usageSource,
      ...(usageSource === "api" && selectedUsageApiKeyId !== "all" ? { api_key_id: selectedUsageApiKeyId } : {}),
    };

    setUsageLoading(true);
    fetchUsageAnalytics(options)
      .then(({ summary, events }) => {
        if (cancelled) return;
        setScopedUsageSummary(summary);
        setScopedUsageEvents(events || []);
      })
      .catch(() => {
        if (cancelled) return;
        setScopedUsageSummary(null);
        setScopedUsageEvents([]);
      })
      .finally(() => {
        if (!cancelled) setUsageLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [activeView, usageSource, selectedUsageApiKeyId]);

  function requestRevoke(key) {
    setPendingRevokeKey(key);
    setRevokeConfirmationText("");
  }

  function cancelRevoke() {
    if (busy) return;
    setPendingRevokeKey(null);
    setRevokeConfirmationText("");
  }

  async function confirmRevoke() {
    if (!pendingRevokeKey || !revokeTextMatches || busy) return;
    await revokeKey(pendingRevokeKey.id);
    setPendingRevokeKey(null);
    setRevokeConfirmationText("");
  }

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
              <p>Generate a new API key for external clients, scripts, and direct API access.</p>
            </div>
            <form className="form-grid" onSubmit={createKey}>
              <Field label="Key Name"><input value={apiKeyName} onChange={(e) => setApiKeyName(e.target.value)} required /></Field>
              <button className="btn-primary" disabled={busy} type="submit">{busy ? "Creating..." : "Generate Key"}</button>
            </form>
            <hr style={{ border: "1px solid var(--border)", margin: "1.5rem 0" }} />
            
            <div className="card-head">
              <h3>Dashboard Access</h3>
              <p>Logged-in dashboard activity now uses your workspace session. API keys here are for external clients, scripts, and direct API integrations.</p>
            </div>
            <div className="sublist">
              <article className="sublist-item">
                <h4>Session Auth</h4>
                <p className="sublist-meta">PII, Playground, Console, Vault, Sandbox, Agents, and other in-app features run with your signed-in account session.</p>
              </article>
              <article className="sublist-item">
                <h4>External Access</h4>
                <p className="sublist-meta">Use generated API keys when calling the public API from outside this dashboard. Only the key prefix is visible after creation.</p>
              </article>
            </div>
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
                  </div>
                  <button className="btn-danger btn-sm" type="button" onClick={() => requestRevoke(k)}>Revoke</button>
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
            <div className="usage-filter-bar">
              <div className="auth-switch usage-source-switch">
                <button
                  className={usageSource === "workspace" ? "active" : ""}
                  type="button"
                  onClick={() => setUsageSource("workspace")}
                >
                  Workspace
                </button>
                <button
                  className={usageSource === "api" ? "active" : ""}
                  type="button"
                  onClick={() => setUsageSource("api")}
                >
                  API
                </button>
              </div>
              {usageSource === "api" ? (
                <select
                  className="usage-key-select"
                  value={selectedUsageApiKeyId}
                  onChange={(event) => setSelectedUsageApiKeyId(event.target.value)}
                >
                  <option value="all">All API Keys</option>
                  {apiKeys.map((key) => (
                    <option key={key.id} value={key.id}>{key.name}</option>
                  ))}
                </select>
              ) : null}
            </div>
            {scopedUsageSummary ? (
              <div className="stats-row">
                <article className="stat-card"><span>Total Units</span><strong>{scopedUsageSummary.usage.unit_count}</strong></article>
                <article className="stat-card"><span>Tokens Used</span><strong>{scopedUsageSummary.usage.token_count}</strong></article>
                <article className="stat-card"><span>Requests Executed</span><strong>{scopedUsageSummary.usage.request_count}</strong></article>
                <article className="stat-card"><span>Tracked Scope</span><strong>{usageSource === "workspace" ? "Workspace" : (selectedUsageApiKey?.name || "All API Keys")}</strong></article>
                <article className="stat-card"><span>Monthly Limit</span><strong>{quotaStatus?.limit_units?.toLocaleString?.() ?? scopedUsageSummary?.limits?.monthly_units?.toLocaleString?.() ?? "N/A"}</strong></article>
                <article className="stat-card"><span>Remaining Units</span><strong>{quotaStatus?.remaining_units?.toLocaleString?.() ?? "N/A"}</strong></article>
              </div>
            ) : <p className="muted">{usageLoading ? "Loading usage statistics..." : "No usage statistics available."}</p>}
          </section>
          <section className="card usage-events-card">
            <div className="card-head usage-events-head">
              <h3>Recent Traffic</h3>
              <p>{usageLoading ? "Loading..." : `${orderedUsageEvents.length} events`}</p>
            </div>
            {orderedUsageEvents.length ? (
              <div className="usage-graph-grid">
                <UsageLineChart
                  title="By Endpoint"
                  subtitle="Billed units over time for the busiest recent endpoints."
                  data={endpointUsage}
                />
                <UsageLineChart
                  title="By Category"
                  subtitle="Recent traffic patterns grouped by service area."
                  data={categoryUsage}
                />
              </div>
            ) : !usageLoading ? (
              <p className="muted">
                {usageSource === "api" ? "No API usage events recorded yet for this selection." : "No workspace usage events recorded yet."}
              </p>
            ) : null}
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
            <p>This key will only be shown once. Please store it somewhere safe immediately. Use it for external API access, scripts, or integrations.</p>
            <div className="key-display">{newRawKey}</div>
            <div style={{ display: "flex", gap: "1rem" }}>
              <button className="btn-ghost btn-full" onClick={() => copyText(newRawKey)}>Copy to Clipboard</button>
              <button className="btn-primary btn-full" onClick={() => setNewRawKey("")}>I Have Saved It</button>
            </div>
          </div>
        </div>
      )}

      {pendingRevokeKey ? (
        <div className="popup-overlay" onClick={cancelRevoke} role="presentation">
          <div
            className="popup-box confirm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="revoke-confirm-title"
            aria-describedby="revoke-confirm-description"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="confirm-dialog-icon" aria-hidden="true">
              <Icons.IconKey />
            </div>
            <h2 id="revoke-confirm-title">Revoke this API key?</h2>
            <p id="revoke-confirm-description">
              This will immediately disable <strong>{pendingRevokeKey.name}</strong> for this workspace. Type <strong>REVOKE</strong> below to confirm.
            </p>
            <div className="field revoke-confirm-field">
              <span>Confirmation Text</span>
              <input
                autoFocus
                value={revokeConfirmationText}
                onChange={(event) => setRevokeConfirmationText(event.target.value)}
                placeholder="Type REVOKE"
              />
              <small className="muted revoke-confirm-hint">Exact match required.</small>
            </div>
            <div className="confirm-actions">
              <button className="btn-ghost btn-full" type="button" onClick={cancelRevoke} disabled={busy}>
                Cancel
              </button>
              <button className="btn-danger btn-full" type="button" onClick={confirmRevoke} disabled={!revokeTextMatches || busy}>
                {busy ? "Revoking..." : "Revoke Key"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}


