import { useMemo, useState } from "react";
import { API_BASE_URL } from "../api";
import { useApp } from "../context/AppContext";
import { Field, FeaturePageHeader, ResultBadge, ResultPanel } from "./Shared";
import { CONSOLE_SCENARIOS, ENGINE_OPERATIONS } from "../constants";
import * as Icons from "./Icons";

export default function Console() {
  const {
    engineOperation, setEngineOperation, enginePayload, setEnginePayload,
    engineResult, engineRequestMeta, runFeatureApi, busy, hasFeatureAccess, copyText, sessionStatus
  } = useApp();

  const [scenarioQuery, setScenarioQuery] = useState("");
  const [payloadError, setPayloadError] = useState("");
  const [showAllScenarios, setShowAllScenarios] = useState(false);
  const [sampleLang, setSampleLang] = useState("curl");

  const selectedOp = ENGINE_OPERATIONS[engineOperation] || ENGINE_OPERATIONS.workflow;
  const featuredScenarioIds = [
    "pii_masking",
    "pandora_defense",
    "agent_workflow",
    "llm_dispatch",
    "secure_playground",
    "sandbox_lab",
    "runtime_lazy_load",
    "vault_encrypt",
  ];

  const groupedScenarios = useMemo(() => {
    const baseScenarios = showAllScenarios
      ? CONSOLE_SCENARIOS
      : CONSOLE_SCENARIOS.filter((item) => featuredScenarioIds.includes(item.id));
    const q = scenarioQuery.trim().toLowerCase();
    const filtered = baseScenarios.filter((item) => {
      if (!q) return true;
      const op = ENGINE_OPERATIONS[item.endpointId] || {};
      return (
        item.title.toLowerCase().includes(q)
        || item.description.toLowerCase().includes(q)
        || item.group.toLowerCase().includes(q)
        || String(op.path || "").toLowerCase().includes(q)
      );
    });
    return Object.entries(
      filtered.reduce((acc, item) => {
        acc[item.group] = acc[item.group] || [];
        acc[item.group].push(item);
        return acc;
      }, {})
    );
  }, [scenarioQuery, showAllScenarios]);

  const endpointPath = selectedOp.path || "/unknown";
  const endpointMethod = String(selectedOp.method || "POST").toUpperCase();
  const parsedPayload = useMemo(() => {
    try {
      return JSON.parse(enginePayload);
    } catch {
      return selectedOp.payload ?? {};
    }
  }, [enginePayload, selectedOp.payload]);
  const prettyPayload = JSON.stringify(parsedPayload, null, 2);
  const pythonJsonLiteral = JSON.stringify(parsedPayload)
    .replace(/\\/g, "\\\\")
    .replace(/'/g, "\\'");

  function selectScenario(scenarioId) {
    const scenario = CONSOLE_SCENARIOS.find((item) => item.id === scenarioId);
    if (!scenario) return;
    const operation = ENGINE_OPERATIONS[scenario.endpointId];
    if (!operation) return;
    setEngineOperation(scenario.endpointId);
    setEnginePayload(JSON.stringify(scenario.payload ?? operation.payload ?? {}, null, 2));
    setPayloadError("");
  }

  function formatPayload() {
    try {
      const parsed = JSON.parse(enginePayload);
      setEnginePayload(JSON.stringify(parsed, null, 2));
      setPayloadError("");
    } catch {
      setPayloadError("Payload must be valid JSON before formatting.");
    }
  }

  function resetPayload() {
    setEnginePayload(JSON.stringify(selectedOp.payload ?? {}, null, 2));
    setPayloadError("");
  }

  function onPayloadChange(event) {
    const next = event.target.value;
    setEnginePayload(next);
    try {
      JSON.parse(next);
      setPayloadError("");
    } catch {
      setPayloadError("Invalid JSON. Fix payload format before sending.");
    }
  }

  function handleSubmit(event) {
    event.preventDefault();
    if (endpointMethod !== "GET") {
      try {
        JSON.parse(enginePayload);
        setPayloadError("");
      } catch {
        setPayloadError("Invalid JSON. Fix payload format before sending.");
        return;
      }
    }
    runFeatureApi(event);
  }

  const curlCommand = endpointMethod === "GET"
    ? `curl -X ${endpointMethod} ${API_BASE_URL}${endpointPath} \\
  -H "X-API-Key: YOUR_AICCEL_API_KEY"`
    : `curl -X ${endpointMethod} ${API_BASE_URL}${endpointPath} \\
  -H "X-API-Key: YOUR_AICCEL_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '${prettyPayload}'`;

  const jsSample = endpointMethod === "GET"
    ? `const API_KEY = "YOUR_AICCEL_API_KEY";
const response = await fetch("${API_BASE_URL}${endpointPath}", {
  method: "${endpointMethod}",
  headers: {
    "X-API-Key": API_KEY
  }
});
const data = await response.json();
console.log(response.status, data);`
    : `const API_KEY = "YOUR_AICCEL_API_KEY";
const payload = ${prettyPayload};

const response = await fetch("${API_BASE_URL}${endpointPath}", {
  method: "${endpointMethod}",
  headers: {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
  },
  body: JSON.stringify(payload)
});
const data = await response.json();
console.log(response.status, data);`;

  const pythonSample = endpointMethod === "GET"
    ? `import requests

url = "${API_BASE_URL}${endpointPath}"
headers = {
    "X-API-Key": "YOUR_AICCEL_API_KEY"
}
response = requests.get(url, headers=headers, timeout=30)
print(response.status_code)
print(response.json())`
    : `import json
import requests

url = "${API_BASE_URL}${endpointPath}"
headers = {
    "X-API-Key": "YOUR_AICCEL_API_KEY",
    "Content-Type": "application/json"
}
payload = json.loads('${pythonJsonLiteral}')

response = requests.request("${endpointMethod}", url, headers=headers, json=payload, timeout=30)
print(response.status_code)
print(response.json())`;

  const codeSamples = {
    curl: curlCommand,
    javascript: jsSample,
    python: pythonSample,
  };

  const sampleTitles = {
    curl: "cURL",
    javascript: "JavaScript (fetch)",
    python: "Python (requests)",
  };

  return (
    <div className="feature-page">
      <FeaturePageHeader
        icon={<Icons.IconConsole />}
        iconBg="var(--cyan-soft)"
        title="Interactive Console"
        desc="Make real API calls inside the platform, inspect live responses, and copy production-ready integration code."
      />

      {!hasFeatureAccess && (
        <div className="key-alert">
          <span>{sessionStatus.alertMessage}</span>
        </div>
      )}

      <div className="console-layout">
        <aside className="console-scenarios">
          <section className="card console-side-card">
            <div className="card-head">
              <h3>Scenario Library</h3>
              <p>Pick a ready request for any AICCEL module.</p>
            </div>
            <div className="console-side-tools">
              <button
                type="button"
                className="btn-ghost btn-sm"
                onClick={() => setShowAllScenarios((prev) => !prev)}
              >
                {showAllScenarios ? "Show Recommended Only" : "Show All Scenarios"}
              </button>
            </div>
            <div className="console-search">
              <input
                type="text"
                placeholder="Search scenarios, groups, or endpoints..."
                value={scenarioQuery}
                onChange={(e) => setScenarioQuery(e.target.value)}
              />
            </div>
            <div className="scenario-list stagger-children">
              {groupedScenarios.length > 0 ? groupedScenarios.map(([group, list]) => (
                <div className="scenario-section" key={group}>
                  <p>{group}</p>
                  {list.map((scenario) => {
                    const op = ENGINE_OPERATIONS[scenario.endpointId] || {};
                    return (
                      <button
                        className={`scenario-link ${engineOperation === scenario.endpointId ? "active" : ""}`}
                        key={scenario.id}
                        onClick={() => selectScenario(scenario.id)}
                        type="button"
                      >
                        <strong>{scenario.title}</strong>
                        <p>{scenario.description}</p>
                        <div className="scenario-link-meta">
                          <span className={`badge badge-method method-${String(op.method || "post").toLowerCase()}`}>{op.method || "POST"}</span>
                          <span className="badge">{op.path || "/unknown"}</span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )) : <p className="muted">No scenarios match your search.</p>}
            </div>
          </section>
        </aside>

        <section className="console-main">
          <section className="card console-request-card">
            <div className="card-head">
              <h3>Request Builder</h3>
              <p>Real API call execution using method + endpoint + payload.</p>
            </div>

            <div className="console-op-meta">
              <span className={`badge badge-method method-${endpointMethod.toLowerCase()}`}>{endpointMethod}</span>
              <span className="badge">{endpointPath}</span>
              <span className="badge">Auth: Session in UI / API key externally</span>
            </div>

            <form className="form-grid" onSubmit={handleSubmit}>
              <Field label="Endpoint Operation">
                <select value={engineOperation} onChange={(e) => {
                  const next = e.target.value;
                  setEngineOperation(next);
                  setEnginePayload(JSON.stringify(ENGINE_OPERATIONS[next].payload ?? {}, null, 2));
                  setPayloadError("");
                }}>
                  {Object.entries(ENGINE_OPERATIONS).map(([key, op]) => (
                    <option key={key} value={key}>{op.label} ({op.path})</option>
                  ))}
                </select>
              </Field>

              <Field label="Request Payload (JSON)">
                <textarea
                  rows={10}
                  value={enginePayload}
                  onChange={onPayloadChange}
                  className={payloadError ? "invalid-json" : ""}
                  style={{ fontFamily: "var(--mono)", fontSize: "0.84rem" }}
                  required={endpointMethod !== "GET"}
                />
              </Field>

              {payloadError && <p className="console-error">{payloadError}</p>}

              <div className="console-actions">
                <button className="btn-ghost" onClick={formatPayload} type="button">Format JSON</button>
                <button className="btn-ghost" onClick={resetPayload} type="button">Reset Payload</button>
                <button className="btn-ghost" onClick={() => copyText(prettyPayload)} type="button">Copy Payload</button>
                <button className="btn-primary" disabled={busy || !hasFeatureAccess || Boolean(payloadError)} type="submit">
                  {busy ? "Calling API..." : `Send ${endpointMethod}`}
                </button>
              </div>
            </form>
          </section>

          <section className="card">
            <div className="card-head">
              <h3>Response Inspector</h3>
              <p>Live response payload from your selected API endpoint.</p>
            </div>
            {engineRequestMeta && (
              <div className="result-badges">
                <ResultBadge type={engineRequestMeta.status >= 400 ? "danger" : "safe"}>
                  HTTP {engineRequestMeta.status}
                </ResultBadge>
                <ResultBadge type="info">{engineRequestMeta.duration_ms} ms</ResultBadge>
                <ResultBadge type="neutral">{engineRequestMeta.method} {engineRequestMeta.path}</ResultBadge>
              </div>
            )}
            {engineResult ? (
              <ResultPanel title="JSON Response" onCopy={copyText} copyText={JSON.stringify(engineResult, null, 2)}>
                <pre>{JSON.stringify(engineResult, null, 2)}</pre>
              </ResultPanel>
            ) : (
              <p className="muted">Run a request to inspect the backend response.</p>
            )}
          </section>

          <section className="card">
            <div className="card-head">
              <h3>Sample Code</h3>
              <p>Copy and run these snippets outside the dashboard.</p>
            </div>
            <div className="console-sample-tabs">
              {[
                ["curl", "cURL"],
                ["javascript", "JavaScript"],
                ["python", "Python"],
              ].map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  className={`console-sample-tab ${sampleLang === id ? "active" : ""}`}
                  onClick={() => setSampleLang(id)}
                >
                  {label}
                </button>
              ))}
            </div>
            <ResultPanel title={sampleTitles[sampleLang]} onCopy={copyText} copyText={codeSamples[sampleLang]}>
              <pre>{codeSamples[sampleLang]}</pre>
            </ResultPanel>
          </section>
        </section>
      </div>
    </div>
  );
}
