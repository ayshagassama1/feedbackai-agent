import { useState, useRef, useEffect } from "react";

const API_URL = import.meta.env.VITE_API_URL ?? "";

const SUGGESTIONS = [
  "Quels sont les bugs les plus signalés cette semaine ?",
  "Montre-moi les feedbacks négatifs sur l'onboarding",
  "Quelles features sont les plus demandées ?",
  "Résume les feedbacks des 7 derniers jours",
];

export default function AgentChat({ projectId }) {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Bonjour ! Je suis votre agent d'analyse de feedback. Posez-moi une question sur vos retours utilisateurs.",
    },
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
      if (!res.ok) throw new Error(`Erreur ${res.status}`);
      const data = await res.json();
      setMessages((prev) => [...prev, { role: "assistant", content: data.response }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Désolé, une erreur est survenue : ${err.message}` },
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

      {/* Messages */}
      <div style={st.messages}>
        {messages.map((m, i) => (
          <div key={i} style={{ ...st.message, ...(m.role === "user" ? st.userMsg : st.assistantMsg) }}>
            {m.role === "assistant" && <span style={st.avatar}>🤖</span>}
            <div style={{ ...st.bubble, ...(m.role === "user" ? st.userBubble : st.assistantBubble) }}>
              {m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ ...st.message, ...st.assistantMsg }}>
            <span style={st.avatar}>🤖</span>
            <div style={{ ...st.bubble, ...st.assistantBubble, ...st.typing }}>
              <span>●</span><span>●</span><span>●</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggestions */}
      {messages.length === 1 && (
        <div style={st.suggestions}>
          {SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => send(s)} style={st.suggestion}>
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <div style={st.inputRow}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Posez une question sur vos feedbacks…"
          rows={2}
          style={st.textarea}
          disabled={loading}
        />
        <button
          onClick={() => send()}
          disabled={!input.trim() || loading}
          style={{ ...st.sendBtn, ...(input.trim() && !loading ? st.sendBtnActive : st.sendBtnDisabled) }}
        >
          →
        </button>
      </div>
      <p style={st.hint}>Entrée pour envoyer · Shift+Entrée pour nouvelle ligne</p>
    </div>
  );
}

const st = {
  wrapper:        { display: "flex", flexDirection: "column", gap: 12, fontFamily: "var(--font-sans, system-ui)", height: "100%" },
  messages:       { display: "flex", flexDirection: "column", gap: 12, overflowY: "auto", maxHeight: 420, padding: "4px 0" },
  message:        { display: "flex", gap: 10, alignItems: "flex-end" },
  userMsg:        { flexDirection: "row-reverse" },
  assistantMsg:   { flexDirection: "row" },
  avatar:         { fontSize: 20, flexShrink: 0, marginBottom: 2 },
  bubble:         { maxWidth: "75%", padding: "10px 14px", borderRadius: 12, fontSize: 14, lineHeight: 1.6 },
  userBubble:     { background: "var(--color-text-primary)", color: "var(--color-background-primary)", borderBottomRightRadius: 4 },
  assistantBubble:{ background: "var(--color-background-secondary)", color: "var(--color-text-primary)", border: "1px solid var(--color-border-tertiary)", borderBottomLeftRadius: 4 },
  typing:         { display: "flex", gap: 4, alignItems: "center", padding: "12px 16px" },
  suggestions:    { display: "flex", flexDirection: "column", gap: 6 },
  suggestion:     { textAlign: "left", padding: "8px 14px", borderRadius: 8, border: "1px solid var(--color-border-tertiary)", background: "transparent", fontSize: 13, color: "var(--color-text-secondary)", cursor: "pointer", transition: "all .15s" },
  inputRow:       { display: "flex", gap: 8, alignItems: "flex-end" },
  textarea:       { flex: 1, padding: "10px 12px", borderRadius: 10, border: "1px solid var(--color-border-tertiary)", fontSize: 14, fontFamily: "inherit", resize: "none", outline: "none", background: "var(--color-background-secondary)", color: "var(--color-text-primary)", lineHeight: 1.5 },
  sendBtn:        { padding: "10px 16px", borderRadius: 10, border: "none", fontSize: 18, cursor: "pointer", flexShrink: 0, fontFamily: "inherit", transition: "all .15s" },
  sendBtnActive:  { background: "var(--color-text-primary)", color: "var(--color-background-primary)" },
  sendBtnDisabled:{ background: "var(--color-background-secondary)", color: "var(--color-text-tertiary)", cursor: "not-allowed" },
  hint:           { fontSize: 11, color: "var(--color-text-tertiary)", margin: 0 },
};
