export function Field({ label, children }) {
  return (
    <div className="field">
      <span>{label}</span>
      {children}
    </div>
  );
}

export function ToggleField({ label, value, onChange }) {
  return (
    <div className="toggle-field">
      <span>{label}</span>
      <input type="checkbox" checked={value} onChange={(e) => onChange(e.target.checked)} />
    </div>
  );
}

export function ResultPanel({ title, children, onCopy, copyText }) {
  return (
    <div className="result-panel">
      <div className="result-panel-header">
        <h4>{title || "Result"}</h4>
        {onCopy ? <button className="btn-ghost btn-sm" onClick={() => onCopy(copyText)}>Copy</button> : null}
      </div>
      <div className="result-panel-body">{children}</div>
    </div>
  );
}

export function ResultBadge({ type, children }) {
  return <span className={`result-badge ${type}`}>{children}</span>;
}

export function StatusPill({ active, children }) {
  return <span className={`status-pill ${active ? "live" : ""}`}>{children}</span>;
}

export function FeaturePageHeader({ icon, iconBg, title, desc }) {
  return (
    <div className="feature-page-header">
      <div className="fp-icon" style={{ background: iconBg }}>
        {icon}
      </div>
      <div>
        <h2>{title}</h2>
        <p>{desc}</p>
      </div>
    </div>
  );
}
