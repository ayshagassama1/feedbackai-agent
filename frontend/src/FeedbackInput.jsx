import { useState, useRef } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "";

const MODES = [
  { id: "text", label: "Texte libre", icon: "✏️" },
  { id: "csv",  label: "CSV",         icon: "📄" },
  { id: "url",  label: "URL",         icon: "🔗" },
];

const SOURCES = {
  text: { placeholder: "Colle ici un feedback brut, un avis client, une note de support…", rows: 6 },
  url:  { placeholder: "https://www.g2.com/products/… ou lien App Store / Play Store" },
};

export default function FeedbackInput({ projectId, onSuccess }) {
  const [mode, setMode]           = useState("text");
  const [value, setValue]         = useState("");
  const [file, setFile]           = useState(null);
  const [status, setStatus]       = useState("idle"); // idle | loading | success | error
  const [errorMsg, setErrorMsg]   = useState("");
  const [preview, setPreview]     = useState(null);   // {rows, columns} for CSV
  const fileRef                   = useRef(null);

  /* ── CSV preview ── */
  const handleFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    const reader = new FileReader();
    reader.onload = (ev) => {
      const lines = ev.target.result.trim().split("\n").slice(0, 4);
      const cols  = lines[0]?.split(",").length ?? 0;
      setPreview({ rows: lines.length - 1, columns: cols, sample: lines.slice(1) });
    };
    reader.readAsText(f);
  };

  /* ── Submit ── */
  const handleSubmit = async () => {
    if (status === "loading") return;
    if (mode === "text" && !value.trim()) return;
    if (mode === "url"  && !value.trim()) return;
    if (mode === "csv"  && !file)         return;

    setStatus("loading");
    setErrorMsg("");

    try {
      let body;
      let headers = {};

      if (mode === "csv") {
        body = new FormData();
        body.append("file", file);
        body.append("project_id", projectId);
      } else {
        headers["Content-Type"] = "application/json";
        body = JSON.stringify({
          project_id: projectId,
          source:     mode,
          content:    value.trim(),
        });
      }

      const endpoint = mode === "csv" ? `${API_URL}/api/ingest/csv` : `${API_URL}/api/ingest`;
      const res = await fetch(endpoint, {
        method: "POST",
        headers,
        body,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `Erreur ${res.status}`);
      }

      const data = await res.json();
      setStatus("success");
      setValue("");
      setFile(null);
      setPreview(null);
      onSuccess?.(data);

      setTimeout(() => setStatus("idle"), 3000);
    } catch (err) {
      setStatus("error");
      setErrorMsg(err.message);
    }
  };

  /* ── Reset ── */
  const reset = () => {
    setStatus("idle");
    setErrorMsg("");
    setValue("");
    setFile(null);
    setPreview(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const canSubmit =
    status !== "loading" &&
    ((mode === "text" && value.trim()) ||
     (mode === "url"  && value.trim()) ||
     (mode === "csv"  && file));

  return (
    <div style={styles.card}>

      {/* ── Header ── */}
      <div style={styles.header}>
        <span style={styles.title}>Nouveau feedback</span>
        <span style={styles.subtitle}>Analysé par l'agent en quelques secondes</span>
      </div>

      {/* ── Mode tabs ── */}
      <div style={styles.tabs}>
        {MODES.map((m) => (
          <button
            key={m.id}
            onClick={() => { setMode(m.id); reset(); }}
            style={{ ...styles.tab, ...(mode === m.id ? styles.tabActive : {}) }}
          >
            <span style={styles.tabIcon}>{m.icon}</span>
            {m.label}
          </button>
        ))}
      </div>

      {/* ── Input area ── */}
      <div style={styles.inputArea}>

        {/* Text */}
        {mode === "text" && (
          <textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={SOURCES.text.placeholder}
            rows={SOURCES.text.rows}
            style={styles.textarea}
            disabled={status === "loading"}
          />
        )}

        {/* URL */}
        {mode === "url" && (
          <input
            type="url"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={SOURCES.url.placeholder}
            style={styles.input}
            disabled={status === "loading"}
          />
        )}

        {/* CSV */}
        {mode === "csv" && (
          <div>
            <div
              style={{
                ...styles.dropzone,
                ...(file ? styles.dropzoneFilled : {}),
              }}
              onClick={() => fileRef.current?.click()}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                const f = e.dataTransfer.files[0];
                if (f) handleFile({ target: { files: [f] } });
              }}
            >
              {!file ? (
                <>
                  <span style={styles.dropIcon}>📂</span>
                  <span style={styles.dropLabel}>Glisse ton fichier CSV ici</span>
                  <span style={styles.dropHint}>ou clique pour parcourir</span>
                </>
              ) : (
                <>
                  <span style={styles.dropIcon}>✅</span>
                  <span style={styles.dropLabel}>{file.name}</span>
                  <span style={styles.dropHint}>
                    {(file.size / 1024).toFixed(1)} Ko
                  </span>
                </>
              )}
            </div>
            <input
              ref={fileRef}
              type="file"
              accept=".csv"
              style={{ display: "none" }}
              onChange={handleFile}
            />

            {/* CSV preview */}
            {preview && (
              <div style={styles.preview}>
                <span style={styles.previewLabel}>
                  Aperçu · {preview.rows} lignes · {preview.columns} colonnes
                </span>
                <div style={styles.previewRows}>
                  {preview.sample.map((row, i) => (
                    <div key={i} style={styles.previewRow}>
                      {row.split(",").map((cell, j) => (
                        <span key={j} style={styles.previewCell}>
                          {cell.trim().slice(0, 40)}
                        </span>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Error ── */}
      {status === "error" && (
        <div style={styles.errorBanner}>
          <span> {errorMsg}</span>
          <button onClick={reset} style={styles.errorClose}>✕</button>
        </div>
      )}

      {/* ── Footer ── */}
      <div style={styles.footer}>
        {status === "success" ? (
          <div style={styles.successMsg}>
            <span> Feedback ingéré — l'agent analyse en cours…</span>
          </div>
        ) : (
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            style={{
              ...styles.btn,
              ...(canSubmit ? styles.btnActive : styles.btnDisabled),
            }}
          >
            {status === "loading" ? (
              <span style={styles.spinner}>⏳ Analyse en cours…</span>
            ) : (
              "Envoyer à l'agent →"
            )}
          </button>
        )}

        <span style={styles.hint}>
          {mode === "text" && "Texte libre, e-mail client, transcript de support…"}
          {mode === "csv"  && "Colonnes attendues : text, source, date (optionnels)"}
          {mode === "url"  && "G2, Trustpilot, App Store, Play Store supportés"}
        </span>
      </div>
    </div>
  );
}

/* ── Styles ── */
const styles = {
  card: {
    background: "var(--color-background-primary, #fff)",
    border: "1px solid var(--color-border-tertiary, #e5e5e5)",
    borderRadius: 16,
    padding: "24px",
    maxWidth: 560,
    fontFamily: "var(--font-sans, system-ui)",
    display: "flex",
    flexDirection: "column",
    gap: 20,
  },
  header: {
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  title: {
    fontSize: 18,
    fontWeight: 600,
    color: "var(--color-text-primary, #111)",
  },
  subtitle: {
    fontSize: 13,
    color: "var(--color-text-tertiary, #888)",
  },
  tabs: {
    display: "flex",
    gap: 8,
  },
  tab: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    padding: "7px 14px",
    borderRadius: 8,
    border: "1px solid var(--color-border-tertiary, #e5e5e5)",
    background: "transparent",
    fontSize: 13,
    fontWeight: 500,
    color: "var(--color-text-secondary, #555)",
    cursor: "pointer",
    transition: "all .15s",
  },
  tabActive: {
    background: "var(--color-background-secondary, #f5f5f5)",
    borderColor: "var(--color-border-primary, #ccc)",
    color: "var(--color-text-primary, #111)",
  },
  tabIcon: {
    fontSize: 14,
  },
  inputArea: {
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  textarea: {
    width: "100%",
    padding: "12px 14px",
    borderRadius: 10,
    border: "1px solid var(--color-border-tertiary, #e5e5e5)",
    fontSize: 14,
    lineHeight: 1.6,
    color: "var(--color-text-primary, #111)",
    background: "var(--color-background-secondary, #fafafa)",
    resize: "vertical",
    outline: "none",
    boxSizing: "border-box",
    fontFamily: "inherit",
    transition: "border-color .15s",
  },
  input: {
    width: "100%",
    padding: "12px 14px",
    borderRadius: 10,
    border: "1px solid var(--color-border-tertiary, #e5e5e5)",
    fontSize: 14,
    color: "var(--color-text-primary, #111)",
    background: "var(--color-background-secondary, #fafafa)",
    outline: "none",
    boxSizing: "border-box",
    fontFamily: "inherit",
  },
  dropzone: {
    border: "2px dashed var(--color-border-secondary, #ccc)",
    borderRadius: 12,
    padding: "32px 20px",
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 6,
    cursor: "pointer",
    transition: "all .15s",
  },
  dropzoneFilled: {
    borderStyle: "solid",
    borderColor: "var(--color-border-primary, #aaa)",
    background: "var(--color-background-secondary, #fafafa)",
  },
  dropIcon: { fontSize: 28 },
  dropLabel: {
    fontSize: 14,
    fontWeight: 500,
    color: "var(--color-text-primary, #111)",
  },
  dropHint: {
    fontSize: 12,
    color: "var(--color-text-tertiary, #888)",
  },
  preview: {
    marginTop: 12,
    borderRadius: 8,
    border: "1px solid var(--color-border-tertiary, #e5e5e5)",
    overflow: "hidden",
  },
  previewLabel: {
    display: "block",
    padding: "6px 12px",
    fontSize: 11,
    fontWeight: 500,
    color: "var(--color-text-secondary, #555)",
    background: "var(--color-background-secondary, #fafafa)",
    borderBottom: "1px solid var(--color-border-tertiary, #e5e5e5)",
    letterSpacing: "0.04em",
    textTransform: "uppercase",
  },
  previewRows: {
    padding: "8px 12px",
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  previewRow: {
    display: "flex",
    gap: 8,
  },
  previewCell: {
    fontSize: 12,
    color: "var(--color-text-secondary, #555)",
    background: "var(--color-background-tertiary, #f0f0f0)",
    padding: "2px 8px",
    borderRadius: 4,
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
    maxWidth: 160,
  },
  footer: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  btn: {
    padding: "11px 20px",
    borderRadius: 10,
    border: "none",
    fontSize: 14,
    fontWeight: 600,
    cursor: "pointer",
    transition: "all .15s",
    fontFamily: "inherit",
  },
  btnActive: {
    background: "var(--color-text-primary, #111)",
    color: "var(--color-background-primary, #fff)",
  },
  btnDisabled: {
    background: "var(--color-background-secondary, #f0f0f0)",
    color: "var(--color-text-tertiary, #aaa)",
    cursor: "not-allowed",
  },
  hint: {
    fontSize: 12,
    color: "var(--color-text-tertiary, #888)",
  },
  errorBanner: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "10px 14px",
    borderRadius: 8,
    background: "var(--color-background-danger, #fef2f2)",
    border: "1px solid var(--color-border-danger, #fca5a5)",
    fontSize: 13,
    color: "var(--color-text-danger, #b91c1c)",
  },
  errorClose: {
    background: "none",
    border: "none",
    cursor: "pointer",
    fontSize: 13,
    color: "var(--color-text-danger, #b91c1c)",
    padding: 0,
  },
  successMsg: {
    padding: "10px 14px",
    borderRadius: 8,
    background: "var(--color-background-success, #f0fdf4)",
    border: "1px solid var(--color-border-success, #86efac)",
    fontSize: 13,
    color: "var(--color-text-success, #15803d)",
  },
  spinner: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
  },
};
