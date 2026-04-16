import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";

import { API_BASE_URL } from "../api";
import { useApp } from "../context/AppContext";
import { FeaturePageHeader, ResultBadge, ResultPanel } from "./Shared";
import * as Icons from "./Icons";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

const DEFAULT_TEXT = "Customer: Jane Doe, email jane@acme.com, phone +1-212-555-0180, SSN 123-45-6789, card 4111 1111 1111 1111.";
const HISTORY_STORAGE_KEY = "aiccel-pii-history-v1";
const PRESET_STORAGE_KEY = "aiccel-pii-preset-v1";

const DEFAULT_OPTIONS = {
  remove_email: true,
  remove_phone: true,
  remove_person: true,
  remove_blood_group: true,
  remove_passport: true,
  remove_pancard: true,
  remove_organization: true,
  remove_ssn: true,
  remove_card: true,
  remove_address: true,
  remove_dob: true,
  remove_bank_account: true,
};

const OPTIONS_LIST = [
  { key: "remove_email", label: "Email" },
  { key: "remove_phone", label: "Phone" },
  { key: "remove_person", label: "Person Name" },
  { key: "remove_organization", label: "Organization" },
  { key: "remove_address", label: "Address" },
  { key: "remove_dob", label: "Date of Birth" },
  { key: "remove_bank_account", label: "Bank Account" },
  { key: "remove_blood_group", label: "Blood Group" },
  { key: "remove_passport", label: "Passport" },
  { key: "remove_pancard", label: "PAN Card" },
  { key: "remove_ssn", label: "SSN" },
  { key: "remove_card", label: "Credit Card" },
];

const PDF_PROGRESS_STEPS = [
  "Preparing document",
  "Extracting page text",
  "Detecting sensitive entities",
  "Applying permanent redactions",
  "Rendering audit-ready output",
];

const TEXT_PROGRESS_STEPS = [
  "Preparing input",
  "Detecting sensitive entities",
  "Building masked output",
  "Scoring policy risk",
];

const PRESETS = [
  {
    id: "resume",
    name: "Resume Redaction",
    description: "Best for CVs, candidate packets, and reference docs.",
    reversible: true,
    sampleText: "Candidate: Jane Doe, email jane@acme.com, phone +1-212-555-0180, SSN 123-45-6789, Education: New York City College.",
    options: {
      ...DEFAULT_OPTIONS,
      remove_bank_account: false,
      remove_blood_group: false,
      remove_passport: false,
      remove_pancard: false,
    },
  },
  {
    id: "finance",
    name: "Finance Safe",
    description: "Strict masking for payment, ID, and account-heavy documents.",
    reversible: false,
    sampleText: "Customer John Smith paid with card 4111 1111 1111 1111 using account 998877665544 and email john@example.com.",
    options: {
      ...DEFAULT_OPTIONS,
    },
  },
  {
    id: "identity",
    name: "KYC Pack",
    description: "Prioritizes identity documents and onboarding paperwork.",
    reversible: false,
    sampleText: "Passport P1234567, PAN ABCDE1234F, phone +1-212-555-0180, address 20 Main Street, New York.",
    options: {
      ...DEFAULT_OPTIONS,
      remove_card: false,
      remove_blood_group: false,
    },
  },
  {
    id: "minimal",
    name: "Contact Only",
    description: "Quick scrub for emails, phones, and direct contact details.",
    reversible: true,
    sampleText: "Reach Jane Doe at jane@acme.com or +1-212-555-0180 for the latest project update.",
    options: {
      ...DEFAULT_OPTIONS,
      remove_person: false,
      remove_organization: false,
      remove_address: false,
      remove_dob: false,
      remove_bank_account: false,
      remove_blood_group: false,
      remove_passport: false,
      remove_pancard: false,
      remove_ssn: false,
      remove_card: false,
    },
  },
];

const CANONICAL_ENTITY_TYPES = {
  email: "emails",
  emails: "emails",
  phone: "phones",
  phones: "phones",
  person: "persons",
  persons: "persons",
  organization: "organizations",
  organizations: "organizations",
  address: "addresses",
  addresses: "addresses",
  birthday: "birthdays",
  birthdays: "birthdays",
  dob: "birthdays",
  bank_account: "bank_accounts",
  bank_accounts: "bank_accounts",
  passport: "passports",
  passports: "passports",
  pancard: "pancards",
  pancards: "pancards",
  ssn: "ssns",
  ssns: "ssns",
  card: "cards",
  cards: "cards",
  blood_group: "blood_groups",
  blood_groups: "blood_groups",
  ids: "ids",
};

const ENTITY_TYPE_ICONS = {
  emails: Icons.IconMail,
  phones: Icons.IconPhone,
  persons: Icons.IconPatient,
  organizations: Icons.IconBuilding,
  blood_groups: Icons.IconDrop,
  passports: Icons.IconID,
  pancards: Icons.IconID,
  ssns: Icons.IconID,
  cards: Icons.IconCreditCard,
  addresses: Icons.IconMapPin,
  birthdays: Icons.IconCake,
  bank_accounts: Icons.IconBank,
  usernames: Icons.IconPatient,
  passwords: Icons.IconKey,
  ips: Icons.IconGlobe,
  financials: Icons.IconDollar,
  ids: Icons.IconID,
  demographics: Icons.IconUsage,
};

const ENTITY_TYPE_LABELS = {
  emails: "Emails",
  phones: "Phone Numbers",
  persons: "Person Names",
  organizations: "Organizations",
  blood_groups: "Blood Groups",
  passports: "Passports",
  pancards: "PAN Cards",
  ssns: "SSNs",
  cards: "Credit Cards",
  addresses: "Addresses",
  birthdays: "Birthdays",
  bank_accounts: "Bank Accounts",
  usernames: "Usernames",
  passwords: "Passwords",
  ips: "IP Addresses",
  financials: "Financial Details",
  ids: "Identification Docs",
  demographics: "Demographics",
};

const STRUCTURED_TYPES = new Set(["emails", "phones", "ssns", "cards", "bank_accounts", "blood_groups", "pancards", "ids"]);

function cloneOptions(options) {
  return { ...DEFAULT_OPTIONS, ...(options || {}) };
}

function loadHistory() {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(HISTORY_STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveHistory(history) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(history.slice(0, 8)));
  } catch {}
}

function savePresetId(presetId) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(PRESET_STORAGE_KEY, presetId);
  } catch {}
}

function loadPresetId() {
  if (typeof window === "undefined") return PRESETS[0].id;
  try {
    return window.localStorage.getItem(PRESET_STORAGE_KEY) || PRESETS[0].id;
  } catch {
    return PRESETS[0].id;
  }
}

function formatTimestamp(value) {
  try {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(new Date(value));
  } catch {
    return value;
  }
}

function groupEntities(entities) {
  const groups = {};
  for (const entity of entities || []) {
    const rawType = String(entity.type || "unknown").toLowerCase();
    const type = CANONICAL_ENTITY_TYPES[rawType] || rawType;
    if (!groups[type]) groups[type] = [];
    groups[type].push(entity);
  }
  return groups;
}

function getEntityTrust(entityType, entity) {
  if (entity?.source === "regex" || STRUCTURED_TYPES.has(entityType)) {
    return { source: "Rule verified", confidence: "High confidence" };
  }
  return { source: "GLiNER review", confidence: "Needs quick review" };
}

function triggerDownload(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function buildAuditReport({ activeTab, file, text, presetName, options, pdfResult, result, entityGroups }) {
  return {
    generated_at: new Date().toISOString(),
    mode: activeTab,
    preset: presetName,
    input: activeTab === "pdf" ? { filename: file?.name || null, size_bytes: file?.size || null } : { preview: text.slice(0, 200) },
    options,
    summary: activeTab === "pdf"
      ? {
          redactions: pdfResult?.count || 0,
          entities_found: pdfResult?.entities?.length || 0,
          entity_types: Object.keys(entityGroups || {}),
        }
      : {
          risk_score: result?.risk_score ?? null,
          entities_found: result?.sensitive_entities?.length || 0,
          markers: result?.detected_markers || [],
        },
    entities: activeTab === "pdf"
      ? (pdfResult?.entities || []).map((entity) => {
          const type = CANONICAL_ENTITY_TYPES[String(entity.type || "").toLowerCase()] || entity.type;
          const trust = getEntityTrust(type, entity);
          return { ...entity, type, ...trust };
        })
      : result?.sensitive_entities || [],
  };
}

function StatCard({ label, value, tone = "neutral" }) {
  return (
    <div className={`pii-stat-card ${tone}`}>
      <span className="pii-stat-value">{value}</span>
      <span className="pii-stat-label">{label}</span>
    </div>
  );
}

function DiagnosticsItem({ label, state, detail }) {
  return (
    <div className={`pii-diagnostic ${state}`}>
      <span className="pii-diagnostic-dot" />
      <div>
        <div className="pii-diagnostic-label">{label}</div>
        <div className="pii-diagnostic-detail">{detail}</div>
      </div>
    </div>
  );
}

function ProgressTracker({ steps, activeIndex }) {
  return (
    <div className="pii-progress-tracker">
      {steps.map((step, index) => (
        <div
          key={step}
          className={`pii-progress-step ${index < activeIndex ? "done" : ""} ${index === activeIndex ? "active" : ""}`}
        >
          <span className="pii-progress-bullet">{index < activeIndex ? <Icons.IconCheck /> : index + 1}</span>
          <span>{step}</span>
        </div>
      ))}
    </div>
  );
}

export default function PiiMasking() {
  const { runPiiMasking, runPdfMasking, busy, hasFeatureAccess, sessionStatus } = useApp();
  const [activeTab, setActiveTab] = useState("text");
  const [text, setText] = useState(DEFAULT_TEXT);
  const [file, setFile] = useState(null);
  const [pdfResult, setPdfResult] = useState(null);
  const [result, setResult] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [reversible, setReversible] = useState(true);
  const [options, setOptions] = useState(cloneOptions(DEFAULT_OPTIONS));
  const [selectedPresetId, setSelectedPresetId] = useState(loadPresetId());
  const [history, setHistory] = useState(loadHistory());
  const [backendStatus, setBackendStatus] = useState({ state: "checking", detail: "Checking API availability..." });
  const [progressIndex, setProgressIndex] = useState(0);
  const [previewMode, setPreviewMode] = useState("redacted");
  const [originalPreviewUrl, setOriginalPreviewUrl] = useState(null);
  const [originalNumPages, setOriginalNumPages] = useState(0);
  const fileInputRef = useRef(null);
  const redactedUrlRef = useRef(null);

  const sensitiveEntities = result?.sensitive_entities || [];
  const detectedMarkers = result?.detected_markers || [];
  const maskedParagraph = result?.tokenized_text || result?.sanitized_text || result?.tokenized_prompt || result?.sanitized_prompt || "";
  const injectionDetected = Boolean(result?.blocked || result?.prompt_injection_detected || detectedMarkers.length);
  const progressSteps = activeTab === "pdf" ? PDF_PROGRESS_STEPS : TEXT_PROGRESS_STEPS;
  const activePreset = PRESETS.find((preset) => preset.id === selectedPresetId) || PRESETS[0];
  const entityGroups = groupEntities(pdfResult?.entities || []);
  const enabledCount = OPTIONS_LIST.filter((option) => options[option.key]).length;
  const historyItems = history.slice(0, 5);
  const diagnostics = [
    { label: "Backend", state: backendStatus.state, detail: backendStatus.detail },
    { label: "Session", state: hasFeatureAccess ? "ready" : sessionStatus.tone, detail: hasFeatureAccess ? "Authenticated and ready to run." : sessionStatus.statusDetail },
    { label: "Preset", state: "ready", detail: `${activePreset.name} is loaded with ${enabledCount} entity controls.` },
    { label: "Review", state: pdfResult || result ? "ready" : "checking", detail: pdfResult ? "Audit report and review modes are available." : "Run a scan to unlock review tools." },
  ];

  useEffect(() => {
    let alive = true;
    fetch(`${API_BASE_URL}/v1/services`)
      .then((response) => {
        if (!alive) return;
        setBackendStatus({
          state: response.ok ? "ready" : "warn",
          detail: response.ok ? "Reachable and responding." : "Service endpoint returned an unexpected status.",
        });
      })
      .catch(() => {
        if (!alive) return;
        setBackendStatus({
          state: "danger",
          detail: "Backend is offline or unreachable from the UI.",
        });
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!file) {
      setOriginalNumPages(0);
      setOriginalPreviewUrl((previous) => {
        if (previous) URL.revokeObjectURL(previous);
        return null;
      });
      return;
    }

    const nextUrl = URL.createObjectURL(file);
    setOriginalPreviewUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return nextUrl;
    });

    return () => {
      URL.revokeObjectURL(nextUrl);
    };
  }, [file]);

  useEffect(() => {
    if (!busy) {
      setProgressIndex(0);
      return undefined;
    }

    setProgressIndex(0);
    const timer = window.setInterval(() => {
      setProgressIndex((current) => Math.min(current + 1, progressSteps.length - 1));
    }, 1100);

    return () => window.clearInterval(timer);
  }, [busy, activeTab, progressSteps.length]);

  useEffect(() => {
    saveHistory(history);
  }, [history]);

  useEffect(() => {
    savePresetId(selectedPresetId);
  }, [selectedPresetId]);

  useEffect(() => () => {
    if (redactedUrlRef.current) URL.revokeObjectURL(redactedUrlRef.current);
  }, []);

  function updateHistory(entry) {
    setHistory((previous) => {
      const next = [entry, ...previous.filter((item) => item.id !== entry.id)];
      return next.slice(0, 8);
    });
  }

  function applyPreset(presetId) {
    const preset = PRESETS.find((item) => item.id === presetId);
    if (!preset) return;
    setSelectedPresetId(preset.id);
    setOptions(cloneOptions(preset.options));
    setReversible(preset.reversible);
    if (activeTab === "text" && preset.sampleText) {
      setText(preset.sampleText);
    }
  }

  function handleOptionChange(key) {
    setOptions((previous) => ({ ...previous, [key]: !previous[key] }));
  }

  function handleDrop(event) {
    event.preventDefault();
    setIsDragging(false);
    const droppedFile = event.dataTransfer.files[0];
    if (droppedFile?.type === "application/pdf") setFile(droppedFile);
  }

  function handleDragOver(event) {
    event.preventDefault();
    setIsDragging(true);
  }

  function handleDragLeave() {
    setIsDragging(false);
  }

  async function handleSubmit(event) {
    event.preventDefault();

    if (activeTab === "text") {
      setResult(null);
      const response = await runPiiMasking(text, reversible, options);
      if (!response) return;
      setResult(response);
      updateHistory({
        id: `${Date.now()}-text`,
        mode: "text",
        title: activePreset.name,
        timestamp: new Date().toISOString(),
        detail: `${response.sensitive_entities?.length || 0} entities`,
        presetId: activePreset.id,
        options,
        reversible,
        textSnapshot: text,
        textPreview: text.slice(0, 120),
      });
      return;
    }

    if (!file) return;
    if (redactedUrlRef.current) {
      URL.revokeObjectURL(redactedUrlRef.current);
      redactedUrlRef.current = null;
    }
    setPdfResult(null);
    const response = await runPdfMasking(file, options);
    if (!response) return;
    const strictBlob = new Blob([response.blob], { type: "application/pdf" });
    const strictUrl = URL.createObjectURL(strictBlob);
    redactedUrlRef.current = strictUrl;
    setPdfResult({
      url: strictUrl,
      downloadUrl: strictUrl,
      count: response.redactedCount,
      entities: response.entities || [],
      numPages: 0,
      generatedAt: new Date().toISOString(),
    });
    setPreviewMode("redacted");
    updateHistory({
      id: `${Date.now()}-pdf`,
      mode: "pdf",
      title: file.name,
      timestamp: new Date().toISOString(),
      detail: `${response.redactedCount || 0} redactions`,
      presetId: activePreset.id,
      options,
      entityCount: response.entities?.length || 0,
    });
  }

  function exportAuditReport() {
    const report = buildAuditReport({
      activeTab,
      file,
      text,
      presetName: activePreset.name,
      options,
      pdfResult,
      result,
      entityGroups,
    });
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    triggerDownload(blob, `aiccel_${activeTab}_audit_report.json`);
  }

  function restoreFromHistory(item) {
    setActiveTab(item.mode);
    setSelectedPresetId(item.presetId || PRESETS[0].id);
    setOptions(cloneOptions(item.options));
    if (typeof item.reversible === "boolean") {
      setReversible(item.reversible);
    }
    if (item.mode === "text" && (item.textSnapshot || item.textPreview)) {
      setText(item.textSnapshot || item.textPreview);
    }
  }

  const textRiskTone = result?.risk_score > 0.5 ? "warn" : "safe";
  const pdfViewerWidth = previewMode === "compare" ? 420 : 640;

  return (
    <div className="feature-page pii-experience">
      <FeaturePageHeader
        icon={<Icons.IconPII />}
        iconBg="linear-gradient(135deg, #f5e8d4 0%, #ead7bd 100%)"
        title="PII Masking"
        desc="Premium document redaction with review tools, saved presets, diagnostics, and audit-friendly exports."
      />

      <section className="pii-hero-shell">
        <div className="pii-hero-copy">
          <span className="pii-kicker">Operational Privacy Control</span>
          <h3>Mask sensitive text and PDFs with a review-first workflow.</h3>
          <p>
            AICCEL now gives you setup presets, live diagnostics, processing checkpoints, side-by-side review,
            and audit exports so the masking flow feels production-ready instead of opaque.
          </p>
        </div>
        <div className="pii-hero-stats">
          <StatCard label="Preset" value={activePreset.name} tone="warm" />
          <StatCard label="Enabled Controls" value={enabledCount} tone="neutral" />
          <StatCard
            label="Backend"
            value={backendStatus.state === "ready" ? "Online" : backendStatus.state === "checking" ? "Checking" : "Attention"}
            tone={backendStatus.state === "ready" ? "safe" : "warn"}
          />
        </div>
      </section>

      {!hasFeatureAccess && (
        <div className="key-alert">
          <span>{sessionStatus.alertMessage}</span>
        </div>
      )}

      <section className="pii-control-strip">
        <div className="pdf-tabs">
          <button className={`pdf-tab ${activeTab === "text" ? "active" : ""}`} onClick={() => setActiveTab("text")} type="button">
            <span className="pdf-tab-icon"><Icons.IconFileText /></span>
            Text Scanner
          </button>
          <button className={`pdf-tab ${activeTab === "pdf" ? "active" : ""}`} onClick={() => setActiveTab("pdf")} type="button">
            <span className="pdf-tab-icon"><Icons.IconFilePdf /></span>
            PDF Redactor
            <span className="pdf-tab-badge">PRO</span>
          </button>
        </div>

        <div className="pii-preset-row">
          {PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              className={`pii-preset-pill ${selectedPresetId === preset.id ? "active" : ""}`}
              onClick={() => applyPreset(preset.id)}
            >
              <span>{preset.name}</span>
              <small>{preset.description}</small>
            </button>
          ))}
        </div>
      </section>

      <section className="pii-diagnostics-grid">
        {diagnostics.map((diagnostic) => (
          <DiagnosticsItem
            key={diagnostic.label}
            label={diagnostic.label}
            state={diagnostic.state}
            detail={diagnostic.detail}
          />
        ))}
      </section>

      {activeTab === "text" ? (
        <div className="pii-workspace-grid">
          <section className="card pii-panel">
            <div className="pii-panel-head">
              <div>
                <h3>Input + Controls</h3>
                <p>Switch presets, tune entity coverage, and run a trustable scan.</p>
              </div>
              <span className="pii-panel-tag">Text Mode</span>
            </div>

            <form className="form-grid" onSubmit={handleSubmit}>
              <label className="pii-input-label">
                Text to scan
                <textarea
                  className="pii-rich-textarea"
                  rows={10}
                  value={text}
                  onChange={(event) => setText(event.target.value)}
                  placeholder="Paste text with sensitive information..."
                  required
                />

                <div className="agent-prompt-chips" style={{ marginTop: "0.5rem" }}>
                  {PRESETS.map((p) => (
                    <button key={p.id} type="button" className="btn-ghost btn-sm" onClick={() => applyPreset(p.id)}>
                      {p.name}
                    </button>
                  ))}
                </div>
              </label>

              <div className="pii-controls-grid">
                {OPTIONS_LIST.map((option) => (
                  <label key={option.key} className="pii-toggle-card">
                    <div>
                      <strong>{option.label}</strong>
                      <span>{options[option.key] ? "Included in masking run" : "Excluded from current run"}</span>
                    </div>
                    <input type="checkbox" checked={options[option.key]} onChange={() => handleOptionChange(option.key)} />
                  </label>
                ))}
              </div>

              <label className="pii-toggle-card">
                <div>
                  <strong>Reversible tokenization</strong>
                  <span>Keep token mapping for controlled restore flows.</span>
                </div>
                <input type="checkbox" checked={reversible} onChange={(event) => setReversible(event.target.checked)} />
              </label>

              <div className="pii-action-row">
              <button className={`btn-primary${busy ? " btn-loading" : ""}`} disabled={busy || !hasFeatureAccess} type="submit">
                  {busy ? "Scanning..." : "Scan & Mask PII"}
                </button>
                <button type="button" className="btn-secondary" onClick={exportAuditReport} disabled={!result}>
                  Export Audit Report
                </button>
              </div>
            </form>
          </section>

          <section className="card pii-panel">
            <div className="pii-panel-head">
              <div>
                <h3>Results</h3>
                <p>See risk, entity coverage, and masked output in one place.</p>
              </div>
              <span className="pii-panel-tag">Trust Layer</span>
            </div>

            {busy ? (
              <div className="pii-loading-stack">
                <ProgressTracker steps={progressSteps} activeIndex={progressIndex} />
                <div className="aiccel-loader"><span className="dot"></span><span className="dot"></span><span className="dot"></span></div>
                <p className="muted">Running masking, entity validation, and policy checks...</p>
              </div>
            ) : result ? (
              <>
                <div className="result-badges">
                  <ResultBadge type={textRiskTone}>Risk: {result.risk_score ?? "N/A"}</ResultBadge>
                  <ResultBadge type="info">Entities: {sensitiveEntities.length}</ResultBadge>
                  <ResultBadge type="info">Markers: {detectedMarkers.length}</ResultBadge>
                  {injectionDetected && <ResultBadge type="danger">Injection Detected</ResultBadge>}
                </div>

                <div className="pii-summary-grid">
                  <StatCard label="Risk Score" value={result.risk_score ?? "N/A"} tone={textRiskTone === "safe" ? "safe" : "warn"} />
                  <StatCard label="Entities Found" value={sensitiveEntities.length} tone="neutral" />
                  <StatCard label="Detection Markers" value={detectedMarkers.length} tone="warm" />
                </div>

                {maskedParagraph && (
                  <ResultPanel title="Masked Output">
                    <pre>{maskedParagraph}</pre>
                  </ResultPanel>
                )}

                {sensitiveEntities.length > 0 && (
                  <ResultPanel title="Detected Entities">
                    <div className="entity-list">
                      {sensitiveEntities.map((entity, index) => (
                        <div className="entity-item" key={`${entity.kind}-${index}`}>
                          <span className="entity-type">{entity.kind}</span>
                          <span className="entity-value">{entity.value_preview}</span>
                        </div>
                      ))}
                    </div>
                  </ResultPanel>
                )}

                {detectedMarkers.length > 0 && (
                  <div className="code-block">Detected markers: {detectedMarkers.join(" | ")}</div>
                )}
              </>
            ) : (
              <div className="pii-empty-state">
                <div className="pdf-viewer-empty-icon"><Icons.IconShield /></div>
                <h3>Mask with confidence</h3>
                <p className="muted">Choose a preset, paste content, and run a scan to generate masked output with review metadata.</p>
              </div>
            )}
          </section>
        </div>
      ) : (
        <form onSubmit={handleSubmit}>
          <div className="pii-workspace-grid pii-workspace-grid-pdf">
            <aside className="card pii-panel pii-side-rail">
              <div className="pii-panel-head">
                <div>
                  <h3>Review Controls</h3>
                  <p>Upload, choose coverage, and rerun safely from presets or history.</p>
                </div>
                <span className="pii-panel-tag">PDF Mode</span>
              </div>

              <div
                className="pdf-upload-zone pii-upload-zone"
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onClick={() => fileInputRef.current?.click()}
                style={{
                  borderColor: isDragging ? "var(--grey-950)" : undefined,
                  background: isDragging ? "linear-gradient(135deg, rgba(19, 19, 19, 0.06), rgba(19, 19, 19, 0.02))" : undefined,
                }}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="application/pdf"
                  style={{ display: "none" }}
                  onChange={(event) => setFile(event.target.files[0])}
                />
                {file ? (
                  <div className="pdf-file-info">
                    <div className="pdf-file-icon"><Icons.IconFilePdf /></div>
                    <div className="pdf-file-name">{file.name}</div>
                    <div className="pdf-file-size">{(file.size / 1024 / 1024).toFixed(2)} MB</div>
                  </div>
                ) : (
                  <div className="pdf-upload-prompt">
                    <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}><Icons.IconUpload /></div>
                    <p style={{ fontWeight: 600 }}>Drop PDF here</p>
                    <p className="muted" style={{ fontSize: "0.82rem" }}>or click to browse for a document</p>
                  </div>
                )}
              </div>

              <div className="pii-side-section">
                <div className="pii-section-head">
                  <h4>Masking Coverage</h4>
                  <span>{enabledCount} active</span>
                </div>
                <div className="pii-controls-grid compact">
                  {OPTIONS_LIST.map((option) => (
                    <label key={option.key} className="pii-toggle-card compact">
                      <div>
                        <strong>{option.label}</strong>
                        <span>{options[option.key] ? "On" : "Off"}</span>
                      </div>
                      <input type="checkbox" checked={options[option.key]} onChange={() => handleOptionChange(option.key)} />
                    </label>
                  ))}
                </div>
              </div>

              <div className="pii-action-stack">
              <button className={`btn-primary btn-full${busy ? " btn-loading" : ""}`} disabled={busy || !hasFeatureAccess || !file} type="submit">
                  {busy ? "Redacting..." : <><Icons.IconLock /> Redact PDF</>}
                </button>
                <button type="button" className="btn-secondary btn-full" onClick={exportAuditReport} disabled={!pdfResult}>
                  Export Audit Report
                </button>
              </div>

              <div className="pii-side-section">
                <div className="pii-section-head">
                  <h4>Recent Runs</h4>
                  <span>Local</span>
                </div>
                <div className="pii-history-list">
                  {historyItems.length ? historyItems.map((item) => (
                    <button key={item.id} type="button" className="pii-history-item" onClick={() => restoreFromHistory(item)}>
                      <strong>{item.title}</strong>
                      <span>{item.detail}</span>
                      <small>{formatTimestamp(item.timestamp)}</small>
                    </button>
                  )) : <p className="muted">No runs saved yet.</p>}
                </div>
              </div>
            </aside>

            <main className="card pii-panel pii-review-shell">
              <div className="pii-panel-head">
                <div>
                  <h3>Document Review</h3>
                  <p>Inspect the output before export with review modes and trust signals.</p>
                </div>
                <span className="pii-panel-tag">Preview</span>
              </div>

              {busy ? (
                <div className="pdf-viewer-loading">
                  <ProgressTracker steps={progressSteps} activeIndex={progressIndex} />
                  <div className="pdf-scan-animation">
                    <div className="pdf-scan-bar"></div>
                  </div>
                  <h3>{progressSteps[progressIndex]}</h3>
                  <p className="muted">AICCEL is running GLiNER, structured validation, and permanent PDF redaction.</p>
                </div>
              ) : pdfResult ? (
                <div className="pdf-viewer-content">
                  <div className="pii-review-topbar">
                    <div className="pii-summary-grid">
                      <StatCard label="Redactions" value={pdfResult.count} tone="safe" />
                      <StatCard label="Entities Found" value={pdfResult.entities.length} tone="neutral" />
                      <StatCard label="Entity Types" value={Object.keys(entityGroups).length} tone="warm" />
                    </div>

                    <div className="pii-toolbar-actions">
                      <div className="pii-preview-tabs">
                        {[
                          { id: "redacted", label: "Redacted" },
                          { id: "original", label: "Original" },
                          { id: "compare", label: "Compare" },
                        ].map((mode) => (
                          <button
                            key={mode.id}
                            type="button"
                            className={`pii-preview-tab ${previewMode === mode.id ? "active" : ""}`}
                            onClick={() => setPreviewMode(mode.id)}
                          >
                            {mode.label}
                          </button>
                        ))}
                      </div>

                      <a
                        href={pdfResult.downloadUrl || pdfResult.url}
                        download={`redacted_${file?.name || "document.pdf"}`}
                        className="btn-primary btn-sm"
                      >
                        Download Redacted PDF
                      </a>
                    </div>
                  </div>

                  <div className="pii-trust-strip">
                    <span><Icons.IconCheck /> Structured values are rule-validated before masking.</span>
                    <span><Icons.IconRobot /> GLiNER-driven entities are surfaced for review context.</span>
                    <span><Icons.IconDocs /> Export an audit report with entity metadata anytime.</span>
                  </div>

                  <div className={`pii-preview-grid ${previewMode === "compare" ? "compare" : ""}`}>
                    {(previewMode === "original" || previewMode === "compare") && (
                      <section className="pii-preview-pane">
                        <div className="pii-preview-head">
                          <h4>Original</h4>
                          <span>{file?.name || "Input PDF"}</span>
                        </div>
                        <div className="pdf-iframe-wrapper">
                          {originalPreviewUrl ? (
                            <Document
                              file={originalPreviewUrl}
                              loading={<div className="pii-preview-empty">Rendering original document...</div>}
                              onLoadSuccess={({ numPages }) => setOriginalNumPages(numPages)}
                              error={<div className="pii-preview-empty">Original preview unavailable.</div>}
                            >
                              {Array.from({ length: originalNumPages || 1 }, (_, index) => index + 1).map((pageNumber) => (
                                <Page
                                  key={`original_${pageNumber}`}
                                  pageNumber={pageNumber}
                                  renderTextLayer={false}
                                  renderAnnotationLayer={false}
                                  width={pdfViewerWidth}
                                  className="pdf-page-render"
                                />
                              ))}
                            </Document>
                          ) : (
                            <div className="pii-preview-empty">Upload a PDF to preview the original document.</div>
                          )}
                        </div>
                      </section>
                    )}

                    {(previewMode === "redacted" || previewMode === "compare") && (
                      <section className="pii-preview-pane">
                        <div className="pii-preview-head">
                          <h4>Redacted</h4>
                          <span>{formatTimestamp(pdfResult.generatedAt)}</span>
                        </div>
                        <div className="pdf-iframe-wrapper">
                          <Document
                            file={pdfResult.url}
                            loading={<div className="pii-preview-empty">Rendering redacted document...</div>}
                            onLoadSuccess={({ numPages }) => setPdfResult((previous) => (previous ? { ...previous, numPages } : previous))}
                            error={<div className="pii-preview-empty">Failed to render preview. Please use the download button.</div>}
                          >
                            {Array.from({ length: pdfResult.numPages || 1 }, (_, index) => index + 1).map((pageNumber) => (
                              <Page
                                key={`redacted_${pageNumber}`}
                                pageNumber={pageNumber}
                                renderTextLayer={false}
                                renderAnnotationLayer={false}
                                width={pdfViewerWidth}
                                className="pdf-page-render"
                              />
                            ))}
                          </Document>
                        </div>
                      </section>
                    )}
                  </div>

                  <div className="pii-entity-review-grid">
                    <section className="pdf-entity-summary pii-entity-summary-enhanced">
                      <div className="pii-section-head">
                        <h4>Detected Entities</h4>
                        <span>{pdfResult.entities.length} total</span>
                      </div>
                      {Object.entries(entityGroups).length ? Object.entries(entityGroups).map(([type, entities]) => {
                        const Icon = ENTITY_TYPE_ICONS[type] || Icons.IconShield;
                        return (
                          <div key={type} className="pii-entity-cluster">
                            <div className="pdf-entity-group-header">
                              <span className="pii-entity-cluster-title"><Icon /> {ENTITY_TYPE_LABELS[type] || type}</span>
                              <span className="pdf-entity-count">{entities.length}</span>
                            </div>
                            <div className="pdf-entity-values">
                              {entities.map((entity, index) => {
                                const trust = getEntityTrust(type, entity);
                                return (
                                  <div key={`${type}-${index}`} className="pii-entity-review-card">
                                    <strong>{entity.value}</strong>
                                    <span>Page {entity.page || 1}</span>
                                    <small>{trust.source} / {trust.confidence}</small>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        );
                      }) : <p className="muted">No entities detected in the latest run.</p>}
                    </section>

                    <section className="pii-review-notes">
                      <div className="pii-section-head">
                        <h4>Reviewer Notes</h4>
                        <span>Checklist</span>
                      </div>
                      <ul className="pii-note-list">
                        <li>Compare the original and redacted document before export.</li>
                        <li>Use saved presets to keep similar document classes consistent.</li>
                        <li>Audit exports include entity counts, active controls, and run metadata.</li>
                        <li>Rerun the document after changing any coverage toggle or preset.</li>
                      </ul>
                    </section>
                  </div>
                </div>
              ) : (
                <div className="pdf-viewer-empty pii-empty-state">
                  <div className="pdf-viewer-empty-icon"><Icons.IconVault /></div>
                  <h3>Premium PDF Redactor</h3>
                  <p className="muted">Upload a PDF to unlock diagnostics, review modes, audit export, and a side-by-side redaction workflow.</p>
                </div>
              )}
            </main>
          </div>
        </form>
      )}

      <section className="card pii-capability-grid-shell">
        <div className="card-head">
          <h3>Why This Flow Feels Stronger</h3>
          <p>These upgrades are focused on trust, repeatability, and reviewer efficiency.</p>
        </div>
        <div className="feature-cards-grid pii-capability-grid">
          {[
            { Icon: Icons.IconShield, title: "Setup Diagnostics", desc: "The page now tells you whether the backend, API key, and review flow are ready before you start." },
            { Icon: Icons.IconDocs, title: "Audit Export", desc: "Each run can produce a downloadable report with active controls, entity counts, and timestamps." },
            { Icon: Icons.IconRefresh, title: "Saved Presets", desc: "Resume, finance, KYC, and contact-only presets cut setup time and keep runs consistent." },
            { Icon: Icons.IconFilePdf, title: "Review Modes", desc: "Switch between original, redacted, and compare views before sending the output downstream." },
            { Icon: Icons.IconDatabase, title: "Run History", desc: "Recent runs stay local so you can restore a previous preset and workflow quickly." },
            { Icon: Icons.IconRobot, title: "Trust Signals", desc: "Structured entities show rule-verification context while semantic ones stay visible for review." },
          ].map((item) => (
            <article className="sublist-item pii-capability-card" key={item.title}>
              <h4>{item.Icon && <item.Icon />} {item.title}</h4>
              <p>{item.desc}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
