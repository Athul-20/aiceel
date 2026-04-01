import { useState } from "react";
import { useApp } from "../context/AppContext";
import { Field, FeaturePageHeader, ResultPanel, ResultBadge } from "./Shared";
import * as Icons from "./Icons";

export default function PandoraVault() {
  const { vaultEncrypt, vaultDecrypt, busy, hasActiveKey, setActiveView, copyText, apiKeyReadiness } = useApp();
  const [mode, setMode] = useState("encrypt");
  const [plaintext, setPlaintext] = useState("my-secret-api-key-12345");
  const [passphrase, setPassphrase] = useState("StrongPassphrase123!");
  const [encryptedBlob, setEncryptedBlob] = useState("");
  const [decryptPassphrase, setDecryptPassphrase] = useState("StrongPassphrase123!");
  const [encryptResult, setEncryptResult] = useState(null);
  const [decryptResult, setDecryptResult] = useState(null);

  async function handleEncrypt(e) {
    e.preventDefault();
    const res = await vaultEncrypt(plaintext, passphrase);
    if (res) {
      setEncryptResult(res);
      if (res.encrypted_blob) {
        setEncryptedBlob(res.encrypted_blob);
        setDecryptPassphrase(passphrase);
      }
    }
  }

  async function handleDecrypt(e) {
    e.preventDefault();
    const res = await vaultDecrypt(encryptedBlob, decryptPassphrase);
    if (res) setDecryptResult(res);
  }

  return (
    <div className="feature-page">
      <FeaturePageHeader
        icon={<Icons.IconVault />}
        iconBg="var(--purple-soft)"
        title="Pandora Vault"
        desc="Enterprise-grade encryption with AES-256-GCM and PBKDF2 key derivation. Encrypt and decrypt any secret."
      />

      {!hasActiveKey && (
        <div className="key-alert">
          <span>{apiKeyReadiness.alertMessage}</span>
          <button className="btn-ghost btn-sm" onClick={() => setActiveView("keys")}>{apiKeyReadiness.alertActionLabel}</button>
        </div>
      )}

      <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.3rem" }}>
        <button className={mode === "encrypt" ? "btn-primary" : "btn-ghost"} onClick={() => setMode("encrypt")}>Encrypt</button>
        <button className={mode === "decrypt" ? "btn-primary" : "btn-ghost"} onClick={() => setMode("decrypt")}>Decrypt</button>
      </div>

      {mode === "encrypt" ? (
        <div className="feature-split">
          <section className="card">
            <div className="card-head">
              <h3>Encrypt Secret</h3>
              <p>Enter plaintext and a passphrase. AICCEL will encrypt using AES-256-GCM with PBKDF2 (600k iterations).</p>
            </div>
            <form className="form-grid" onSubmit={handleEncrypt}>
              <Field label="Plaintext secret">
                <textarea rows={4} value={plaintext} onChange={(e) => setPlaintext(e.target.value)} placeholder="Enter the secret to encrypt..." required />
              </Field>
              <Field label="Passphrase">
                <input type="password" value={passphrase} onChange={(e) => setPassphrase(e.target.value)} placeholder="Strong passphrase for key derivation" required />
              </Field>
              <button className="btn-primary btn-full" disabled={busy || !hasActiveKey} type="submit">
                {busy ? "Encrypting..." : "Encrypt"}
              </button>
            </form>
          </section>

          <section className="card">
            <div className="card-head">
              <h3>Encrypted Output</h3>
              <p>The encrypted blob you can store safely anywhere.</p>
            </div>
            {encryptResult ? (
              <>
                <div className="result-badges">
                  <ResultBadge type="safe">AES-256-GCM</ResultBadge>
                  <ResultBadge type="info">PBKDF2 600k iterations</ResultBadge>
                  <ResultBadge type="neutral">Encrypted</ResultBadge>
                </div>
                <ResultPanel title="Encrypted Blob" onCopy={copyText} copyText={encryptResult.encrypted_blob || JSON.stringify(encryptResult, null, 2)}>
                  <pre>{encryptResult.encrypted_blob || JSON.stringify(encryptResult, null, 2)}</pre>
                </ResultPanel>
                <button className="btn-ghost" onClick={() => { setMode("decrypt"); }}>
                  → Decrypt This
                </button>
              </>
            ) : (
              <div style={{ textAlign: "center", padding: "2rem 0" }}>
                <p className="muted">Submit plaintext to encrypt it.</p>
              </div>
            )}
          </section>
        </div>
      ) : (
        <div className="feature-split">
          <section className="card">
            <div className="card-head">
              <h3>Decrypt Secret</h3>
              <p>Paste an encrypted blob and the matching passphrase to recover the original.</p>
            </div>
            <form className="form-grid" onSubmit={handleDecrypt}>
              <Field label="Encrypted blob">
                <textarea rows={6} value={encryptedBlob} onChange={(e) => setEncryptedBlob(e.target.value)} placeholder="Paste encrypted blob here..." required />
              </Field>
              <Field label="Passphrase">
                <input type="password" value={decryptPassphrase} onChange={(e) => setDecryptPassphrase(e.target.value)} placeholder="Same passphrase used for encryption" required />
              </Field>
              <button className="btn-primary btn-full" disabled={busy || !hasActiveKey} type="submit">
                {busy ? "Decrypting..." : "Decrypt"}
              </button>
            </form>
          </section>

          <section className="card">
            <div className="card-head">
              <h3>Decrypted Output</h3>
              <p>The recovered plaintext secret.</p>
            </div>
            {decryptResult ? (
              <>
                <div className="result-badges">
                  <ResultBadge type="safe">Decrypted Successfully</ResultBadge>
                </div>
                <ResultPanel title="Plaintext" onCopy={copyText} copyText={decryptResult.plaintext || JSON.stringify(decryptResult, null, 2)}>
                  <pre>{decryptResult.plaintext || JSON.stringify(decryptResult, null, 2)}</pre>
                </ResultPanel>
              </>
            ) : (
              <div style={{ textAlign: "center", padding: "2rem 0" }}>
                <p className="muted">Paste an encrypted blob and passphrase to decrypt.</p>
              </div>
            )}
          </section>
        </div>
      )}

      <section className="card">
        <div className="card-head">
          <h3>Vault Security</h3>
          <p>Enterprise-grade cryptographic stack.</p>
        </div>
        <div className="feature-cards-grid">
          {[
            { Icon: Icons.IconShield, title: "AES-256-GCM", desc: "Authenticated encryption ensuring confidentiality and integrity." },
            { Icon: Icons.IconKey, title: "PBKDF2 Key Derivation", desc: "600,000 iterations with random salt for passphrase hardening." },
            { Icon: Icons.IconRefresh, title: "Random IV", desc: "Unique initialization vector per encryption operation." },
            { Icon: Icons.IconCheck, title: "Authentication Tag", desc: "GCM mode provides built-in tamper detection." },
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
