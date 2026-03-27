import { useApp } from "../context/AppContext";
import { Field, FeaturePageHeader, ResultPanel, ResultBadge } from "./Shared";
import * as Icons from "./Icons";

export default function SwarmLab() {
  const {
    agents, swarmObjective, setSwarmObjective, swarmLeadId, setSwarmLeadId,
    swarmCollaborators, toggleCollaborator, swarmResult, runSwarm,
    busy, hasActiveKey, setActiveView
  } = useApp();

  return (
    <div className="feature-page">
      <FeaturePageHeader
        icon={<Icons.IconSwarm />}
        iconBg="var(--orange-soft)"
        title="Swarm Orchestration"
        desc="Execute multi-agent collaboration with lead/collaborator routing and DAG-like task delegation."
      />

      {!hasActiveKey && (
        <div className="key-alert">
          <span>Activate an API key to run a swarm.</span>
          <button className="btn-ghost btn-sm" onClick={() => setActiveView("keys")}>Get API Key</button>
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

            <button className="btn-primary btn-full" disabled={busy || !hasActiveKey || agents.length === 0} type="submit">
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
                  {swarmResult.stages?.map((stage, i) => (
                    <div className="sublist-item" key={i}>
                      <span className="entity-type" style={{ fontSize: "0.7rem", marginRight: "0.5rem" }}>STEP {i+1}</span>
                      <span style={{ fontSize: "0.85rem" }}>{stage}</span>
                    </div>
                  ))}
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
