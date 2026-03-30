import { useState, useRef, useEffect } from "react";
import { Document, Page, pdfjs } from "react-pdf";

import { useApp } from "../context/AppContext";
import { Field, FeaturePageHeader, ResultPanel, ResultBadge } from "./Shared";
import * as Icons from "./Icons";

import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url
).toString();

const BIOMED_ENTITY_ICONS = {
  Disease: Icons.IconDisease,
  Drug: Icons.IconDrug,
  "Drug dosage": Icons.IconDosage,
  "Drug frequency": Icons.IconFrequency,
  "Lab test": Icons.IconLabTest,
  "Lab test value": Icons.IconValue,
  "Demographic information": Icons.IconPatient,
};

const BIOMED_ENTITY_LABELS = {
  Disease: "Diseases",
  Drug: "Drugs",
  "Drug dosage": "Drug Dosages",
  "Drug frequency": "Drug Frequencies",
  "Lab test": "Lab Tests",
  "Lab test value": "Lab Test Values",
  "Demographic information": "Demographics",
};

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

function groupPdfEntities(entities) {
  const groups = {};
  for (const entity of entities || []) {
    const type = String(entity.type || "unknown");
    if (!groups[type]) groups[type] = [];
    groups[type].push(entity);
  }
  return groups;
}

export default function BiomedMasking() {
  const { runBiomedMasking, runBiomedPdfMasking, busy, hasActiveKey, setActiveView } = useApp();

  // Mode
  const [activeTab, setActiveTab] = useState("text");

  // Text mode state
  const [text, setText] = useState(
    "The patient, a 45-year-old male, was diagnosed with type 2 diabetes mellitus and hypertension.\nHe was prescribed Metformin 500mg twice daily and Lisinopril 10mg once daily.\nA recent lab test showed elevated HbA1c levels at 8.2%."
  );
  const [threshold, setThreshold] = useState(0.5);
  const [selectedLabels, setSelectedLabels] = useState(Object.keys(BIOMED_ENTITY_LABELS));
  const [result, setResult] = useState(null);

  // PDF mode state
  const [file, setFile] = useState(null);
  const [pdfResult, setPdfResult] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [previewMode, setPreviewMode] = useState("redacted");
  const [originalPreviewUrl, setOriginalPreviewUrl] = useState(null);
  const [originalNumPages, setOriginalNumPages] = useState(0);
  const fileInputRef = useRef(null);
  const redactedUrlRef = useRef(null);

  // Text result data
  const maskedText = result?.masked_text || "";
  const extractedEntities = result?.extracted_entities || {};
  const allEntities = Object.entries(extractedEntities)
    .flatMap(([kind, values]) => values.map((val) => ({ kind, value: val })))
    .filter((e) => e.kind !== "errors" && e.kind !== "warnings");

  // PDF result data
  const pdfEntityGroups = groupPdfEntities(pdfResult?.entities || []);

  // Cleanup object URLs
  useEffect(() => {
    if (!file) {
      setOriginalNumPages(0);
      setOriginalPreviewUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      return;
    }
    const nextUrl = URL.createObjectURL(file);
    setOriginalPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return nextUrl;
    });
    return () => URL.revokeObjectURL(nextUrl);
  }, [file]);

  useEffect(
    () => () => {
      if (redactedUrlRef.current) URL.revokeObjectURL(redactedUrlRef.current);
    },
    []
  );

  // Text submit
  async function handleTextSubmit(e) {
    e.preventDefault();
    if (selectedLabels.length === 0) return;
    setResult(null);
    const res = await runBiomedMasking(text, threshold, selectedLabels);
    if (res) setResult(res);
  }

  // PDF submit
  async function handlePdfSubmit(e) {
    e.preventDefault();
    if (!file || selectedLabels.length === 0) return;
    if (redactedUrlRef.current) {
      URL.revokeObjectURL(redactedUrlRef.current);
      redactedUrlRef.current = null;
    }
    setPdfResult(null);
    const response = await runBiomedPdfMasking(file, threshold, selectedLabels);
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
  }

  // Drag & drop
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

  const pdfViewerWidth = previewMode === "compare" ? 420 : 640;

  return (
    <div className="feature-page">
      <FeaturePageHeader
        icon={<Icons.IconBioMed />}
        iconBg="var(--blue-soft)"
        title="BioMed Masking"
        desc="Specialized zero-shot entity recognition for healthcare and life sciences. Powered by GLiNER-BioMed."
      />

      {!hasActiveKey && (
        <div className="key-alert">
          <span>Activate an API key to use BioMedical Masking.</span>
          <button className="btn-ghost btn-sm" onClick={() => setActiveView("keys")}>
            Get API Key
          </button>
        </div>
      )}

      {/* Tab switcher */}
      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1rem" }}>
        <button
          className={`pdf-tab ${activeTab === "text" ? "active" : ""}`}
          onClick={() => setActiveTab("text")}
          type="button"
        >
          <span className="pdf-tab-icon"><Icons.IconFileText /></span>
          Text Scanner
        </button>
        <button
          className={`pdf-tab ${activeTab === "pdf" ? "active" : ""}`}
          onClick={() => setActiveTab("pdf")}
          type="button"
        >
          <span className="pdf-tab-icon"><Icons.IconFilePdf /></span>
          PDF Redactor
          <span className="pdf-tab-badge">PRO</span>
        </button>
      </div>

      {/* Configuration */}
      <div style={{ marginBottom: "1.5rem", display: "flex", flexDirection: "column", gap: "1rem" }}>
        <Field label={`Confidence Threshold: ${threshold}`}>
          <input
            type="range"
            min="0.1"
            max="0.9"
            step="0.05"
            value={threshold}
            onChange={(e) => setThreshold(parseFloat(e.target.value))}
            style={{ width: "100%" }}
          />
        </Field>

        <Field label="Medical Entities to Redact">
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", padding: "0.5rem 0" }}>
            {Object.entries(BIOMED_ENTITY_LABELS).map(([key, label]) => {
              const active = selectedLabels.includes(key);
              return (
                <label key={key} style={{ display: "flex", alignItems: "center", gap: "0.4rem", cursor: "pointer", whiteSpace: "nowrap", opacity: active ? 1 : 0.6 }}>
                  <input
                    type="checkbox"
                    checked={active}
                    onChange={() => {
                      setSelectedLabels((prev) =>
                        prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
                      );
                    }}
                    style={{ accentColor: "var(--primary)" }}
                  />
                  <span style={{ fontSize: "0.85rem", fontWeight: active ? 500 : 400 }}>
                    {label}
                  </span>
                </label>
              );
            })}
          </div>
        </Field>
      </div>

      {activeTab === "text" ? (
        /* ── TEXT MODE ────────────────────────────────── */
        <div className="feature-split">
          <section className="card">
            <div className="card-head">
              <h3>Medical Records</h3>
              <p>Enter clinical notes, discharge summaries, or prescriptions.</p>
            </div>
            <form className="form-grid" onSubmit={handleTextSubmit}>
              <Field label="Clinical Text">
                <textarea
                  rows={10}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Enter medical text..."
                  required
                />
              </Field>

              <div className="agent-prompt-chips" style={{ marginBottom: "1rem" }}>
                {[
                  { name: "Discharge Summary", text: "Patient John Doe, 45, discharged after treatment for Acute Myocardial Infarction. Prescribed Atorvastatin 40mg and Aspirin 81mg." },
                  { name: "Lab Report", text: "Blood work for Jane Smith shows HbA1c of 7.5% and fasting glucose of 140 mg/dL. Diagnosis: Type 2 Diabetes." },
                  { name: "Prescription", text: "Rx: Amoxicillin 500mg TID for 10 days. Take with food. Patient has allergy to Penicillin." },
                ].map((s) => (
                  <button key={s.name} type="button" className="btn-ghost btn-sm" onClick={() => setText(s.text)}>
                    {s.name}
                  </button>
                ))}
              </div>

              <button
                className={`btn-primary btn-full${busy ? " btn-loading" : ""}`}
                disabled={busy || !hasActiveKey}
                type="submit"
              >
                {busy ? "Analyzing BioMed Data..." : "Mask Medical Entities"}
              </button>
            </form>
          </section>

          <section className="card">
            <div className="card-head">
              <h3>Masked Output</h3>
              <p>BioMedical entities are identified and tokenized.</p>
            </div>
            {result ? (
              <>
                <div className="result-badges">
                  <ResultBadge type="info">Entities Found: {allEntities.length}</ResultBadge>
                  <ResultBadge type="safe">Model: GLiNER BioMed v1.0</ResultBadge>
                </div>

                {maskedText && (
                  <ResultPanel title="Anonymized Record">
                    <pre style={{ whiteSpace: "pre-wrap" }}>{maskedText}</pre>
                  </ResultPanel>
                )}

                {allEntities.length > 0 && (
                  <ResultPanel title="Extracted Medical Entities">
                    <div className="entity-list">
                      {allEntities.map((entity, i) => (
                        <div className="entity-item" key={i}>
                          <span className="entity-type">{entity.kind}</span>
                          <span className="entity-value">{entity.value}</span>
                        </div>
                      ))}
                    </div>
                  </ResultPanel>
                )}
              </>
            ) : busy ? (
              <div style={{ display: "grid", gap: "1rem", padding: "1rem 0" }}>
                <div className="aiccel-loader" style={{ justifyContent: "center" }}>
                  <span className="dot"></span>
                  <span className="dot"></span>
                  <span className="dot"></span>
                </div>
                <p className="muted" style={{ textAlign: "center" }}>
                  Identifying diseases, drugs, and lab values...
                </p>
                <div className="skeleton skeleton-block" style={{ height: "100px" }}></div>
                <div className="skeleton skeleton-line"></div>
                <div className="skeleton skeleton-line" style={{ width: "80%" }}></div>
              </div>
            ) : (
              <div className="empty-state">
                <p className="muted">Submit medical text to see specialized masking results.</p>
              </div>
            )}
          </section>
        </div>
      ) : (
        /* ── PDF MODE ────────────────────────────────── */
        <form onSubmit={handlePdfSubmit}>
          <div className="feature-split" style={{ gridTemplateColumns: "1fr 1.5fr" }}>
            {/* Left: Upload + Controls */}
            <section className="card">
              <div className="card-head">
                <h3>Upload Medical PDF</h3>
                <p>Upload clinical PDFs — discharge summaries, lab reports, prescriptions.</p>
              </div>

              <div
                className="pdf-upload-zone pii-upload-zone"
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onClick={() => fileInputRef.current?.click()}
                style={{
                  borderColor: isDragging ? "var(--grey-950)" : undefined,
                  background: isDragging
                    ? "linear-gradient(135deg, rgba(19,19,19,0.06), rgba(19,19,19,0.02))"
                    : undefined,
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
                    <div className="pdf-file-icon">
                      <Icons.IconFilePdf />
                    </div>
                    <div className="pdf-file-name">{file.name}</div>
                    <div className="pdf-file-size">
                      {(file ? file.size / 1024 / 1024 : 0).toFixed(2)} MB
                    </div>
                  </div>
                ) : (
                  <div className="pdf-upload-prompt">
                    <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>
                      <Icons.IconUpload />
                    </div>
                    <p>
                      <strong>Drop a PDF here</strong> or click to browse
                    </p>
                    <p className="muted" style={{ fontSize: "0.8rem" }}>
                      Max 20 MB. Only PDF files accepted.
                    </p>
                  </div>
                )}
              </div>

              <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem", flexWrap: "wrap" }}>
                <button
                  className={`btn-primary${busy ? " btn-loading" : ""}`}
                  disabled={busy || !hasActiveKey || !file}
                  type="submit"
                >
                  {busy ? "Redacting..." : "Redact Medical PDF"}
                </button>
                {file && (
                  <button
                    type="button"
                    className="btn-ghost btn-sm"
                    onClick={() => {
                      setFile(null);
                      setPdfResult(null);
                    }}
                  >
                    Clear
                  </button>
                )}
              </div>

              {/* Entity Summary */}
              {pdfResult && pdfResult.entities.length > 0 && (
                <div style={{ marginTop: "1rem" }}>
                  <h4 style={{ marginBottom: "0.5rem" }}>Detected Medical Entities</h4>
                  <div className="entity-list">
                    {Object.entries(pdfEntityGroups).map(([type, entities]) => {
                      const IconComp = BIOMED_ENTITY_ICONS[type];
                      const label = BIOMED_ENTITY_LABELS[type] || type;
                      return (
                        <div key={type} style={{ marginBottom: "0.5rem" }}>
                          <div style={{ fontWeight: 600, fontSize: "0.85rem", marginBottom: "0.25rem", display: "flex", alignItems: "center", gap: "0.3rem" }}>
                            {IconComp && <IconComp />} {label} ({entities.length})
                          </div>
                          {entities.map((e, i) => (
                            <div className="entity-item" key={`${type}-${i}`}>
                              <span className="entity-value">{e.value}</span>
                              <span className="muted" style={{ fontSize: "0.75rem" }}>
                                p.{e.page}
                              </span>
                            </div>
                          ))}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </section>

            {/* Right: PDF Preview + Results */}
            <section className="card">
              <div className="card-head">
                <h3>Redacted Preview</h3>
                <p>View the redacted PDF with medical entities blacked out.</p>
              </div>

              {pdfResult ? (
                <>
                  <div className="result-badges" style={{ marginBottom: "0.75rem" }}>
                    <ResultBadge type="safe">
                      {pdfResult.count} Redaction{pdfResult.count !== 1 ? "s" : ""}
                    </ResultBadge>
                    <ResultBadge type="info">
                      {pdfResult.entities.length} Entit{pdfResult.entities.length !== 1 ? "ies" : "y"}
                    </ResultBadge>
                    <ResultBadge type="neutral">GLiNER BioMed v1.0</ResultBadge>
                  </div>

                  {/* View mode toggle */}
                  <div style={{ display: "flex", gap: "0.4rem", marginBottom: "0.5rem" }}>
                    <button
                      type="button"
                      className={`btn-ghost btn-sm ${previewMode === "redacted" ? "active" : ""}`}
                      onClick={() => setPreviewMode("redacted")}
                    >
                      Redacted
                    </button>
                    {originalPreviewUrl && (
                      <button
                        type="button"
                        className={`btn-ghost btn-sm ${previewMode === "original" ? "active" : ""}`}
                        onClick={() => setPreviewMode("original")}
                      >
                        Original
                      </button>
                    )}
                    {originalPreviewUrl && (
                      <button
                        type="button"
                        className={`btn-ghost btn-sm ${previewMode === "compare" ? "active" : ""}`}
                        onClick={() => setPreviewMode("compare")}
                      >
                        Compare
                      </button>
                    )}
                  </div>

                  <div
                    className="pdf-viewer-wrapper"
                    style={{
                      display: previewMode === "compare" ? "grid" : "block",
                      gridTemplateColumns: previewMode === "compare" ? "1fr 1fr" : undefined,
                      gap: previewMode === "compare" ? "0.5rem" : undefined,
                    }}
                  >
                    {(previewMode === "original" || previewMode === "compare") && originalPreviewUrl && (
                      <div>
                        <p className="muted" style={{ fontSize: "0.75rem", marginBottom: "0.3rem" }}>
                          Original
                        </p>
                        <Document file={originalPreviewUrl} onLoadSuccess={({ numPages }) => setOriginalNumPages(numPages)}>
                          {Array.from({ length: originalNumPages }, (_, i) => (
                            <Page key={`orig-${i}`} pageNumber={i + 1} width={pdfViewerWidth} />
                          ))}
                        </Document>
                      </div>
                    )}
                    {(previewMode === "redacted" || previewMode === "compare") && pdfResult.url && (
                      <div>
                        {previewMode === "compare" && (
                          <p className="muted" style={{ fontSize: "0.75rem", marginBottom: "0.3rem" }}>
                            Redacted
                          </p>
                        )}
                        <Document file={pdfResult.url} onLoadSuccess={({ numPages }) => setPdfResult((prev) => prev ? { ...prev, numPages } : prev)}>
                          {Array.from({ length: pdfResult.numPages || 1 }, (_, i) => (
                            <Page key={`red-${i}`} pageNumber={i + 1} width={pdfViewerWidth} />
                          ))}
                        </Document>
                      </div>
                    )}
                  </div>

                  <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.75rem" }}>
                    <button
                      type="button"
                      className="btn-primary btn-sm"
                      onClick={() => {
                        const blob = new Blob([pdfResult.url], { type: "application/pdf" });
                        // Use the actual redacted URL for download
                        const link = document.createElement("a");
                        link.href = pdfResult.downloadUrl;
                        link.download = `biomed_redacted_${file?.name || "document.pdf"}`;
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                      }}
                    >
                      Download Redacted PDF
                    </button>
                  </div>
                </>
              ) : busy ? (
                <div style={{ display: "grid", gap: "1rem", padding: "2rem 0" }}>
                  <div className="aiccel-loader" style={{ justifyContent: "center" }}>
                    <span className="dot"></span>
                    <span className="dot"></span>
                    <span className="dot"></span>
                  </div>
                  <p className="muted" style={{ textAlign: "center" }}>
                    Scanning PDF for diseases, drugs, lab values, and demographics...
                  </p>
                  <div className="skeleton skeleton-block" style={{ height: "200px" }}></div>
                </div>
              ) : (
                <div className="empty-state" style={{ padding: "3rem 1rem", textAlign: "center" }}>
                  <div style={{ fontSize: "2.5rem", marginBottom: "0.5rem", opacity: 0.3 }}>
                    <Icons.IconBioMed />
                  </div>
                  <h3>Upload a medical PDF</h3>
                  <p className="muted">
                    Drop or select a PDF to redact diseases, drugs, lab results, and patient demographics.
                  </p>
                </div>
              )}
            </section>
          </div>
        </form>
      )}

      {/* Healthcare compliance section */}
      <section className="card" style={{ marginTop: "1.5rem" }}>
        <div className="card-head">
          <h3>Healthcare Compliance</h3>
          <p>
            Protect Patient Health Information (PHI) before processing with Large Language Models.
          </p>
        </div>
        <div className="feature-cards-grid">
          {[
            {
              Icon: Icons.IconLabTest,
              title: "Lab Results",
              desc: "Detects HbA1c, Blood Glucose, and other clinical measurements.",
            },
            {
              Icon: Icons.IconDrug,
              title: "Pharmacology",
              desc: "Identifies drug names, dosages, and administration frequencies.",
            },
            {
              Icon: Icons.IconDisease,
              title: "Diagnostics",
              desc: "Categorizes diseases, syndromes, and acute conditions.",
            },
            {
              Icon: Icons.IconPatient,
              title: "Demographics",
              desc: "Masks age, gender, and other identifiable patient traits.",
            },
          ].map((item) => (
            <article className="sublist-item" key={item.title}>
              <h4>
                {item.Icon && <item.Icon />} {item.title}
              </h4>
              <p>{item.desc}</p>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
