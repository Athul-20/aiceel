import { useApp } from "../context/AppContext";
import { Field, FeaturePageHeader, ResultPanel } from "./Shared";
import * as Icons from "./Icons";

export default function SandboxLab() {
  const { labLanguage, setLabLanguage, labCode, setLabCode, labInput, setLabInput, labResult, runLab, busy, hasActiveKey, setActiveView } = useApp();

  return (
    <div className="feature-page">
      <FeaturePageHeader
        icon={<Icons.IconSandbox />}
        iconBg="var(--cyan-soft)"
        title="Sandbox Lab"
        desc="Execute Python and JavaScript code in a memory-limited, time-constrained sandbox runtime."
      />

      {!hasActiveKey && (
        <div className="key-alert">
          <span>Activate an API key to use Sandbox Lab.</span>
          <button className="btn-ghost btn-sm" onClick={() => setActiveView("keys")}>Get API Key</button>
        </div>
      )}

      <div className="feature-split">
        <section className="card">
          <div className="card-head">
            <h3>Code Editor</h3>
            <p>Write code — it runs in a constrained sandbox with memory and time limits.</p>
          </div>
          <form className="form-grid" onSubmit={runLab}>
            <Field label="Language">
              <select value={labLanguage} onChange={(e) => setLabLanguage(e.target.value)}>
                <option value="python">Python</option>
                <option value="javascript">JavaScript</option>
              </select>
            </Field>
            <Field label="Code">
              <textarea rows={10} value={labCode} onChange={(e) => setLabCode(e.target.value)} placeholder="Write your code here..." style={{ fontFamily: "var(--mono)", fontSize: "0.85rem" }} required />
            </Field>
            <Field label="Input (stdin)">
              <textarea rows={3} value={labInput} onChange={(e) => setLabInput(e.target.value)} placeholder="Optional input data..." style={{ fontFamily: "var(--mono)", fontSize: "0.85rem" }} />
            </Field>
            <button className="btn-primary btn-full" disabled={busy || !hasActiveKey} type="submit">
              {busy ? "Executing..." : "Run in Sandbox"}
            </button>
          </form>
        </section>

        <section className="card">
          <div className="card-head">
            <h3>Output</h3>
            <p>Sandbox execution result.</p>
          </div>
          {labResult ? (
            <>
              <ResultPanel title="stdout">
                <pre>{labResult.stdout || "(no output)"}</pre>
              </ResultPanel>
              {labResult.stderr && (
                <ResultPanel title="stderr">
                  <pre style={{ color: "var(--red)" }}>{labResult.stderr}</pre>
                </ResultPanel>
              )}
              <div className="result-badges">
                <span className={`result-badge ${labResult.exit_code === 0 ? "safe" : "danger"}`}>
                  Exit: {labResult.exit_code}
                </span>
                {labResult.runtime_ms != null && <span className="result-badge neutral">Runtime: {labResult.runtime_ms}ms</span>}
              </div>
            </>
          ) : (
            <div style={{ textAlign: "center", padding: "2rem 0" }}>
              <p className="muted">Run code to see output here.</p>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
