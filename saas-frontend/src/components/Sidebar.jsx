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
  api_docs: Icons.IconDocs,
  securitycenter: Icons.IconSecurityCenter,
  hardware: Icons.IconHardware,
  canary: Icons.IconCanary,
};

export default function Sidebar() {
  const { activeView, setActiveView, user, logout } = useApp();

  return (
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
        <button className="btn-ghost btn-sm" type="button" onClick={logout}>
          <Icons.IconLogout />
          Logout
        </button>
      </footer>
    </aside>
  );
}
