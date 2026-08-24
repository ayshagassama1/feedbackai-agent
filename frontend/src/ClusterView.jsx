import { useState, useEffect } from "react";
import { theme, sentimentColor } from "./theme";
import { translations } from "./i18n";

const API_URL = import.meta.env.VITE_API_URL ?? "";

export default function ClusterView({ projectId, lang }) {
  const t = translations[lang];
  const [clusters, setClusters] = useState([]);
  const [selected, setSelected] = useState(null);
  const [feedbacks, setFeedbacks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_URL}/api/clusters?project_id=${projectId}`)
      .then((r) => r.json())
      .then((data) => { setClusters(data.clusters ?? []); setLoading(false); })
      .catch(() => setLoading(false));
  }, [projectId]);

  const selectCluster = async (cluster) => {
    setSelected(cluster);
    const res = await fetch(`${API_URL}/api/feedbacks?cluster_id=${cluster._id}&project_id=${projectId}`);
    const data = await res.json();
    setFeedbacks(data.feedbacks ?? []);
  };

  if (loading) return <div style={st.placeholder}>{t.clusters.loading}</div>;
  if (!clusters.length) return <div style={st.placeholder}>{t.clusters.empty}</div>;

  return (
    <div style={st.wrapper}>
      <div style={st.grid}>
        {clusters.map((c) => (
          <div
            key={c._id}
            className="card-elevate"
            onClick={() => selectCluster(c)}
            style={{
              ...st.clusterCard,
              ...(selected?._id === c._id ? st.clusterCardActive : {}),
            }}
          >
            <div style={st.clusterTop}>
              <span style={st.clusterLabel}>{c.label}</span>
              <span style={{ ...st.sentimentDot, color: sentimentColor(c.avg_sentiment) }}>●</span>
            </div>
            <div style={st.clusterMeta}>
              <span style={st.clusterCount}>{c.feedback_count} {t.clusters.feedbackCount}</span>
              <span style={{ ...st.sentiment, color: sentimentColor(c.avg_sentiment) }}>
                {c.avg_sentiment > 0 ? "+" : ""}{c.avg_sentiment?.toFixed(2)}
              </span>
            </div>
            <div style={st.progressBar}>
              <div
                style={{
                  ...st.progressFill,
                  width: `${Math.min(100, (c.feedback_count / (clusters[0]?.feedback_count || 1)) * 100)}%`,
                  background: sentimentColor(c.avg_sentiment),
                }}
              />
            </div>
            {c.issue_url && (
              <a
                href={c.issue_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                style={st.ticketBadge}
              >
                {t.clusters.ticketCreated} · #{c.issue_number}
              </a>
            )}
          </div>
        ))}
      </div>

      {selected && (
        <div style={st.detail}>
          <div style={st.detailHeader}>
            <span style={st.detailTitle}>{selected.label}</span>
            <button onClick={() => { setSelected(null); setFeedbacks([]); }} style={st.closeBtn}>
              {t.clusters.close}
            </button>
          </div>
          <div style={st.feedbackList}>
            {feedbacks.length === 0 && <p style={st.empty}>{t.clusters.loadingFeedbacks}</p>}
            {feedbacks.map((f) => (
              <div key={f._id} style={st.feedbackItem}>
                <p style={st.feedbackText}>{f.text}</p>
                <div style={st.feedbackMeta}>
                  <span style={st.source}>{f.source}</span>
                  <span style={{ ...st.sentimentSmall, color: sentimentColor(f.sentiment) }}>
                    {f.sentiment > 0 ? "+" : ""}{f.sentiment?.toFixed(2)}
                  </span>
                  <span style={st.date}>{new Date(f.created_at).toLocaleDateString(lang === "fr" ? "fr-FR" : "en-US")}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

const st = {
  wrapper:          { display: "flex", flexDirection: "column", gap: 20, fontFamily: theme.font.sans },
  placeholder:      { padding: 24, color: theme.color.textTertiary, fontSize: 14 },
  grid:             { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 },
  clusterCard:      { padding: "14px 16px", borderRadius: theme.radius.lg, border: `1px solid ${theme.color.borderTertiary}`, background: theme.color.bgPrimary, boxShadow: theme.shadow.sm, cursor: "pointer", display: "flex", flexDirection: "column", gap: 8, transition: "border-color .15s, background .15s" },
  clusterCardActive:{ border: `1px solid ${theme.color.brand}`, background: theme.color.brandLight },
  clusterTop:       { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 },
  clusterLabel:     { fontSize: 13, fontWeight: 600, color: theme.color.textPrimary, lineHeight: 1.4 },
  sentimentDot:     { fontSize: 10, flexShrink: 0 },
  clusterMeta:      { display: "flex", justifyContent: "space-between", alignItems: "center" },
  clusterCount:     { fontSize: 12, color: theme.color.textTertiary },
  sentiment:        { fontSize: 12, fontWeight: 600 },
  progressBar:      { height: 3, borderRadius: 2, background: theme.color.borderTertiary, overflow: "hidden" },
  progressFill:     { height: "100%", borderRadius: 2, transition: "width .3s" },
  ticketBadge:      { fontSize: 11, fontWeight: 500, color: theme.color.brandHover, background: theme.color.brandLight, border: `1px solid ${theme.color.brandBorder}`, borderRadius: theme.radius.pill, padding: "3px 10px", textDecoration: "none", alignSelf: "flex-start" },
  detail:           { border: `1px solid ${theme.color.borderTertiary}`, borderRadius: theme.radius.lg, overflow: "hidden" },
  detailHeader:     { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 16px", background: theme.color.bgSecondary, borderBottom: `1px solid ${theme.color.borderTertiary}` },
  detailTitle:      { fontSize: 14, fontWeight: 600, color: theme.color.textPrimary },
  closeBtn:         { background: "none", border: "none", cursor: "pointer", color: theme.color.textSecondary, fontSize: 13, fontWeight: 500, fontFamily: "inherit" },
  feedbackList:     { display: "flex", flexDirection: "column", gap: 0, maxHeight: 360, overflowY: "auto" },
  feedbackItem:     { padding: "12px 16px", borderBottom: `1px solid ${theme.color.borderTertiary}`, display: "flex", flexDirection: "column", gap: 6 },
  feedbackText:     { fontSize: 13, color: theme.color.textPrimary, margin: 0, lineHeight: 1.5 },
  feedbackMeta:     { display: "flex", gap: 10, alignItems: "center" },
  source:           { fontSize: 11, color: theme.color.textTertiary, background: theme.color.bgTertiary, padding: "1px 6px", borderRadius: theme.radius.sm },
  sentimentSmall:   { fontSize: 11, fontWeight: 600 },
  date:             { fontSize: 11, color: theme.color.textTertiary, marginLeft: "auto" },
  empty:            { padding: 16, fontSize: 13, color: theme.color.textTertiary, fontStyle: "italic", margin: 0 },
};
