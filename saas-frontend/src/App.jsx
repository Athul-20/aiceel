import React, { useEffect, useRef, useState } from "react";
import { AppProvider, useApp } from "./context/AppContext";

// Components
import AuthScreen from "./components/AuthScreen";
import Sidebar from "./components/Sidebar";
import Dashboard from "./components/Dashboard";
import Console from "./components/Console";
import PiiMasking from "./components/PiiMasking";
import SentinelShield from "./components/SentinelShield";
import PandoraVault from "./components/PandoraVault";
import PandoraLab from "./components/PandoraLab";
import SandboxLab from "./components/SandboxLab";
import AgentBuilder from "./components/AgentBuilder";
import SwarmLab from "./components/SwarmLab";
import Playground from "./components/Playground";
import ApiDocs from "./components/ApiDocs";
import Settings from "./components/Settings";
import BiomedMasking from "./components/BiomedMasking";

const MAX_NOTIFICATIONS = 5;
const NOTIFICATION_TTL_MS = 4500;

function NotificationTray({ notice, error }) {
  const [items, setItems] = useState([]);
  const timersRef = useRef(new Map());

  function dismiss(id) {
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
    setItems((prev) => prev.filter((item) => item.id !== id));
  }

  function push(type, message) {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    setItems((prev) => {
      const next = [...prev, { id, type, message }];
      if (next.length <= MAX_NOTIFICATIONS) return next;
      const removed = next[0];
      const timer = timersRef.current.get(removed.id);
      if (timer) {
        clearTimeout(timer);
        timersRef.current.delete(removed.id);
      }
      return next.slice(next.length - MAX_NOTIFICATIONS);
    });

    const timer = setTimeout(() => dismiss(id), NOTIFICATION_TTL_MS);
    timersRef.current.set(id, timer);
  }

  useEffect(() => {
    if (notice) push("ok", notice);
  }, [notice]);

  useEffect(() => {
    if (error) push("error", error);
  }, [error]);

  useEffect(() => {
    return () => {
      for (const timer of timersRef.current.values()) {
        clearTimeout(timer);
      }
      timersRef.current.clear();
    };
  }, []);

  if (!items.length) return null;

  return (
    <div className="toast-stack" role="status" aria-live="polite">
      {items.map((item) => (
        <div className={`toast-item ${item.type}`} key={item.id}>
          <span className="toast-dot" />
          <p className="toast-message">{item.message}</p>
          <button className="toast-close" onClick={() => dismiss(item.id)} type="button" aria-label="Dismiss notification">
            x
          </button>
        </div>
      ))}
    </div>
  );
}

function AppContent() {
  const { isLoggedIn, activeView, activeViewMeta, error, notice, activeWorkspace } = useApp();

  if (!isLoggedIn) {
    return <AuthScreen />;
  }

  function renderMain() {
    switch (activeView) {
      case "dashboard": return <Dashboard />;
      case "console": return <Console />;
      case "pii_masking": return <PiiMasking />;
      case "biomed_masking": return <BiomedMasking />;
      case "jailbreak": return <SentinelShield />;
      case "vault": return <PandoraVault />;
      case "pandora": return <PandoraLab />;
      case "sandbox": return <SandboxLab />;
      case "agents": return <AgentBuilder />;
      case "swarm": return <SwarmLab />;
      case "playground": return <Playground />;
      case "api_docs": return <ApiDocs />;
      case "keys":
      case "providers":
      case "usage":
      case "webhooks":
      case "workspaces":
        return <Settings />;
      default: return <Dashboard />;
    }
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="main-area">
        <header className="top-bar">
          <div className="top-bar-left">
            <h2>{activeViewMeta?.title}</h2>
            <p>{activeViewMeta?.desc}</p>
          </div>
          <div className="top-bar-right">
            <span className="status-pill">{activeWorkspace ? activeWorkspace.name : "Personal Sandbox"}</span>
            <span className="status-pill live">Engine Ready</span>
          </div>
        </header>

        <div className="content-area">
          {renderMain()}
        </div>
      </main>
      <NotificationTray notice={notice} error={error} />
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <AppContent />
    </AppProvider>
  );
}
