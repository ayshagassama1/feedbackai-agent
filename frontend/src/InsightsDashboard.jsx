import { useState, useEffect } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "";

const CATEGORY_COLORS = {
  bug:             { bg: "#fef2f2", text: "#b91c1c", border: "#fca5a5" },
  feature_request: { bg: "#eff6ff", text: "#1d4ed8", border: "#93c5fd" },
  ux:              { bg: "#faf5ff", text: "#7e22ce", border: "#d8b4fe" },
  pricing:         { bg: "#fff7ed", text: "#c2410c", border: "#fdba74" },
  other:           { bg: "#f9fafb", text: "#374151", border: "#d1d5db" },
};

const PRIORITY_LABELS = {
  high:   { label: "Haute",  color: "#b91c1c" },
  medium: { label: "Moyenne", color: "#c2410c" },
  low:    { label: "Basse",  color: "#374151" },
};

export default function InsightsDashboard({ projectId }) {
  const [insights, setInsights] = useState(null);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchInsights = async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const res = await fetch(`${API_URL}/api/insights?project_id=${projectId}`);
      if (!res.ok) throw new Error(`Erreur ${res.status}`);
      const data = await res.json();
      setInsights(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { fetchInsights(); }, [projectId]);

  if (loading) return <div style={s.placeholder}>Chargement des insights…</div>;
  if (error)   return <div style={s.errorBox}>⚠️ {error}</div>;
  if (!insights) return null;

  const { stats, top_issues, recommendations, generated_at } = insights;

  return (
    <div style={s.wrapper}>

      {/* ── Stats bar ── */}
      <div style={s.statsRow}>
        {[
          { label: "Feedbacks",      value: stats?.total ?? 0 },
          { label: "Cette semaine",  value: stats?.this_week ?? 0 },
          { label: "Sentiment moy.", value: stats?.avg_sentiment != null ? (stats.avg_sentiment > 0 ? `+${stats.avg_sentiment.toFixed(2)}` : stats.avg_sentiment.toFixed(2)) : "—" },
          { label: "Clusters",       value: stats?.clusters ?? 0 },
        ].map((s) => (
          <div key={s.label} style={styles.statCard}>
            <span style={styles.statValue}>{s.value}</span>
            <span style={styles.statLabel}>{s.label}</span>
          </div>
        ))}
      </div>

      {/* ── Top issues ── */}
      <section style={styles.section}>
        <div style={styles.sectionHeader}>
          <span style={styles.sectionTitle}>🔥 Problèmes prioritaires</span>
          <button
            onClick={() => fetchInsights(true)}
            style={styles.refreshBtn}
            disabled={refreshing}
          >
            {refreshing ? "…" : "↻ Rafraîchir"}
          </button>
        </div>

        {top_issues?.length ? (
          <div style={styles.issueList}>
            {top_issues.map((issue, i) => {
              const cat   = CATEGORY_COLORS[issue.category] ?? CATEGORY_COLORS.other;
              const prio  = PRIORITY_LABELS[issue.priority]  ?? PRIORITY_LABELS.low;
              return (
                <div key={i} style={styles.issueCard}>
                  <div style={styles.issueTop}>
                    <span style={{ ...styles.badge, background: cat.bg, color: cat.text, border: `1px solid ${cat.border}` }}>
                      {issue.category?.replace("_", " ")}
                    </span>
                    <span style={{ ...styles.priority, color: prio.color }}>
                      ● {prio.label}
                    </span>
                    <span style={styles.issueCount}>{issue.count} feedbacks</span>
                  </div>
                  <p style={styles.issueLabel}>{issue.label}</p>
                  {issue.sample && (
                    <p style={styles.issueSample}>« {issue.sample} »</p>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <p style={styles.empty}>Pas encore de données suffisantes.</p>
        )}
      </section>

      {/* ── Recommendations ── */}
      <section style={styles.section}>
        <div style={styles.sectionHeader}>
          <span style={styles.sectionTitle}>✅ Recommandations cette semaine</span>
        </div>

        {recommendations?.length ? (
          <ol style={styles.recList}>
            {recommendations.map((rec, i) => (
              <li key={i} style={styles.recItem}>
                <span style={styles.recNumber}>{i + 1}</span>
                <div>
                  <p style={styles.recTitle}>{rec.action}</p>
                  <p style={styles.recReason}>{rec.reason}</p>
                  {rec.impact && (
                    <span style={styles.impactBadge}>Impact estimé : {rec.impact}</span>
                  )}
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p style={styles.empty}>L'agent génère les recommandations en cours…</p>
        )}
      </section>

      <p style={styles.generatedAt}>
        Généré le {new Date(generated_at).toLocaleString("fr-FR")}
      </p>
    </div>
  );
}

const s = {
  placeholder: { padding: 24, color: "var(--color-text-tertiary)", fontSize: 14 },
  errorBox: { padding: 14, borderRadius: 8, background: "#fef2f2", color: "#b91c1c", fontSize: 13 },
  statsRow: { display: "flex", gap: 12 },
};

const styles = {
  wrapper:       { display: "flex", flexDirection: "column", gap: 24, fontFamily: "var(--font-sans, system-ui)" },
  statsRow:      { display: "flex", gap: 12, flexWrap: "wrap" },
  statCard:      { flex: 1, minWidth: 100, padding: "16px 20px", borderRadius: 12, border: "1px solid var(--color-border-tertiary)", background: "var(--color-background-primary)", display: "flex", flexDirection: "column", gap: 4 },
  statValue:     { fontSize: 24, fontWeight: 700, color: "var(--color-text-primary)" },
  statLabel:     { fontSize: 12, color: "var(--color-text-tertiary)" },
  section:       { display: "flex", flexDirection: "column", gap: 12 },
  sectionHeader: { display: "flex", justifyContent: "space-between", alignItems: "center" },
  sectionTitle:  { fontSize: 15, fontWeight: 600, color: "var(--color-text-primary)" },
  refreshBtn:    { fontSize: 12, color: "var(--color-text-secondary)", background: "none", border: "none", cursor: "pointer", padding: "4px 8px" },
  issueList:     { display: "flex", flexDirection: "column", gap: 10 },
  issueCard:     { padding: "14px 16px", borderRadius: 10, border: "1px solid var(--color-border-tertiary)", background: "var(--color-background-primary)", display: "flex", flexDirection: "column", gap: 8 },
  issueTop:      { display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" },
  badge:         { fontSize: 11, fontWeight: 500, padding: "2px 8px", borderRadius: 20 },
  priority:      { fontSize: 12, fontWeight: 500 },
  issueCount:    { fontSize: 12, color: "var(--color-text-tertiary)", marginLeft: "auto" },
  issueLabel:    { fontSize: 14, fontWeight: 500, color: "var(--color-text-primary)", margin: 0 },
  issueSample:   { fontSize: 13, color: "var(--color-text-secondary)", fontStyle: "italic", margin: 0 },
  recList:       { display: "flex", flexDirection: "column", gap: 12, paddingLeft: 0, margin: 0, listStyle: "none" },
  recItem:       { display: "flex", gap: 14, alignItems: "flex-start" },
  recNumber:     { width: 28, height: 28, borderRadius: "50%", background: "var(--color-background-secondary)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 700, color: "var(--color-text-secondary)", flexShrink: 0 },
  recTitle:      { fontSize: 14, fontWeight: 600, color: "var(--color-text-primary)", margin: "0 0 4px" },
  recReason:     { fontSize: 13, color: "var(--color-text-secondary)", margin: "0 0 6px" },
  impactBadge:   { fontSize: 11, padding: "2px 8px", borderRadius: 20, background: "#f0fdf4", color: "#15803d", border: "1px solid #86efac" },
  empty:         { fontSize: 13, color: "var(--color-text-tertiary)", fontStyle: "italic" },
  generatedAt:   { fontSize: 11, color: "var(--color-text-tertiary)", textAlign: "right" },
};
