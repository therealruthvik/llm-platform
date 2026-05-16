import { useState, useEffect, useRef } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ── Helpers ──────────────────────────────────────────────────────────────────
const UserBubble = ({ text }) => (
  <div style={{ display: "flex", justifyContent: "flex-end", margin: "8px 0" }}>
    <div style={{
      background: "#2563eb", color: "#fff", borderRadius: "18px 18px 4px 18px",
      padding: "10px 16px", maxWidth: "75%", whiteSpace: "pre-wrap", lineHeight: 1.5,
    }}>{text}</div>
  </div>
);

const BotBubble = ({ text, loading }) => (
  <div style={{ display: "flex", justifyContent: "flex-start", margin: "8px 0" }}>
    <div style={{
      background: "#1e1e1e", border: "1px solid #333", borderRadius: "18px 18px 18px 4px",
      padding: "10px 16px", maxWidth: "75%", whiteSpace: "pre-wrap", lineHeight: 1.5,
      color: loading ? "#888" : "#ececec",
    }}>
      {loading ? "Thinking…" : text}
    </div>
  </div>
);

// ── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [messages, setMessages] = useState([]);   // {role, content}
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [modelInfo, setModelInfo] = useState({ model_name: "—", model_version: "—" });
  const [error, setError] = useState(null);
  const bottomRef = useRef(null);

  // Fetch model version on mount
  useEffect(() => {
    fetch(`${API_BASE}/version`)
      .then(r => r.json())
      .then(setModelInfo)
      .catch(() => setModelInfo({ model_name: "unreachable", model_version: "?" }));
  }, []);

  // Auto-scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const newHistory = [...messages, { role: "user", content: text }];
    setMessages(newHistory);
    setInput("");
    setLoading(true);
    setError(null);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history: messages }),
      });

      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const data = await res.json();

      setMessages([...newHistory, { role: "assistant", content: data.reply }]);
      // Update model info from response
      setModelInfo({ model_name: data.model_name, model_version: data.model_version });
    } catch (err) {
      setError(err.message);
      setMessages([...newHistory, { role: "assistant", content: `⚠️ Error: ${err.message}` }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100dvh", maxWidth: 800, margin: "0 auto", width: "100%" }}>

      {/* Header */}
      <header style={{
        padding: "14px 20px", background: "#111", borderBottom: "1px solid #222",
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <span style={{ fontWeight: 700, fontSize: 18 }}>🤖 LLM Chat</span>
        <span style={{
          fontSize: 12, background: "#1e3a8a", color: "#93c5fd",
          borderRadius: 20, padding: "4px 12px", fontWeight: 600,
        }}>
          {modelInfo.model_version} · {modelInfo.model_name.split("/").pop()}
        </span>
      </header>

      {/* Message list */}
      <div style={{ flex: 1, overflowY: "auto", padding: "20px 16px" }}>
        {messages.length === 0 && (
          <div style={{ textAlign: "center", color: "#555", marginTop: 80 }}>
            <div style={{ fontSize: 48 }}>🤖</div>
            <p style={{ marginTop: 12 }}>Start a conversation</p>
            <p style={{ fontSize: 12, marginTop: 4, color: "#444" }}>
              Model: {modelInfo.model_name} ({modelInfo.model_version})
            </p>
          </div>
        )}

        {messages.map((m, i) =>
          m.role === "user"
            ? <UserBubble key={i} text={m.content} />
            : <BotBubble key={i} text={m.content} />
        )}

        {loading && <BotBubble loading />}
        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div style={{ padding: "12px 16px", background: "#111", borderTop: "1px solid #222" }}>
        <div style={{ display: "flex", gap: 8 }}>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKey}
            rows={1}
            placeholder="Message… (Enter to send, Shift+Enter for newline)"
            style={{
              flex: 1, resize: "none", background: "#1a1a1a", border: "1px solid #333",
              borderRadius: 12, color: "#ececec", padding: "10px 14px", fontSize: 14,
              outline: "none", maxHeight: 120, overflowY: "auto",
            }}
          />
          <button
            onClick={sendMessage}
            disabled={loading || !input.trim()}
            style={{
              background: loading || !input.trim() ? "#333" : "#2563eb",
              color: "#fff", border: "none", borderRadius: 12,
              padding: "10px 18px", cursor: loading ? "not-allowed" : "pointer",
              fontWeight: 600, transition: "background 0.2s",
            }}
          >
            {loading ? "…" : "Send"}
          </button>
        </div>
        <p style={{ fontSize: 11, color: "#444", marginTop: 6, textAlign: "center" }}>
          LLM Pipeline · Model version updates automatically on deployment
        </p>
      </div>
    </div>
  );
}
