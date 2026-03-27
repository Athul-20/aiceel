import { useApp } from "../context/AppContext";
import { Field, FeaturePageHeader, ResultPanel, ResultBadge } from "./Shared";
import * as Icons from "./Icons";

export default function AgentBuilder() {
  const {
    agents, agentName, setAgentName, agentRole, setAgentRole,
    agentProvider, handleAgentProviderChange, agentModel, setAgentModel,
    agentPrompt, setAgentPrompt, agentTools, setAgentTools,
    agentRunAgentId, setAgentRunAgentId, agentRunService, setAgentRunService,
    agentRunObjective, setAgentRunObjective, agentRunPrompt, setAgentRunPrompt,
    agentRunResult, selectedRunAgent, createAgent, deleteAgent, runAgentFromStudio,
    singleAgentTestAgentId, setSingleAgentTestAgentId, singleAgentTestService, setSingleAgentTestService,
    singleAgentTestPrompt, setSingleAgentTestPrompt, singleAgentTestResult, runSingleAgentTest,
    services, busy, setActiveView, setPlaygroundAgentId, hasActiveKey
  } = useApp();

  const selectedSingleAgent = agents.find((item) => String(item.id) === String(singleAgentTestAgentId)) || null;
  const preferredServiceSlugs = new Set(["single-agent-lab", "secure-playground"]);
  const singleAgentServiceOptions = (() => {
    const base = (services || []).filter((service) => preferredServiceSlugs.has(service.slug));
    if (!base.length) {
      base.push({
        slug: "secure-playground",
        name: "Single Agent Lab (Secure Playground)",
      });
    }
    const ordered = [...base].sort((a, b) => (a.slug === "single-agent-lab" ? -1 : 1) - (b.slug === "single-agent-lab" ? -1 : 1));
    const seen = new Set();
    return ordered.filter((service) => {
      if (!service?.slug || seen.has(service.slug)) return false;
      seen.add(service.slug);
      return true;
    });
  })();
  const workflowServiceOptions = singleAgentServiceOptions;

  const QUICK_TEST_PROMPTS = [
    "Summarize this request in 3 concise bullet points.",
    "Return a sanitized response and flag any security risk in plain English.",
    "Draft a professional reply email with clear action items.",
    "Explain this API error and suggest the next 2 debug steps.",
  ];

  return (
    <div className="feature-page">
      <FeaturePageHeader
        icon={<Icons.IconAgent />}
        iconBg="var(--green-soft)"
        title="Agent Builder"
        desc="Create reusable AI agents, test one agent instantly, and run full workflow orchestration."
      />

      {!hasActiveKey && (
        <div className="key-alert">
          <span>Activate an API key to run agents.</span>
          <button className="btn-ghost btn-sm" onClick={() => setActiveView("keys")}>Get API Key</button>
        </div>
      )}

      <div className="feature-split">
        <section className="card">
          <div className="card-head">
            <h3>Create Agent</h3>
            <p>Define provider, model, tools, and behavior for your agent.</p>
          </div>
          <form className="form-grid" onSubmit={createAgent}>
            <Field label="Name"><input value={agentName} onChange={(e) => setAgentName(e.target.value)} required /></Field>
            <Field label="Role"><input value={agentRole} onChange={(e) => setAgentRole(e.target.value)} required /></Field>
            <div className="row">
              <Field label="Provider">
                <select value={agentProvider} onChange={(e) => handleAgentProviderChange(e.target.value)}>
                  <option value="openai">OpenAI</option>
                  <option value="groq">Groq</option>
                  <option value="google">Google</option>
                </select>
              </Field>
              <Field label="Model"><input value={agentModel} onChange={(e) => setAgentModel(e.target.value)} required /></Field>
            </div>
            <Field label="Tools (comma-separated)">
              <input value={agentTools} onChange={(e) => setAgentTools(e.target.value)} />
            </Field>
            <Field label="System Prompt">
              <textarea rows={4} value={agentPrompt} onChange={(e) => setAgentPrompt(e.target.value)} required />
            </Field>
            <button className="btn-primary" disabled={busy || !hasActiveKey} type="submit">
              {busy ? "Saving..." : "Create Agent"}
            </button>
          </form>
        </section>

        <section className="card">
          <div className="card-head">
            <h3>Single Agent Test</h3>
            <p>Pick one agent and run a direct live test call.</p>
          </div>
          <form className="form-grid" onSubmit={runSingleAgentTest}>
            <Field label="Agent">
              <select value={singleAgentTestAgentId} onChange={(e) => setSingleAgentTestAgentId(e.target.value)} required>
                <option value="">Select an agent</option>
                {agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
              </select>
            </Field>
            <Field label="Service">
              <select value={singleAgentTestService} onChange={(e) => setSingleAgentTestService(e.target.value)}>
                {singleAgentServiceOptions.map((service) => (
                  <option key={service.slug} value={service.slug}>{service.name}</option>
                ))}
              </select>
            </Field>
            <Field label="Test Prompt">
              <textarea rows={4} value={singleAgentTestPrompt} onChange={(e) => setSingleAgentTestPrompt(e.target.value)} required />
            </Field>
            <div className="agent-prompt-chips">
              {QUICK_TEST_PROMPTS.map((prompt, index) => (
                <button key={prompt} type="button" className="btn-ghost btn-sm" title={prompt} onClick={() => setSingleAgentTestPrompt(prompt)}>
                  Example {index + 1}
                </button>
              ))}
            </div>
            <button className="btn-primary btn-full" disabled={busy || agents.length === 0 || !hasActiveKey} type="submit">
              {busy ? "Testing..." : "Run Single Agent Test"}
            </button>
          </form>

          {selectedSingleAgent && (
            <div className="result-badges" style={{ marginTop: "0.5rem" }}>
              <ResultBadge type="info">{selectedSingleAgent.provider}</ResultBadge>
              <ResultBadge type="neutral">{selectedSingleAgent.model}</ResultBadge>
              <ResultBadge type="neutral">Agent ID: {selectedSingleAgent.id}</ResultBadge>
            </div>
          )}

          {singleAgentTestResult && (
            <div style={{ marginTop: "1rem", display: "grid", gap: "0.6rem" }}>
              <ResultPanel title="Agent Output">
                <pre>{singleAgentTestResult.output}</pre>
              </ResultPanel>
              {singleAgentTestResult.security_report && (
                <div className="result-badges">
                  <ResultBadge type={singleAgentTestResult.security_report.blocked ? "danger" : "safe"}>
                    {singleAgentTestResult.security_report.blocked ? "Blocked" : "Passed"}
                  </ResultBadge>
                  <ResultBadge type={singleAgentTestResult.security_report.risk_score > 0.5 ? "warn" : "info"}>
                    Risk: {singleAgentTestResult.security_report.risk_score}
                  </ResultBadge>
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      <section className="card">
        <div className="card-head">
          <h3>Advanced Workflow Runner</h3>
          <p>Run full workflow execution with selected lead agent.</p>
        </div>
        <form className="form-grid" onSubmit={runAgentFromStudio}>
          <Field label="Lead Agent">
            <select value={agentRunAgentId} onChange={(e) => setAgentRunAgentId(e.target.value)} required>
              <option value="">Select an agent</option>
              {agents.map((agent) => <option key={agent.id} value={agent.id}>{agent.name}</option>)}
            </select>
          </Field>
            <Field label="Target Service">
              <select value={agentRunService} onChange={(e) => setAgentRunService(e.target.value)}>
                {workflowServiceOptions.map((service) => (
                  <option key={service.slug} value={service.slug}>{service.name}</option>
                ))}
              </select>
            </Field>
          <Field label="Objective">
            <input value={agentRunObjective} onChange={(e) => setAgentRunObjective(e.target.value)} required />
          </Field>
          <Field label="User Prompt">
            <textarea rows={4} value={agentRunPrompt} onChange={(e) => setAgentRunPrompt(e.target.value)} required />
          </Field>
          <button className="btn-primary btn-full" disabled={busy || agents.length === 0 || !hasActiveKey} type="submit">
            {busy ? "Running..." : "Run Workflow"}
          </button>
        </form>

        {selectedRunAgent && (
          <div className="result-badges" style={{ marginTop: "0.5rem" }}>
            <ResultBadge type="info">{selectedRunAgent.provider}</ResultBadge>
            <ResultBadge type="neutral">{selectedRunAgent.model}</ResultBadge>
          </div>
        )}

        {agentRunResult && (
          <div style={{ marginTop: "1rem", display: "grid", gap: "0.6rem" }}>
            <ResultPanel title="Model Output">
              <pre>{agentRunResult.llm_dispatch?.output || agentRunResult.final_output}</pre>
            </ResultPanel>
            <details className="console-code-toggle">
              <summary>View Workflow Summary</summary>
              <ResultPanel title="Workflow Summary">
                <pre>{agentRunResult.final_output}</pre>
              </ResultPanel>
            </details>
          </div>
        )}
      </section>

      <section className="card">
        <div className="card-head">
          <div className="row" style={{ alignItems: "center" }}>
            <div>
              <h3>Saved Agents</h3>
              <p>Your library of configured agents.</p>
            </div>
          </div>
        </div>
        <div className="feature-cards-grid">
          {agents.map((agent) => (
            <article className="sublist-item" key={agent.id} style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <div>
                <h4>{agent.name}</h4>
                <p>{agent.role}</p>
                <div className="result-badges">
                  <ResultBadge type="neutral">{agent.provider}</ResultBadge>
                  <ResultBadge type="neutral">{agent.model}</ResultBadge>
                </div>
              </div>
              <div className="inline" style={{ marginTop: "auto", paddingTop: "0.5rem", borderTop: "1px solid var(--border)" }}>
                <button className="btn-ghost btn-sm" onClick={() => setSingleAgentTestAgentId(String(agent.id))}>Single Test</button>
                <button className="btn-ghost btn-sm" onClick={() => setAgentRunAgentId(String(agent.id))}>Workflow</button>
                <button className="btn-ghost btn-sm" onClick={() => { setPlaygroundAgentId(String(agent.id)); setActiveView("playground"); }}>Playground</button>
                <button className="btn-ghost btn-sm" style={{ color: "var(--red)" }} onClick={() => deleteAgent(agent.id)}>Delete</button>
              </div>
            </article>
          ))}
          {!agents.length && <p className="muted">No agents yet. Create one above to get started.</p>}
        </div>
      </section>
    </div>
  );
}
