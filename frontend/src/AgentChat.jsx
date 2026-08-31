import { useState, useRef, useEffect } from "react";
import { theme } from "./theme";
import { translations } from "./i18n";

const API_URL = import.meta.env.VITE_API_URL ?? "";

/* Rendu markdown minimal (titres #-####, listes -/*, gras **texte**) : le modèle répond en
   markdown, mais le rendait jusqu'ici en texte brut, symboles littéraux compris. Pas de
   dépendance externe pour un besoin aussi ciblé. */
function renderMarkdown(text) {
  const lines = text.split("\n");
  const elements = [];
  let listItems = null;

  const flushList = () => {
    if (listItems) {
      elements.push(
        <ul key={`ul-${elements.length}`} style={{ margin: "4px 0", paddingLeft: 18 }}>
          {listItems.map((item, j) => <li key={j}>{item}</li>)}
        </ul>
      );
      listItems = null;
    }
  };

  const renderInline = (line) =>
    line.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
      part.startsWith("**") && part.endsWith("**")
        ? <strong key={i}>{part.slice(2, -2)}</strong>
        : <span key={i}>{part}</span>
    );

  lines.forEach((line, i) => {
    const trimmed = line.trim();
    if (!trimmed) { flushList(); return; }

    const headerMatch = trimmed.match(/^#{1,4}\s+(.*)/);
    if (headerMatch) {
      flushList();
      elements.push(
        <div key={i} style={{ fontWeight: 700, marginTop: elements.length ? 10 : 0 }}>
          {renderInline(headerMatch[1])}
        </div>
      );
      return;
    }

    const bulletMatch = trimmed.match(/^[-*]\s+(.*)/);
    if (bulletMatch) {
      if (!listItems) listItems = [];
      listItems.push(renderInline(bulletMatch[1]));
      return;
    }

    flushList();
    elements.push(<p key={i} style={{ margin: "4px 0" }}>{renderInline(trimmed)}</p>);
  });
  flushList();

  return elements;
}

export default function AgentChat({ projectId, lang }) {
  const t = translations[lang];
  const [messages, setMessages] = useState([
    { role: "assistant", content: t.chat.greeting },
  ]);
  const [input, setInput]       = useState("");
  const [loading, setLoading]   = useState(false);
  const bottomRef               = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async (text) => {
    const content = (text ?? input).trim();
    if (!content || loading) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content }]);
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/api/agent/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId,
          message: content,
          history: messages.slice(-6),
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `${res.status}`);
      }
      const data = await res.json();
      setMessages((prev) => [...prev, { role: "assistant", content: data.response }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `${t.chat.error} ${err.message}` },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  };

  return (
    <div style={st.wrapper}>

      <div style={st.messages}>
        {messages.map((m, i) => (
          <div key={i} style={{ ...st.message, ...(m.role === "user" ? st.userMsg : st.assistantMsg) }}>
            <div style={{ ...st.bubble, ...(m.role === "user" ? st.userBubble : st.assistantBubble) }}>
              {m.role === "assistant" ? renderMarkdown(m.content) : m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ ...st.message, ...st.assistantMsg }}>
            <div style={{ ...st.bubble, ...st.assistantBubble, ...st.typing }}>
              <span>●</span><span>●</span><span>●</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {messages.length === 1 && (
        <div style={st.suggestions}>
          {t.chat.suggestions.map((s) => (
            <button key={s} onClick={() => send(s)} style={st.suggestion}>
              {s}
            </button>
          ))}
        </div>
      )}

      <div style={st.inputRow}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder={t.chat.placeholder}
          rows={2}
          style={st.textarea}
          disabled={loading}
        />
        <button
          className="btn-elevate"
          onClick={() => send()}
          disabled={!input.trim() || loading}
          style={{ ...st.sendBtn, ...(input.trim() && !loading ? st.sendBtnActive : st.sendBtnDisabled) }}
        >
          →
        </button>
      </div>
      <p style={st.hint}>{t.chat.hint}</p>
    </div>
  );
}

const st = {
  wrapper:        { display: "flex", flexDirection: "column", gap: 12, fontFamily: theme.font.sans, height: "100%" },
  messages:       { display: "flex", flexDirection: "column", gap: 12, overflowY: "auto", maxHeight: 420, padding: "4px 0" },
  message:        { display: "flex", gap: 10, alignItems: "flex-end" },
  userMsg:        { flexDirection: "row-reverse" },
  assistantMsg:   { flexDirection: "row" },
  bubble:         { maxWidth: "75%", padding: "10px 14px", borderRadius: theme.radius.lg, fontSize: 14, lineHeight: 1.6 },
  userBubble:     { background: theme.color.brand, color: theme.color.textOnBrand, borderBottomRightRadius: 4 },
  assistantBubble:{ background: theme.color.bgSecondary, color: theme.color.textPrimary, border: `1px solid ${theme.color.borderTertiary}`, borderBottomLeftRadius: 4 },
  typing:         { display: "flex", gap: 4, alignItems: "center", padding: "12px 16px" },
  suggestions:    { display: "flex", flexDirection: "column", gap: 6 },
  suggestion:     { textAlign: "left", padding: "8px 14px", borderRadius: theme.radius.md, border: `1px solid ${theme.color.borderTertiary}`, background: "transparent", fontSize: 13, color: theme.color.textSecondary, cursor: "pointer", fontFamily: "inherit", transition: "border-color .15s" },
  inputRow:       { display: "flex", gap: 8, alignItems: "flex-end" },
  textarea:       { flex: 1, padding: "10px 12px", borderRadius: theme.radius.md, border: `1px solid ${theme.color.borderTertiary}`, fontSize: 14, fontFamily: "inherit", resize: "none", outline: "none", background: theme.color.bgSecondary, color: theme.color.textPrimary, lineHeight: 1.5 },
  sendBtn:        { padding: "10px 16px", borderRadius: theme.radius.md, border: "none", fontSize: 18, cursor: "pointer", flexShrink: 0, fontFamily: "inherit", transition: "background .15s" },
  sendBtnActive:  { background: theme.color.brand, color: theme.color.textOnBrand },
  sendBtnDisabled:{ background: theme.color.bgTertiary, color: theme.color.textTertiary, cursor: "not-allowed" },
  hint:           { fontSize: 11, color: theme.color.textTertiary, margin: 0 },
};
