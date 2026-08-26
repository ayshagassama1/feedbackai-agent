import { useState, useEffect } from "react";
import FeedbackInput     from "./FeedbackInput";
import InsightsDashboard from "./InsightsDashboard";
import ClusterView       from "./ClusterView";
import AgentChat          from "./AgentChat";
import { theme } from "./theme";
import { translations } from "./i18n";

const API_URL = import.meta.env.VITE_API_URL ?? "";
const PROJECT_ID = import.meta.env.VITE_PROJECT_ID ?? "demo";

export default function App() {
  const [tab, setTab] = useState(0);
  const [lang, setLang] = useState(() => localStorage.getItem("feedbackai_lang") ?? "fr");
  const t = translations[lang];

  // Au chargement, la langue vient du réglage d'équipe côté serveur (team_language) plutôt que
  // du seul localStorage : les deux doivent rester alignés, voir setLanguage ci-dessous.
  useEffect(() => {
    fetch(`${API_URL}/api/projects/${PROJECT_ID}/settings`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.team_language) {
          setLang(data.team_language);
          localStorage.setItem("feedbackai_lang", data.team_language);
        }
      })
      .catch(() => {}); // pas bloquant : reste sur la valeur locale si l'appel échoue
  }, []);

  const setLanguage = (next) => {
    setLang(next);
    localStorage.setItem("feedbackai_lang", next);

    // Le bouton pilote aussi team_language : les FUTURS contenus générés (labels de cluster,
    // insights, tickets) suivront cette langue. Ne retraduit jamais ce qui existe déjà.
    fetch(`${API_URL}/api/projects/${PROJECT_ID}/settings`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ team_language: next }),
    }).catch((err) => console.error("Échec de la mise à jour de team_language :", err));
  };

  const tabs = [t.tabs.insights, t.tabs.clusters, t.tabs.newFeedback, t.tabs.chat];

  return (
    <div style={st.app}>
      <header style={st.header}>
        <div style={st.logo}>{t.appName}</div>
        <nav style={st.nav}>
          {tabs.map((label, i) => (
            <button
              key={label}
              onClick={() => setTab(i)}
              style={{ ...st.navBtn, ...(tab === i ? st.navBtnActive : {}) }}
            >
              {label}
            </button>
          ))}
        </nav>
        <button
          onClick={() => setLanguage(lang === "fr" ? "en" : "fr")}
          style={st.langBtn}
        >
          {t.langToggle}
        </button>
      </header>

      <main style={st.main}>
        {tab === 0 && <InsightsDashboard projectId={PROJECT_ID} lang={lang} />}
        {tab === 1 && <ClusterView       projectId={PROJECT_ID} lang={lang} />}
        {tab === 2 && <FeedbackInput     projectId={PROJECT_ID} lang={lang} />}
        {tab === 3 && <AgentChat         projectId={PROJECT_ID} lang={lang} />}
      </main>
    </div>
  );
}

const st = {
  app: {
    minHeight: "100vh",
    background: theme.color.bgSecondary,
    fontFamily: theme.font.sans,
  },
  header: {
    background: theme.color.bgPrimary,
    borderBottom: `1px solid ${theme.color.borderTertiary}`,
    padding: "0 32px",
    display: "flex",
    alignItems: "center",
    gap: 32,
    height: 56,
  },
  logo: {
    fontSize: 16,
    fontWeight: 700,
    color: theme.color.textPrimary,
    letterSpacing: "-0.01em",
  },
  nav: { display: "flex", gap: 4, flex: 1 },
  navBtn: {
    padding: "6px 14px",
    borderRadius: theme.radius.md,
    border: "none",
    background: "transparent",
    fontSize: 14,
    fontWeight: 500,
    color: theme.color.textSecondary,
    cursor: "pointer",
    fontFamily: "inherit",
    transition: "background .15s, color .15s",
  },
  navBtnActive: {
    background: theme.color.brandLight,
    color: theme.color.brandHover,
  },
  langBtn: {
    padding: "6px 12px",
    borderRadius: theme.radius.md,
    border: `1px solid ${theme.color.borderSecondary}`,
    background: "transparent",
    fontSize: 13,
    fontWeight: 500,
    color: theme.color.textSecondary,
    cursor: "pointer",
    fontFamily: "inherit",
  },
  main: { maxWidth: 960, margin: "0 auto", padding: "32px 24px" },
};
