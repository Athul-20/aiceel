import { useApp } from "../context/AppContext";
import { Field } from "./Shared";
import * as Icons from "./Icons";

export default function AuthScreen() {
  const { mode, setMode, email, setEmail, password, setPassword, busy, authError, authNotice, authSubmit, theme, toggleTheme } = useApp();

  return (
    <div className="auth-shell">
      <div className="auth-layout">
        <section className="auth-showcase">
          <p className="auth-kicker">AICCEL CLOUD</p>
          <h1>Build secure AI agents from one powerful platform.</h1>
          <p>
            PII masking, jailbreak detection, vault encryption, multi-agent swarm orchestration, sandboxed execution —
            all accessible as simple APIs.
          </p>
          <div className="auth-feature-grid">
            <article>
              <strong>PII Masking</strong>
              <span>Detect & mask emails, phones, names, cards with reversible tokenization.</span>
            </article>
            <article>
              <strong>Sentinel Shield</strong>
              <span>Block prompt injection, adversarial markers, and system prompt extraction.</span>
            </article>
            <article>
              <strong>Pandora Vault</strong>
              <span>AES-256-GCM encryption with PBKDF2 key derivation for secrets.</span>
            </article>
            <article>
              <strong>Agent Builder</strong>
              <span>Create AI agents with custom roles, tools, and multi-agent swarm orchestration.</span>
            </article>
          </div>
        </section>

        <section className="auth-card">
          <div className="auth-card-head">
            <div className="auth-card-head-row">
              <div>
                <h2>{mode === "login" ? "Welcome back" : "Create your account"}</h2>
                <p>{mode === "login" ? "Sign in to access your AICCEL workspace." : "Start building with AICCEL features."}</p>
              </div>
              <button
                className="btn-ghost btn-sm auth-theme-toggle"
                onClick={toggleTheme}
                type="button"
                aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
                aria-pressed={theme === "dark"}
              >
                <span className="theme-toggle-icon" aria-hidden="true">
                  {theme === "dark" ? <Icons.IconSun /> : <Icons.IconMoon />}
                </span>
                <span>{theme === "dark" ? "Light" : "Dark"}</span>
              </button>
            </div>
          </div>

          {authError ? <div className="banner error">{authError}</div> : null}
          {authNotice ? <div className="banner ok">{authNotice}</div> : null}

          <div className="auth-switch">
            <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")} type="button">Sign in</button>
            <button className={mode === "register" ? "active" : ""} onClick={() => setMode("register")} type="button">Register</button>
          </div>

          <form className="form-grid auth-form" onSubmit={authSubmit}>
            <Field label="Email">
              <input type="email" placeholder="you@company.com" value={email} onChange={(e) => setEmail(e.target.value)} required />
            </Field>
            <Field label="Password">
              <input type="password" placeholder="Minimum 8 characters" value={password} minLength={8} onChange={(e) => setPassword(e.target.value)} required />
            </Field>
            <button className="btn-primary auth-submit" disabled={busy} type="submit">
              {busy ? "Please wait..." : mode === "login" ? "Sign in" : "Create account"}
            </button>
          </form>

          <p className="auth-footnote">
            Access PII masking, jailbreak detection, vault encryption, agent builder, and all AICCEL features from one dashboard.
          </p>
        </section>
      </div>
    </div>
  );
}
