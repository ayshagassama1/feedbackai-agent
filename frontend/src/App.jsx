import { useState } from "react";
import FeedbackInput     from "./FeedbackInput";
import InsightsDashboard from "./InsightsDashboard";
import ClusterView       from "./ClusterView";
import AgentChat         from "./AgentChat";

const PROJECT_ID = import.meta.env.VITE_PROJECT_ID ?? "demo";

const TABS = ["Insights", "Clusters", "Nouveau feedback", "Chat agent"];

export default function App() {
  const [tab, setTab] = useState(0);

  return (
    <div style={st.app}>
      <header style={st.header}>
        <div style={st.logo}>⚡ FeedbackAI</div>
        <nav style={st.nav}>
          {TABS.map((t, i) => (
            <button
              key={t}
              onClick={() => setTab(i)}
              style={{ ...st.navBtn, ...(tab === i ? st.navBtnActive : {}) }}
            >
              {t}
            </button>
          ))}
        </nav>
      </header>

      <main style={st.main}>
        {tab === 0 && <InsightsDashboard projectId={PROJECT_ID} />}
        {tab === 1 && <ClusterView       projectId={PROJECT_ID} />}
        {tab === 2 && <FeedbackInput     projectId={PROJECT_ID} />}
        {tab === 3 && <AgentChat         projectId={PROJECT_ID} />}
      </main>
    </div>
  );
}

const st = {
  app:          { minHeight: "100vh", background: "var(--color-background-tertiary, #f5f5f5)", fontFamily: "system-ui" },
  header:       { background: "var(--color-background-primary, #fff)", borderBottom: "1px solid var(--color-border-tertiary, #e5e5e5)", padding: "0 32px", display: "flex", alignItems: "center", gap: 32, height: 56 },
  logo:         { fontSize: 16, fontWeight: 700, color: "var(--color-text-primary, #111)" },
  nav:          { display: "flex", gap: 4 },
  navBtn:       { padding: "6px 14px", borderRadius: 8, border: "none", background: "transparent", fontSize: 14, color: "var(--color-text-secondary, #555)", cursor: "pointer" },
  navBtnActive: { background: "var(--color-background-secondary, #f0f0f0)", color: "var(--color-text-primary, #111)", fontWeight: 500 },
  main:         { maxWidth: 960, margin: "0 auto", padding: "32px 24px" },
};
