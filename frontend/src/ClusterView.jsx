import { useState, useEffect } from "react";

export default function ClusterView({ projectId }) {
  const [clusters, setClusters] = useState([]);
  const [selected, setSelected] = useState(null);
  const [feedbacks, setFeedbacks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/clusters?project_id=${projectId}`)
      .then((r) => r.json())
      .then((data) => { setClusters(data.clusters ?? []); setLoading(false); })
      .catch(() => setLoading(false));
  }, [projectId]);

  const selectCluster = async (cluster) => {
    setSelected(cluster);
    const res = await fetch(`/api/feedbacks?cluster_id=${cluster._id}&project_id=${projectId}`);
    const data = await res.json();
    setFeedbacks(data.feedbacks ?? []);
  };

  const sentimentColor = (s) => {
    if (s > 0.2)  return "#15803d";
    if (s < -0.2) return "#b91c1c";
    return "#92400e";
  };

  if (loading) return <div style={st.placeholder}>Chargement des clusters…</div>;
  if (!clusters.length) return <div style={st.placeholder}>Aucun cluster détecté — envoyez plus de feedbacks.</div>;

  return (
    <div style={st.wrapper}>
      <div style={st.grid}>
        {clusters.map((c) => (
          <div
            key={c._id}
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
              <span style={st.clusterCount}>{c.feedback_count} feedbacks</span>
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
          </div>
        ))}
      </div>

      {selected && (
        <div style={st.detail}>
          <div style={st.detailHeader}>
            <span style={st.detailTitle}>{selected.label}</span>
            <button onClick={() => { setSelected(null); setFeedbacks([]); }} style={st.closeBtn}>✕</button>
          </div>
          <div style={st.feedbackList}>
            {feedbacks.length === 0 && <p style={st.empty}>Chargement…</p>}
            {feedbacks.map((f) => (
              <div key={f._id} style={st.feedbackItem}>
                <p style={st.feedbackText}>{f.text}</p>
                <div style={st.feedbackMeta}>
                  <span style={st.source}>{f.source}</span>
                  <span style={{ ...st.sentimentSmall, color: sentimentColor(f.sentiment) }}>
                    {f.sentiment > 0 ? "+" : ""}{f.sentiment?.toFixed(2)}
                  </span>
                  <span style={st.date}>{new Date(f.created_at).toLocaleDateString("fr-FR")}</span>
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
  wrapper:          { display: "flex", flexDirection: "column", gap: 20, fontFamily: "var(--font-sans, system-ui)" },
  placeholder:      { padding: 24, color: "var(--color-text-tertiary)", fontSize: 14 },
  grid:             { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 },
  clusterCard:      { padding: "14px 16px", borderRadius: 12, border: "1px solid var(--color-border-tertiary)", background: "var(--color-background-primary)", cursor: "pointer", display: "flex", flexDirection: "column", gap: 8, transition: "all .15s" },
  clusterCardActive:{ border: "1px solid var(--color-border-primary)", background: "var(--color-background-secondary)" },
  clusterTop:       { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 },
  clusterLabel:     { fontSize: 13, fontWeight: 600, color: "var(--color-text-primary)", lineHeight: 1.4 },
  sentimentDot:     { fontSize: 10, flexShrink: 0 },
  clusterMeta:      { display: "flex", justifyContent: "space-between", alignItems: "center" },
  clusterCount:     { fontSize: 12, color: "var(--color-text-tertiary)" },
  sentiment:        { fontSize: 12, fontWeight: 500 },
  progressBar:      { height: 3, borderRadius: 2, background: "var(--color-border-tertiary)", overflow: "hidden" },
  progressFill:     { height: "100%", borderRadius: 2, transition: "width .3s" },
  detail:           { border: "1px solid var(--color-border-tertiary)", borderRadius: 12, overflow: "hidden" },
  detailHeader:     { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "12px 16px", background: "var(--color-background-secondary)", borderBottom: "1px solid var(--color-border-tertiary)" },
  detailTitle:      { fontSize: 14, fontWeight: 600, color: "var(--color-text-primary)" },
  closeBtn:         { background: "none", border: "none", cursor: "pointer", color: "var(--color-text-tertiary)", fontSize: 14 },
  feedbackList:     { display: "flex", flexDirection: "column", gap: 0, maxHeight: 360, overflowY: "auto" },
  feedbackItem:     { padding: "12px 16px", borderBottom: "1px solid var(--color-border-tertiary)", display: "flex", flexDirection: "column", gap: 6 },
  feedbackText:     { fontSize: 13, color: "var(--color-text-primary)", margin: 0, lineHeight: 1.5 },
  feedbackMeta:     { display: "flex", gap: 10, alignItems: "center" },
  source:           { fontSize: 11, color: "var(--color-text-tertiary)", background: "var(--color-background-secondary)", padding: "1px 6px", borderRadius: 4 },
  sentimentSmall:   { fontSize: 11, fontWeight: 500 },
  date:             { fontSize: 11, color: "var(--color-text-tertiary)", marginLeft: "auto" },
  empty:            { padding: 16, fontSize: 13, color: "var(--color-text-tertiary)", fontStyle: "italic", margin: 0 },
};
