import { useState, useRef } from "react";
import { theme } from "./theme";
import { translations } from "./i18n";

const API_URL = import.meta.env.VITE_API_URL ?? "";

export default function FeedbackInput({ projectId, lang, onSuccess }) {
  const t = translations[lang];
  const MODES = [
    { id: "text", label: t.feedbackInput.modeText },
    { id: "csv",  label: t.feedbackInput.modeCsv },
    { id: "url",  label: t.feedbackInput.modeUrl },
  ];

  const [mode, setMode]           = useState("text");
  const [value, setValue]         = useState("");
  const [file, setFile]           = useState(null);
  const [status, setStatus]       = useState("idle"); // idle | loading | success | error
  const [errorMsg, setErrorMsg]   = useState("");
  const [preview, setPreview]     = useState(null);   // {rows, columns} for CSV
  const fileRef                   = useRef(null);

  /* Prévisualisation CSV */
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

  /* Envoi */
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
        throw new Error(err.detail ?? `${res.status}`);
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

  /* Réinitialisation */
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
    <div className="card-elevate" style={styles.card}>

      <div style={styles.header}>
        <span style={styles.title}>{t.feedbackInput.title}</span>
        <span style={styles.subtitle}>{t.feedbackInput.subtitle}</span>
      </div>

      <div style={styles.tabs}>
        {MODES.map((m) => (
          <button
            key={m.id}
            onClick={() => { setMode(m.id); reset(); }}
            style={{ ...styles.tab, ...(mode === m.id ? styles.tabActive : {}) }}
          >
            {m.label}
          </button>
        ))}
      </div>

      <div style={styles.inputArea}>

        {mode === "text" && (
          <textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={t.feedbackInput.placeholderText}
            rows={6}
            style={styles.textarea}
            disabled={status === "loading"}
          />
        )}

        {mode === "url" && (
          <input
            type="url"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={t.feedbackInput.placeholderUrl}
            style={styles.input}
            disabled={status === "loading"}
          />
        )}

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
                  <span style={styles.dropLabel}>{t.feedbackInput.dropCsv}</span>
                  <span style={styles.dropHint}>{t.feedbackInput.orBrowse}</span>
                </>
              ) : (
                <>
                  <span style={styles.dropLabel}>{file.name}</span>
                  <span style={styles.dropHint}>
                    {(file.size / 1024).toFixed(1)} KB
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

            {preview && (
              <div style={styles.preview}>
                <span style={styles.previewLabel}>
                  {t.feedbackInput.preview} · {preview.rows} {t.feedbackInput.rows} · {preview.columns} {t.feedbackInput.columns}
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

      {status === "error" && (
        <div style={styles.errorBanner}>
          <span>{t.feedbackInput.error}: {errorMsg}</span>
          <button onClick={reset} style={styles.errorClose}>×</button>
        </div>
      )}

      <div style={styles.footer}>
        {status === "success" ? (
          <div style={styles.successMsg}>{t.feedbackInput.success}</div>
        ) : (
          <button
            className="btn-elevate"
            onClick={handleSubmit}
            disabled={!canSubmit}
            style={{
              ...styles.btn,
              ...(canSubmit ? styles.btnActive : styles.btnDisabled),
            }}
          >
            {status === "loading" ? t.feedbackInput.submitting : t.feedbackInput.submit}
          </button>
        )}

        <span style={styles.hint}>
          {mode === "text" && t.feedbackInput.hintText}
          {mode === "csv"  && t.feedbackInput.hintCsv}
          {mode === "url"  && t.feedbackInput.hintUrl}
        </span>
      </div>
    </div>
  );
}

/* Styles */
const styles = {
  card: {
    background: theme.color.bgPrimary,
    border: `1px solid ${theme.color.borderTertiary}`,
    borderRadius: theme.radius.lg + 6,
    boxShadow: theme.shadow.sm,
    padding: 24,
    maxWidth: 560,
    fontFamily: theme.font.sans,
    display: "flex",
    flexDirection: "column",
    gap: 20,
  },
  header: { display: "flex", flexDirection: "column", gap: 4 },
  title: { fontSize: 18, fontWeight: 600, color: theme.color.textPrimary, letterSpacing: "-0.01em" },
  subtitle: { fontSize: 13, color: theme.color.textTertiary },
  tabs: { display: "flex", gap: 8 },
  tab: {
    padding: "7px 14px",
    borderRadius: theme.radius.md,
    border: `1px solid ${theme.color.borderTertiary}`,
    background: "transparent",
    fontSize: 13,
    fontWeight: 500,
    color: theme.color.textSecondary,
    cursor: "pointer",
    fontFamily: "inherit",
    transition: "all .15s",
  },
  tabActive: {
    background: theme.color.brandLight,
    borderColor: theme.color.brandBorder,
    color: theme.color.brandHover,
  },
  inputArea: { display: "flex", flexDirection: "column", gap: 12 },
  textarea: {
    width: "100%",
    padding: "12px 14px",
    borderRadius: theme.radius.md,
    border: `1px solid ${theme.color.borderTertiary}`,
    fontSize: 14,
    lineHeight: 1.6,
    color: theme.color.textPrimary,
    background: theme.color.bgSecondary,
    resize: "vertical",
    outline: "none",
    boxSizing: "border-box",
    fontFamily: "inherit",
  },
  input: {
    width: "100%",
    padding: "12px 14px",
    borderRadius: theme.radius.md,
    border: `1px solid ${theme.color.borderTertiary}`,
    fontSize: 14,
    color: theme.color.textPrimary,
    background: theme.color.bgSecondary,
    outline: "none",
    boxSizing: "border-box",
    fontFamily: "inherit",
  },
  dropzone: {
    border: `2px dashed ${theme.color.borderSecondary}`,
    borderRadius: theme.radius.lg,
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
    borderColor: theme.color.brand,
    background: theme.color.brandLight,
  },
  dropLabel: { fontSize: 14, fontWeight: 500, color: theme.color.textPrimary },
  dropHint: { fontSize: 12, color: theme.color.textTertiary },
  preview: {
    marginTop: 12,
    borderRadius: theme.radius.md,
    border: `1px solid ${theme.color.borderTertiary}`,
    overflow: "hidden",
  },
  previewLabel: {
    display: "block",
    padding: "6px 12px",
    fontSize: 11,
    fontWeight: 500,
    color: theme.color.textSecondary,
    background: theme.color.bgSecondary,
    borderBottom: `1px solid ${theme.color.borderTertiary}`,
    letterSpacing: "0.04em",
    textTransform: "uppercase",
  },
  previewRows: { padding: "8px 12px", display: "flex", flexDirection: "column", gap: 4 },
  previewRow: { display: "flex", gap: 8 },
  previewCell: {
    fontSize: 12,
    color: theme.color.textSecondary,
    background: theme.color.bgTertiary,
    padding: "2px 8px",
    borderRadius: theme.radius.sm,
    whiteSpace: "nowrap",
    overflow: "hidden",
    textOverflow: "ellipsis",
    maxWidth: 160,
  },
  footer: { display: "flex", flexDirection: "column", gap: 8 },
  btn: {
    padding: "11px 20px",
    borderRadius: theme.radius.md,
    border: "none",
    fontSize: 14,
    fontWeight: 600,
    cursor: "pointer",
    transition: "background .15s",
    fontFamily: "inherit",
  },
  btnActive: { background: theme.color.brand, color: theme.color.textOnBrand },
  btnDisabled: { background: theme.color.bgTertiary, color: theme.color.textTertiary, cursor: "not-allowed" },
  hint: { fontSize: 12, color: theme.color.textTertiary },
  errorBanner: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "10px 14px",
    borderRadius: theme.radius.md,
    background: theme.color.dangerBg,
    border: `1px solid ${theme.color.dangerBorder}`,
    fontSize: 13,
    color: theme.color.danger,
  },
  errorClose: { background: "none", border: "none", cursor: "pointer", fontSize: 16, color: theme.color.danger, padding: 0, lineHeight: 1 },
  successMsg: {
    padding: "10px 14px",
    borderRadius: theme.radius.md,
    background: theme.color.brandLight,
    border: `1px solid ${theme.color.brandBorder}`,
    fontSize: 13,
    color: theme.color.brandHover,
  },
};
