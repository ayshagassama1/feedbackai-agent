import { useState, useEffect } from "react";
import { theme, priorityStyle } from "./theme";
import { translations } from "./i18n";

const API_URL = import.meta.env.VITE_API_URL ?? "";

export default function InsightsDashboard({ projectId, lang }) {
  const t = translations[lang];
  const [insights, setInsights] = useState(null);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchInsights = async (silent = false) => {
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const res = await fetch(`${API_URL}/api/insights?project_id=${projectId}`);
      if (!res.ok) throw new Error(`${t.insights.error} ${res.status}`);
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

  if (loading) return <div style={s.placeholder}>{t.insights.loading}</div>;
  if (error)   return <div style={s.errorBox}>{error}</div>;
  if (!insights) return null;

  const { stats, top_issues, recommendations, generated_at } = insights;

  return (
    <div style={styles.wrapper}>

      {/* Stats */}
      <div style={styles.statsRow}>
        {[
          { label: t.insights.feedbacks,    value: stats?.total ?? 0 },
          { label: t.insights.thisWeek,     value: stats?.this_week ?? 0 },
          { label: t.insights.avgSentiment, value: stats?.avg_sentiment != null ? (stats.avg_sentiment > 0 ? `+${stats.avg_sentiment.toFixed(2)}` : stats.avg_sentiment.toFixed(2)) : "—" },
          { label: t.insights.clusters,     value: stats?.clusters ?? 0 },
        ].map((s) => (
          <div key={s.label} className="card-elevate" style={styles.statCard}>
            <span style={styles.statValue}>{s.value}</span>
            <span style={styles.statLabel}>{s.label}</span>
          </div>
        ))}
      </div>

      {/* Top issues */}
      <section style={styles.section}>
        <div style={styles.sectionHeader}>
          <span style={styles.sectionTitle}>{t.insights.priorityIssues}</span>
          <button
            onClick={() => fetchInsights(true)}
            style={styles.refreshBtn}
            disabled={refreshing}
          >
            {refreshing ? t.insights.refreshing : t.insights.refresh}
          </button>
        </div>

        {top_issues?.length ? (
          <div style={styles.issueList}>
            {top_issues.map((issue, i) => {
              const prio = priorityStyle(issue.priority, lang);
              return (
                <div key={i} className="card-elevate" style={styles.issueCard}>
                  <div style={styles.issueTop}>
                    <span style={styles.badge}>
                      {issue.category?.replace("_", " ")}
                    </span>
                    <span style={{ ...styles.priority, color: prio.color }}>
                      {prio.label}
                    </span>
                    <span style={styles.issueCount}>{issue.count} {t.clusters.feedbackCount}</span>
                  </div>
                  <p style={styles.issueLabel}>{issue.label}</p>
                  {issue.sample && (
                    <p style={styles.issueSample}>"{issue.sample}"</p>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <p style={styles.empty}>{t.insights.notEnoughData}</p>
        )}
      </section>

      {/* Recommendations */}
      <section style={styles.section}>
        <div style={styles.sectionHeader}>
          <span style={styles.sectionTitle}>{t.insights.recommendations}</span>
        </div>

        {recommendations?.length ? (
          <ol style={styles.recList}>
            {recommendations.map((rec, i) => (
              <li key={i} className="card-elevate" style={styles.recItem}>
                <span style={styles.recNumber}>{i + 1}</span>
                <div>
                  <p style={styles.recTitle}>{rec.action}</p>
                  <p style={styles.recReason}>{rec.reason}</p>
                  {rec.impact && (
                    <span style={styles.impactBadge}>{t.insights.estimatedImpact}: {rec.impact}</span>
                  )}
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p style={styles.empty}>{t.insights.generatingRecommendations}</p>
        )}
      </section>

      <p style={styles.generatedAt}>
        {t.insights.generatedOn} {new Date(generated_at).toLocaleString(lang === "fr" ? "fr-FR" : "en-US")}
      </p>
    </div>
  );
}

const s = {
  placeholder: { padding: 24, color: theme.color.textTertiary, fontSize: 14, fontFamily: theme.font.sans },
  errorBox: { padding: 14, borderRadius: theme.radius.md, background: theme.color.dangerBg, color: theme.color.danger, fontSize: 13, fontFamily: theme.font.sans },
};

const styles = {
  wrapper:       { display: "flex", flexDirection: "column", gap: 24, fontFamily: theme.font.sans },
  statsRow:      { display: "flex", gap: 12, flexWrap: "wrap" },
  statCard:      { flex: 1, minWidth: 100, padding: "16px 20px", borderRadius: theme.radius.lg, border: `1px solid ${theme.color.borderTertiary}`, background: theme.color.bgPrimary, boxShadow: theme.shadow.sm, display: "flex", flexDirection: "column", gap: 4 },
  statValue:     { fontSize: 24, fontWeight: 700, color: theme.color.textPrimary, letterSpacing: "-0.01em" },
  statLabel:     { fontSize: 12, color: theme.color.textTertiary },
  section:       { display: "flex", flexDirection: "column", gap: 12 },
  sectionHeader: { display: "flex", justifyContent: "space-between", alignItems: "center" },
  sectionTitle:  { fontSize: 15, fontWeight: 600, color: theme.color.textPrimary },
  refreshBtn:    { fontSize: 12, fontWeight: 500, color: theme.color.brandHover, background: "none", border: "none", cursor: "pointer", padding: "4px 8px", fontFamily: "inherit" },
  issueList:     { display: "flex", flexDirection: "column", gap: 10 },
  issueCard:     { padding: "14px 16px", borderRadius: theme.radius.lg, border: `1px solid ${theme.color.borderTertiary}`, background: theme.color.bgPrimary, boxShadow: theme.shadow.sm, display: "flex", flexDirection: "column", gap: 8 },
  issueTop:      { display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" },
  badge:         { fontSize: 11, fontWeight: 500, padding: "2px 8px", borderRadius: theme.radius.pill, background: theme.color.bgTertiary, color: theme.color.textSecondary, border: `1px solid ${theme.color.borderSecondary}` },
  priority:      { fontSize: 12, fontWeight: 600 },
  issueCount:    { fontSize: 12, color: theme.color.textTertiary, marginLeft: "auto" },
  issueLabel:    { fontSize: 14, fontWeight: 500, color: theme.color.textPrimary, margin: 0 },
  issueSample:   { fontSize: 13, color: theme.color.textSecondary, fontStyle: "italic", margin: 0 },
  recList:       { display: "flex", flexDirection: "column", gap: 12, paddingLeft: 0, margin: 0, listStyle: "none" },
  recItem:       { display: "flex", gap: 14, alignItems: "flex-start", padding: "14px 16px", borderRadius: theme.radius.lg, border: `1px solid ${theme.color.borderTertiary}`, background: theme.color.bgPrimary, boxShadow: theme.shadow.sm },
  recNumber:     { width: 28, height: 28, borderRadius: "50%", background: theme.color.bgTertiary, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 700, color: theme.color.textSecondary, flexShrink: 0 },
  recTitle:      { fontSize: 14, fontWeight: 600, color: theme.color.textPrimary, margin: "0 0 4px" },
  recReason:     { fontSize: 13, color: theme.color.textSecondary, margin: "0 0 6px" },
  impactBadge:   { fontSize: 11, padding: "2px 8px", borderRadius: theme.radius.pill, background: theme.color.brandLight, color: theme.color.brandHover, border: `1px solid ${theme.color.brandBorder}` },
  empty:         { fontSize: 13, color: theme.color.textTertiary, fontStyle: "italic" },
  generatedAt:   { fontSize: 11, color: theme.color.textTertiary, textAlign: "right" },
};
