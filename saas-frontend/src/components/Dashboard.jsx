import { useState, useEffect } from "react";
import { useApp } from "../context/AppContext";
import { DASHBOARD_FEATURES } from "../constants";
import { api } from "../api";
import * as Icons from "./Icons";

const ICON_MAP = {
  dashboard: Icons.IconDashboard,
  console: Icons.IconConsole,
  pii: Icons.IconPII,
  biomed: Icons.IconBioMed,
  shield: Icons.IconShield,
  datalab: Icons.IconDataLab,
  vault: Icons.IconVault,
  sandbox: Icons.IconSandbox,
  agent: Icons.IconAgent,
  swarm: Icons.IconSwarm,
  playground: Icons.IconPlayground,
};

export default function Dashboard() {
  const { setActiveView, metrics, providerStatuses, agents, hasActiveKey, activeWorkspace, activeApiKey, usageEvents } = useApp();
  const [hwStats, setHwStats] = useState(null);
  
  const configuredProviders = providerStatuses.filter((i) => i.is_configured).length;
  const recentEvents = (usageEvents || []).slice(0, 5);

  const fetchHw = async () => {
    if (!activeApiKey) return;
    try {
      const res = await api.getHardwareStats(activeApiKey);
      setHwStats(res);
    } catch (err) {
      console.error("Dashboard HW fetch failed", err);
    }
  };

  useEffect(() => {
    fetchHw();
    const timer = setInterval(fetchHw, 5000);
    return () => clearInterval(timer);
  }, [activeApiKey]);

  return (
    <div className="dashboard-grid">
      <section className="hero-section">
        <p className="eyebrow">AICCEL Platform</p>
        <h2>Build secure AI agents with enterprise-grade features.</h2>
        <p>
          PII masking, jailbreak detection, vault encryption, sandboxed execution, and multi-agent orchestration —
          all from one platform. Select a feature below to get started.
        </p>
        <div className="hero-actions">
          <button className="btn-primary" type="button" onClick={() => setActiveView("agents")}>Build an Agent</button>
          <button className="btn-ghost" type="button" onClick={() => setActiveView("playground")}>Open Playground</button>
          <button className="btn-ghost" type="button" onClick={() => setActiveView("console")}>Console</button>
        </div>
      </section>

      {/* SYSTEM HEALTH MONITOR */}
      <section className="dashboard-bridge-stats">
         <div className="bridge-card stats-main">
            <div className="bridge-head">
               <Icons.IconShield size={18} />
               <h3>System Health & Hardware Gating</h3>
            </div>
            <div className="bridge-body">
               <div className="hw-mini-grid">
                  {Array.from({ length: hwStats?.logical_cores || 8 }).map((_, i) => {
                    const isActive = i < (hwStats?.current_affinity_count || 1);
                    const risk = hwStats?.risk_level || "low";
                    return (
                      <div key={i} className={`hw-dot ${isActive ? `active ${risk}` : ""}`} title={`Core ${i}: ${isActive ? 'Locked' : 'Available'}`} />
                    );
                  })}
               </div>
               <div className="hw-meta">
                  <div className="hw-meta-item">
                     <span>Cores Isolated</span>
                     <strong>{hwStats?.current_affinity_count || 1} / {hwStats?.logical_cores || 8}</strong>
                  </div>
                  <div className="hw-meta-item">
                     <span>Priority Class</span>
                     <strong className={hwStats?.risk_level === 'critical' ? 'v-danger' : ''}>{hwStats?.priority_class || 'Normal'}</strong>
                  </div>
                  <div className="hw-meta-item">
                     <span>Engine Status</span>
                     <strong style={{ color: "var(--green)" }}>Protected</strong>
                  </div>
               </div>
            </div>
         </div>
      </section>

      <div className="stats-row stagger-children">
        <article className="stat-card">
          <span>Providers</span>
          <strong>{configuredProviders}</strong>
        </article>
        <article className="stat-card">
          <span>Agents</span>
          <strong>{agents.length}</strong>
        </article>
        {metrics.slice(0, 4).map(([label, value]) => (
          <article className="stat-card" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </article>
        ))}
      </div>

      <div className="feature-cards-grid stagger-children">
        {DASHBOARD_FEATURES.map((feat) => {
          const IconComp = ICON_MAP[feat.icon];
          return (
            <article
              className={`feature-hero-card fhc-${feat.color}`}
              key={feat.id}
              onClick={() => setActiveView(feat.id)}
            >
              <div className="fhc-icon">
                {IconComp ? <IconComp /> : null}
              </div>
              <h4>{feat.title}</h4>
              <p>{feat.desc}</p>
              <span className="fhc-tag">{feat.tag}</span>
            </article>
          );
        })}
      </div>

      <div className="feature-split">
        <section className="card">
          <div className="card-head">
            <h3>Setup Status</h3>
            <p>Live readiness checks for your workspace.</p>
          </div>
          <div className="status-list">
            {[
              { label: "API Key", value: hasActiveKey ? "Active" : "Required", good: hasActiveKey },
              { label: "Providers", value: configuredProviders ? `${configuredProviders} configured` : "Required", good: configuredProviders > 0 },
              { label: "Agents", value: agents.length ? `${agents.length} ready` : "Create one", good: agents.length > 0 },
              { label: "Workspace", value: activeWorkspace ? activeWorkspace.name : "No workspace", good: Boolean(activeWorkspace) },
            ].map((item) => (
              <article className="status-item" key={item.label}>
                <p>{item.label}</p>
                <span className={item.good ? "badge good" : "badge"}>{item.value}</span>
              </article>
            ))}
          </div>
          <button className="btn-ghost" type="button" onClick={() => setActiveView("keys")}>Manage API Keys</button>
        </section>

        <section className="card">
          <div className="card-head">
            <h3>Recent Activity</h3>
            <p>Latest API traffic from your workspace.</p>
          </div>
          {recentEvents.length ? (
            <div className="sublist">
              {recentEvents.map((event) => (
                <article className="sublist-item row" key={event.id}>
                  <div>
                    <h4>{event.feature}</h4>
                    <p className="sublist-meta">units={event.units} | tokens={event.tokens} | {event.runtime_ms}ms</p>
                  </div>
                  <p className="muted">{new Date(event.created_at).toLocaleString()}</p>
                </article>
              ))}
            </div>
          ) : (
            <p className="muted">No recent events yet.</p>
          )}
          <button className="btn-ghost" type="button" onClick={() => setActiveView("usage")}>View All Usage</button>
        </section>
      </div>
    </div>
  );
}
