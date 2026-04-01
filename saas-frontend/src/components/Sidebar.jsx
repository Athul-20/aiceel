import { useEffect, useState } from "react";
import { useApp } from "../context/AppContext";
import { NAV_GROUPS } from "../constants";
import * as Icons from "./Icons";

const ICON_MAP = {
  dashboard: Icons.IconDashboard,
  console: Icons.IconConsole,
  pii: Icons.IconPII,
  biomed: Icons.IconBioMed,
  shield: Icons.IconShield,
  datalab: Icons.IconDataLab,
  vault: Icons.IconVault,
  sandbox: Icons.IconSandbox,
  agent: Icons.IconAgent,
  swarm: Icons.IconSwarm,
  playground: Icons.IconPlayground,
  key: Icons.IconKey,
  provider: Icons.IconProvider,
  usage: Icons.IconUsage,
  webhook: Icons.IconWebhook,
  workspace: Icons.IconWorkspace,
  docs: Icons.IconDocs,
};

export default function Sidebar() {
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const { activeView, setActiveView, user, logout } = useApp();

  useEffect(() => {
    if (!showLogoutConfirm) return undefined;

    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setShowLogoutConfirm(false);
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [showLogoutConfirm]);

  function requestLogout() {
    setShowLogoutConfirm(true);
  }

  function cancelLogout() {
    setShowLogoutConfirm(false);
  }

  function confirmLogout() {
    setShowLogoutConfirm(false);
    logout();
  }

  return (
    <>
      <aside className="sidebar">
        <div className="sidebar-brand">
          <h1>AICCEL</h1>
          <p>AI-Accelerated Agentic Library</p>
        </div>

        <nav className="stagger-children">
          {NAV_GROUPS.map((group) => (
            <div className="nav-section" key={group.title}>
              <p className="nav-section-title">{group.title}</p>
              {group.items.map(([id, iconKey, label]) => {
                const IconComp = ICON_MAP[iconKey];
                return (
                  <button
                    className={`nav-item ${activeView === id ? "active" : ""}`}
                    key={id}
                    onClick={() => setActiveView(id)}
                    type="button"
                  >
                    <span className="nav-icon">
                      {IconComp ? <IconComp /> : null}
                    </span>
                    {label}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        <footer className="sidebar-footer">
          <div className="user-info">
            <span>{user?.email}</span>
          </div>
          <button className="btn-ghost btn-sm sidebar-logout-btn" type="button" onClick={requestLogout}>
            <Icons.IconLogout />
            Logout
          </button>
        </footer>
      </aside>

      {showLogoutConfirm ? (
        <div className="popup-overlay" onClick={cancelLogout} role="presentation">
          <div
            className="popup-box confirm-dialog"
            role="dialog"
            aria-modal="true"
            aria-labelledby="logout-confirm-title"
            aria-describedby="logout-confirm-description"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="confirm-dialog-icon" aria-hidden="true">
              <Icons.IconLogout />
            </div>
            <h2 id="logout-confirm-title">Log out now?</h2>
            <p id="logout-confirm-description">
              You will be signed out of this dashboard and returned to the login screen.
            </p>
            <div className="confirm-actions">
              <button className="btn-ghost btn-full" type="button" onClick={cancelLogout}>
                Stay signed in
              </button>
              <button className="btn-danger btn-full" type="button" onClick={confirmLogout}>
                Log out
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
