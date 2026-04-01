import { useState, useRef } from "react";
import { useApp } from "../context/AppContext";
import { Field, FeaturePageHeader, ResultPanel, ResultBadge } from "./Shared";
import * as Icons from "./Icons";

const SAMPLE_DATA = `name,age,email,salary,department
Alice Johnson,34,alice@acme.com,85000,Engineering
Bob Smith,28,bob@corp.io,72000,Marketing
Charlie Brown,45,charlie@work.net,105000,Engineering
Diana Ross,31,diana@biz.org,78000,Design
Eve Taylor,52,eve@hq.co,120000,Marketing
Frank Wilson,27,frank@ops.dev,65000,Engineering
Grace Liu,39,grace@data.ai,95000,Data Science
Henry Park,42,henry@cloud.io,110000,Engineering
Iris Chen,25,iris@ml.co,68000,Data Science
Jack Brown,55,jack@lead.com,135000,Marketing`;

const EXAMPLE_INSTRUCTIONS = [
  { label: "Filter", instruction: "Show only employees in Engineering department" },
  { label: "Aggregate", instruction: "Group by department and show average salary for each" },
  { label: "Add Column", instruction: "Add a column called 'seniority' that says 'Senior' if age > 35, else 'Junior'" },
  { label: "Mask PII", instruction: "Mask all email addresses by replacing with 'hidden@masked.com'" },
  { label: "Sort", instruction: "Sort by salary descending and add a rank column" },
  { label: "Clean", instruction: "Remove any duplicate names and lowercase all department names" },
];

export default function PandoraLab() {
  const { activeApiKey, busy: globalBusy, hasActiveKey, setActiveView, setError, setNotice, copyText, apiKeyReadiness } = useApp();

  const [csvData, setCsvData] = useState(SAMPLE_DATA);
  const [instruction, setInstruction] = useState("Show only employees in Engineering department and sort by salary descending");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState([]);
  const fileRef = useRef(null);

  async function handleFileUpload(e) {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > 5 * 1024 * 1024) {
      setError("File too large (max 5MB)");
      return;
    }

    const reader = new FileReader();
    reader.onload = (event) => {
      setCsvData(event.target.result);
      setNotice(`Loaded: ${file.name} (${(file.size / 1024).toFixed(1)}KB)`);
    };
    reader.readAsText(file);
  }

  async function runTransform(e) {
    e.preventDefault();
    if (!hasActiveKey || !activeApiKey) { setError(apiKeyReadiness.alertMessage); return; }
    setBusy(true); setResult(null); setError("");

    try {
      const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
      const response = await fetch(`${API_BASE}/v1/engine/pandora/transform`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-API-Key": activeApiKey },
        body: JSON.stringify({ csv_data: csvData, instruction }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err?.error?.message || err.detail || "Transform failed");
      }

      const data = await response.json();
      setResult(data);
      setHistory(prev => [{ instruction, timestamp: new Date().toLocaleTimeString(), rows: data.row_count, cols: data.column_count }, ...prev.slice(0, 9)]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function useResultAsInput() {
    if (result?.transformed_csv) {
      setCsvData(result.transformed_csv);
      setResult(null);
      setInstruction("");
      setNotice("Previous output is now your input. Chain another transformation.");
    }
  }

  const previewRows = csvData.trim().split("\n").slice(0, 8);
  const previewHeaders = previewRows[0]?.split(",") || [];
  const previewData = previewRows.slice(1).map(row => row.split(","));

  const resultRows = result?.transformed_csv?.trim().split("\n") || [];
  const resultHeaders = resultRows[0]?.split(",") || [];
  const resultData = resultRows.slice(1, 12).map(row => row.split(","));

  return (
    <div className="feature-page">
      <FeaturePageHeader
        icon={<Icons.IconDataLab />}
        iconBg="linear-gradient(135deg, var(--purple-soft), var(--cyan-soft))"
        title="Pandora Data Lab"
        desc="Transform any dataset using natural language. The AI only sees your schema, never your actual data."
      />

      {!hasActiveKey && (
        <div className="key-alert">
          <span>{apiKeyReadiness.alertMessage} Configure a provider as well to use Pandora.</span>
          <button className="btn-ghost btn-sm" onClick={() => setActiveView("keys")}>{apiKeyReadiness.alertActionLabel}</button>
        </div>
      )}

      <div className="feature-split">
        {/* Input Panel */}
        <section className="card">
          <div className="card-head">
            <h3>Data Input</h3>
            <p>Paste CSV data, upload a file, or use the sample dataset. Your data stays local.</p>
          </div>

          {/* Data Preview Table */}
          {previewHeaders.length > 0 && (
            <div className="pandora-table-wrap">
              <table className="pandora-table">
                <thead>
                  <tr>{previewHeaders.map((h, i) => <th key={i}>{h.trim()}</th>)}</tr>
                </thead>
                <tbody>
                  {previewData.map((row, ri) => (
                    <tr key={ri}>{row.map((cell, ci) => <td key={ci}>{cell.trim()}</td>)}</tr>
                  ))}
                </tbody>
              </table>
              <p className="muted" style={{ fontSize: "0.75rem", marginTop: "0.4rem" }}>
                Showing {Math.min(previewData.length, 7)} of {csvData.trim().split("\n").length - 1} rows
              </p>
            </div>
          )}

          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
            <button className="btn-ghost btn-sm" onClick={() => fileRef.current?.click()}>Upload File</button>
            <button className="btn-ghost btn-sm" onClick={() => setCsvData(SAMPLE_DATA)}>Reset Sample</button>
            <button className="btn-ghost btn-sm" onClick={() => setCsvData("")}>Clear</button>
            <input ref={fileRef} type="file" accept=".csv,.tsv,.txt" style={{ display: "none" }} onChange={handleFileUpload} />
          </div>

          <Field label="Raw CSV Data">
            <textarea
              rows={6}
              value={csvData}
              onChange={(e) => setCsvData(e.target.value)}
              placeholder="Paste CSV data here..."
              style={{ fontFamily: "var(--mono)", fontSize: "0.8rem" }}
            />
          </Field>
        </section>

        {/* Transform Panel */}
        <section className="card">
          <div className="card-head">
            <h3>Natural Language Transform</h3>
            <p>Describe what you want to do. The AI sees only column names and types, then generates code that runs locally on your data.</p>
          </div>

          <form className="form-grid" onSubmit={runTransform}>
            <Field label="Instruction">
              <textarea
                rows={3}
                value={instruction}
                onChange={(e) => setInstruction(e.target.value)}
                required
                placeholder="e.g. Show only rows where salary > 80000 and sort by name"
              />
            </Field>

            <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
              {EXAMPLE_INSTRUCTIONS.map((ex) => (
                <button
                  type="button"
                  key={ex.label}
                  className="btn-ghost btn-sm"
                  onClick={() => setInstruction(ex.instruction)}
                  style={{ fontSize: "0.75rem" }}
                >
                  {ex.label}
                </button>
              ))}
            </div>

            <button className="btn-primary btn-full" disabled={busy || !hasActiveKey || !csvData.trim()} type="submit">
              {busy ? "Transforming..." : "Run Pandora Transform"}
            </button>
          </form>

          {/* Result */}
          {result && (
            <div style={{ marginTop: "0.5rem" }}>
              <div className="result-badges">
                <ResultBadge type="safe">Success</ResultBadge>
                <ResultBadge type="info">{result.row_count} rows</ResultBadge>
                <ResultBadge type="neutral">{result.column_count} columns</ResultBadge>
                {result.provider && <ResultBadge type="neutral">{result.provider}/{result.model}</ResultBadge>}
              </div>

              {/* Result Table */}
              {resultHeaders.length > 0 && (
                <div className="pandora-table-wrap" style={{ marginTop: "0.5rem" }}>
                  <table className="pandora-table result">
                    <thead>
                      <tr>{resultHeaders.map((h, i) => <th key={i}>{h.trim()}</th>)}</tr>
                    </thead>
                    <tbody>
                      {resultData.map((row, ri) => (
                        <tr key={ri}>{row.map((cell, ci) => <td key={ci}>{cell.trim()}</td>)}</tr>
                      ))}
                    </tbody>
                  </table>
                  {result.row_count > 11 && (
                    <p className="muted" style={{ fontSize: "0.75rem", marginTop: "0.3rem" }}>
                      Showing 11 of {result.row_count} rows
                    </p>
                  )}
                </div>
              )}

              {result.generated_code && (
                <ResultPanel title="Generated Code" onCopy={copyText} copyText={result.generated_code}>
                  <pre style={{ fontSize: "0.8rem" }}>{result.generated_code}</pre>
                </ResultPanel>
              )}

              <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.5rem" }}>
                <button className="btn-ghost btn-sm" onClick={useResultAsInput}>Chain - Use as New Input</button>
                <button className="btn-ghost btn-sm" onClick={() => copyText(result.transformed_csv)}>Copy CSV</button>
                <button className="btn-ghost btn-sm" onClick={() => {
                  const blob = new Blob([result.transformed_csv], { type: "text/csv" });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a");
                  a.href = url; a.download = "pandora_output.csv"; a.click();
                  URL.revokeObjectURL(url);
                }}>Download CSV</button>
              </div>
            </div>
          )}
        </section>
      </div>

      {/* History */}
      {history.length > 0 && (
        <section className="card">
          <div className="card-head">
            <h3>Transform History</h3>
            <p>Your recent transformations in this session.</p>
          </div>
          <div className="sublist">
            {history.map((h, i) => (
              <article className="sublist-item row" key={i}>
                <div>
                  <h4>"{h.instruction}"</h4>
                  <p className="sublist-meta">{h.rows} rows x {h.cols} cols - {h.timestamp}</p>
                </div>
                <button className="btn-ghost btn-sm" onClick={() => setInstruction(h.instruction)}>Reuse</button>
              </article>
            ))}
          </div>
        </section>
      )}

      {/* How it works */}
      <section className="card">
        <div className="card-head">
          <h3>How Pandora Works</h3>
          <p>Secure, privacy-first data transformation pipeline.</p>
        </div>
        <div className="feature-cards-grid">
          {[
            { Icon: Icons.IconShield, title: "Schema-Only AI", desc: "The AI model only sees column names and data types. Your actual data values never leave the sandbox." },
            { Icon: Icons.IconKey, title: "AST Security Validation", desc: "Generated code is parsed and validated — no file access, no network calls, no unsafe operations." },
            { Icon: Icons.IconSandbox, title: "Sandboxed Execution", desc: "Code runs in a restricted sandbox with only pandas, numpy, and safe libraries available." },
            { Icon: Icons.IconRefresh, title: "Auto-Repair", desc: "If execution fails, Pandora automatically generates a fix and retries up to 4 times." },
          ].map((item) => (
            <article className="sublist-item" key={item.title} style={{ display: "grid", gap: "0.3rem" }}>
              <h4>{item.Icon && <item.Icon />} {item.title}</h4>
              <p>{item.desc}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
