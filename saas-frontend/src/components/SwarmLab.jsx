import { useApp } from "../context/AppContext";
import { Field, FeaturePageHeader, ResultPanel, ResultBadge } from "./Shared";
import * as Icons from "./Icons";

export default function SwarmLab() {
  const {
    agents, swarmObjective, setSwarmObjective, swarmLeadId, setSwarmLeadId,
    swarmCollaborators, toggleCollaborator, swarmResult, runSwarm,
    busy, hasFeatureAccess, setActiveView, sessionStatus
  } = useApp();

  const SWARM_PRESETS = [
    { label: "GTM Plan", text: "Draft a Go-To-Market plan for the AICCEL enterprise launch." },
    { label: "Security Audit", text: "Analyze the current agentic architecture for PII and context injection vulnerabilities." },
    { label: "Feature Roadmap", text: "Design a 12-month roadmap focusing on multi-cloud agentic orchestration." },
  ];

  return (
    <div className="feature-page">
      <FeaturePageHeader
        icon={<Icons.IconSwarm />}
        iconBg="var(--orange-soft)"
        title="Swarm Orchestration"
        desc="Execute multi-agent collaboration with lead/collaborator routing and DAG-like task delegation."
      />

      {!hasFeatureAccess && (
        <div className="key-alert">
          <span>{sessionStatus.alertMessage}</span>
        </div>
      )}

      <div className="feature-split">
        <section className="card">
          <div className="card-head">
            <h3>Swarm Configuration</h3>
            <p>Define the objective and assemble your team of agents.</p>
          </div>
          <form className="form-grid" onSubmit={runSwarm}>
            <Field label="Objective">
              <textarea rows={4} value={swarmObjective} onChange={(e) => setSwarmObjective(e.target.value)} required placeholder="What should the swarm accomplish?" />
            </Field>

            <div className="agent-prompt-chips" style={{ marginBottom: "1rem" }}>
              {SWARM_PRESETS.map((s) => (
                <button key={s.label} type="button" className="btn-ghost btn-sm" onClick={() => setSwarmObjective(s.text)}>
                  {s.label}
                </button>
              ))}
            </div>
            
            <Field label="Lead Agent (Orchestrator)">
              <select value={swarmLeadId} onChange={(e) => setSwarmLeadId(e.target.value)}>
                <option value="">Auto (System assigns best lead)</option>
                {agents.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
              </select>
            </Field>

            <div className="field">
              <span>Collaborator Agents</span>
              <p className="muted" style={{ marginBottom: "0.5rem" }}>Select agents to assist the lead in completing the objective.</p>
              <div className="chip-grid">
                {agents.map((a) => (
                  <label key={a.id} className="chip">
                    <input type="checkbox" checked={swarmCollaborators.includes(a.id)} onChange={() => toggleCollaborator(a.id)} />
                    <span>{a.name}</span>
                  </label>
                ))}
              </div>
              {agents.length === 0 && <p className="muted">No agents available. <button type="button" className="btn-ghost btn-sm" onClick={() => setActiveView("agents")}>Create Agents</button></p>}
            </div>

            <button className="btn-primary btn-full" disabled={busy || !hasFeatureAccess || agents.length === 0} type="submit">
              {busy ? "Running Swarm..." : <><Icons.IconSwarm /> Launch Swarm Execution</>}
            </button>
          </form>
        </section>

        <section className="card">
          <div className="card-head">
            <h3>Execution Trajectory</h3>
            <p>DAG resolution and collaborative payload trace.</p>
          </div>
          {swarmResult ? (
            <>
              <ResultPanel title="Final Swarm Synthesis">
                <pre>{swarmResult.final_output}</pre>
              </ResultPanel>
              
              <div style={{ marginTop: "1rem" }}>
                <p className="muted" style={{ marginBottom: "0.5rem" }}>Execution Stages:</p>
                <div className="sublist">
                  {swarmResult.stages?.map((stage, i) => {
                    const isCritical = stage.includes("CRITICAL:");
                    const isWarning = stage.includes("WARNING:");
                    return (
                      <div 
                        className="sublist-item" 
                        key={i}
                        style={isCritical ? {
                          background: "rgba(255,59,48,0.08)",
                          borderLeft: "3px solid var(--red)",
                          padding: "0.6rem 0.75rem",
                        } : isWarning ? {
                          background: "rgba(255,149,0,0.08)",
                          borderLeft: "3px solid var(--orange)",
                          padding: "0.6rem 0.75rem",
                        } : {}}
                      >
                        <span className="entity-type" style={{ 
                          fontSize: "0.7rem", 
                          marginRight: "0.5rem",
                          color: isCritical ? "var(--red)" : isWarning ? "var(--orange)" : undefined,
                        }}>
                          {isCritical ? "BREACH" : isWarning ? "ALERT" : `STEP ${i+1}`}
                        </span>
                        <span style={{ 
                          fontSize: "0.85rem",
                          fontWeight: isCritical || isWarning ? 600 : 400,
                          color: isCritical ? "var(--red)" : isWarning ? "var(--orange)" : undefined,
                        }}>{stage}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </>
          ) : (
            <div style={{ textAlign: "center", padding: "2rem 0" }}>
              <div style={{ fontSize: "2rem", marginBottom: "0.5rem", color: "var(--orange)" }}><Icons.IconSwarm /></div>
              <p className="muted">Configure and run a swarm to see the collaborative trace.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
