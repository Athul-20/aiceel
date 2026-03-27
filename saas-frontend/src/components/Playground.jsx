import { useApp } from "../context/AppContext";
import { Field, FeaturePageHeader, ResultPanel, ResultBadge } from "./Shared";
import * as Icons from "./Icons";

export default function Playground() {
  const {
    services, agents, playgroundService, setPlaygroundService,
    playgroundAgentId, setPlaygroundAgentId, playgroundPrompt, setPlaygroundPrompt,
    playgroundResult, runPlayground, busy, hasActiveKey, setActiveView
  } = useApp();

  return (
    <div className="feature-page">
      <FeaturePageHeader
        icon={<Icons.IconPlayground />}
        iconBg="var(--pink-soft)"
        title="Unified Playground"
        desc="Run prompts through any AICCEL service with live policy checks, security screening, and full configuration snapshots."
      />

      {!hasActiveKey && (
        <div className="key-alert">
          <span>Activate an API key to use the playground.</span>
          <button className="btn-ghost btn-sm" onClick={() => setActiveView("keys")}>Get API Key</button>
        </div>
      )}

      <div className="feature-split">
        <section className="card">
          <div className="card-head">
            <h3>Execution Config</h3>
            <p>Target a service and an optional agent.</p>
          </div>
          <form className="form-grid" onSubmit={runPlayground}>
            <Field label="Service">
              <select value={playgroundService} onChange={(e) => setPlaygroundService(e.target.value)}>
                {services.map((s) => <option key={s.slug} value={s.slug}>{s.name}</option>)}
                {!services.length && <option value="secure-playground">Secure Playground</option>}
              </select>
            </Field>
            <Field label="Agent Binding (Optional)">
              <select value={playgroundAgentId} onChange={(e) => setPlaygroundAgentId(e.target.value)}>
                <option value="">None (Use service defaults)</option>
                {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </Field>
            <Field label="Prompt">
              <textarea rows={6} value={playgroundPrompt} onChange={(e) => setPlaygroundPrompt(e.target.value)} required placeholder="Enter a prompt to run through the security and execution engine..." />
            </Field>
            <button className="btn-primary btn-full" disabled={busy || !hasActiveKey} type="submit">
              {busy ? "Executing..." : "Run Request"}
            </button>
          </form>
        </section>

        <section className="card">
          <div className="card-head">
            <h3>Playground Trace</h3>
            <p>Comprehensive response and security report.</p>
          </div>
          
          {playgroundResult ? (
            <>
              <div className="result-badges" style={{ marginBottom: "1rem" }}>
                <ResultBadge type="info">{playgroundResult.service_name}</ResultBadge>
                {playgroundResult.agent_used && <ResultBadge type="neutral">{playgroundResult.agent_used}</ResultBadge>}
                <ResultBadge type={playgroundResult.security_report?.risk_score > 0.5 ? "warn" : "safe"}>
                  Risk: {playgroundResult.security_report?.risk_score || 0}
                </ResultBadge>
              </div>

              <ResultPanel title="Final Output">
                <pre>{playgroundResult.output}</pre>
              </ResultPanel>

              {playgroundResult.security_report && Object.keys(playgroundResult.security_report).length > 0 && (
                <div style={{ marginTop: "1rem" }}>
                  <ResultPanel title="Security & Policy Report">
                    <pre>{JSON.stringify(playgroundResult.security_report, null, 2)}</pre>
                  </ResultPanel>
                </div>
              )}
            </>
          ) : (
            <div style={{ textAlign: "center", padding: "2rem 0" }}>
              <div className="icon-circle" style={{ margin: "0 auto 1rem", width: "48px", height: "48px", background: "var(--surface)", color: "var(--ink-secondary)", display: "flex", alignItems: "center", justifyContent: "center", borderRadius: "50%" }}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M12 16v-4"></path><path d="M12 8h.01"></path></svg>
              </div>
              <p className="muted">Execute a prompt to view the trace.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
