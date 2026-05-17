import { useState, useEffect, useRef } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ── Shared styles ─────────────────────────────────────────────────────────────
const S = {
  input: {
    background: "#1a1a1a", border: "1px solid #333", borderRadius: 8,
    color: "#ececec", padding: "8px 12px", fontSize: 14, width: "100%",
    outline: "none",
  },
  btn: (disabled, color = "#2563eb") => ({
    background: disabled ? "#333" : color,
    color: "#fff", border: "none", borderRadius: 8,
    padding: "10px 18px", cursor: disabled ? "not-allowed" : "pointer",
    fontWeight: 600, fontSize: 14, transition: "background 0.2s",
  }),
  label: { fontSize: 12, color: "#888", marginBottom: 4, display: "block" },
  card: {
    background: "#1a1a1a", border: "1px solid #2a2a2a",
    borderRadius: 10, padding: 16, marginBottom: 12,
  },
};

// ── Chat bubbles ──────────────────────────────────────────────────────────────
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

// ── Status badge ──────────────────────────────────────────────────────────────
const StatusBadge = ({ status }) => {
  const colors = {
    pending: "#92400e", running: "#1e3a8a", completed: "#14532d",
    failed: "#7f1d1d", unknown: "#333",
  };
  const labels = {
    pending: "⏳ Pending", running: "⚙️ Training on Modal GPU…",
    completed: "✅ Completed", failed: "❌ Failed",
  };
  return (
    <span style={{
      background: colors[status] || colors.unknown,
      color: "#fff", borderRadius: 20, padding: "3px 12px", fontSize: 12, fontWeight: 600,
    }}>
      {labels[status] || status}
    </span>
  );
};

// ══════════════════════════════════════════════════════════════════════════════
// Chat Tab
// ══════════════════════════════════════════════════════════════════════════════
function ChatTab({ modelInfo, setModelInfo }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || loading) return;
    const newHistory = [...messages, { role: "user", content: text }];
    setMessages(newHistory);
    setInput("");
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, history: messages }),
      });
      if (!res.ok) throw new Error(`Server error ${res.status}`);
      const data = await res.json();
      setMessages([...newHistory, { role: "assistant", content: data.reply }]);
      setModelInfo({ model_name: data.model_name, model_version: data.model_version });
    } catch (err) {
      setMessages([...newHistory, { role: "assistant", content: `⚠️ ${err.message}` }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, overflow: "hidden" }}>
      <div style={{ flex: 1, overflowY: "auto", padding: "20px 16px" }}>
        {messages.length === 0 && (
          <div style={{ textAlign: "center", color: "#555", marginTop: 80 }}>
            <div style={{ fontSize: 48 }}>🤖</div>
            <p style={{ marginTop: 12 }}>Start a conversation</p>
            <p style={{ fontSize: 12, marginTop: 4, color: "#444" }}>
              {modelInfo.model_name} ({modelInfo.model_version})
            </p>
          </div>
        )}
        {messages.map((m, i) =>
          m.role === "user" ? <UserBubble key={i} text={m.content} /> : <BotBubble key={i} text={m.content} />
        )}
        {loading && <BotBubble loading />}
        <div ref={bottomRef} />
      </div>

      <div style={{ padding: "12px 16px", background: "#111", borderTop: "1px solid #222" }}>
        <div style={{ display: "flex", gap: 8 }}>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
            rows={1}
            placeholder="Message… (Enter to send)"
            style={{ ...S.input, flex: 1, resize: "none", maxHeight: 120, overflowY: "auto" }}
          />
          <button onClick={sendMessage} disabled={loading || !input.trim()} style={S.btn(loading || !input.trim())}>
            {loading ? "…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Training Tab
// ══════════════════════════════════════════════════════════════════════════════
function TrainingTab() {
  const [file, setFile] = useState(null);
  const [form, setForm] = useState({
    base_model: "meta-llama/Meta-Llama-3.1-8B",
    hf_repo_id: "",
    version_tag: "v2",
    epochs: "2",
    lora_r: "16",
    lora_alpha: "32",
  });
  const [jobId, setJobId] = useState(null);
  const [job, setJob] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const logsEndRef = useRef(null);

  // Poll job status while running
  useEffect(() => {
    if (!jobId || job?.status === "completed" || job?.status === "failed") return;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/training-status/${jobId}`);
        const data = await res.json();
        setJob(data);
      } catch (_) {}
    }, 3000);
    return () => clearInterval(interval);
  }, [jobId, job?.status]);

  useEffect(() => { logsEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [job?.logs]);

  const setField = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const submit = async () => {
    if (!file) { setError("Upload a training data file (.jsonl)"); return; }
    if (!form.hf_repo_id) { setError("Enter a HuggingFace repo ID"); return; }
    setError(null);
    setSubmitting(true);
    setJob(null);
    setJobId(null);

    try {
      const fd = new FormData();
      fd.append("file", file);
      Object.entries(form).forEach(([k, v]) => fd.append(k, v));

      const res = await fetch(`${API_BASE}/api/train/upload`, { method: "POST", body: fd });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      setJobId(data.job_id);
      setJob({ status: "pending", logs: [] });
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: "24px 20px" }}>
      <h2 style={{ margin: "0 0 4px", fontSize: 18 }}>🧠 Fine-tune Model</h2>
      <p style={{ color: "#666", fontSize: 13, margin: "0 0 20px" }}>
        Training runs on Modal A10G GPU (24GB VRAM) via QLoRA. Takes ~1–2 hours for Llama 3.1 8B.
      </p>

      {/* Form */}
      <div style={S.card}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          {/* Data upload */}
          <div style={{ gridColumn: "1 / -1" }}>
            <label style={S.label}>Training Data (.jsonl) *</label>
            <input
              type="file"
              accept=".jsonl,.json"
              onChange={e => setFile(e.target.files[0])}
              style={{ ...S.input, padding: "6px 10px" }}
            />
            {file && <p style={{ fontSize: 12, color: "#4ade80", marginTop: 4 }}>✓ {file.name} ({(file.size / 1024).toFixed(1)} KB)</p>}
            <p style={{ fontSize: 11, color: "#555", marginTop: 4 }}>
              Format: one JSON per line — {`{"conversations": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]}`}
            </p>
          </div>

          {/* Base model */}
          <div>
            <label style={S.label}>Base Model</label>
            <input style={S.input} value={form.base_model} onChange={e => setField("base_model", e.target.value)} />
          </div>

          {/* HF repo */}
          <div>
            <label style={S.label}>HuggingFace Repo ID * (e.g. yourname/llama-v2)</label>
            <input style={S.input} value={form.hf_repo_id}
              onChange={e => setField("hf_repo_id", e.target.value)}
              placeholder="yourname/llama-finetuned-v2" />
          </div>

          {/* Version */}
          <div>
            <label style={S.label}>Version Tag</label>
            <input style={S.input} value={form.version_tag} onChange={e => setField("version_tag", e.target.value)} />
          </div>

          {/* Epochs */}
          <div>
            <label style={S.label}>Epochs</label>
            <input style={S.input} type="number" min="1" max="10" value={form.epochs}
              onChange={e => setField("epochs", e.target.value)} />
          </div>

          {/* LoRA r */}
          <div>
            <label style={S.label}>LoRA Rank (r)</label>
            <input style={S.input} type="number" value={form.lora_r}
              onChange={e => setField("lora_r", e.target.value)} />
          </div>

          {/* LoRA alpha */}
          <div>
            <label style={S.label}>LoRA Alpha</label>
            <input style={S.input} type="number" value={form.lora_alpha}
              onChange={e => setField("lora_alpha", e.target.value)} />
          </div>
        </div>

        {error && <p style={{ color: "#f87171", fontSize: 13, marginTop: 12 }}>⚠️ {error}</p>}

        <div style={{ marginTop: 16 }}>
          <button onClick={submit} disabled={submitting || !!jobId && job?.status === "running"}
            style={S.btn(submitting)}>
            {submitting ? "Submitting…" : "🚀 Start Training on Modal"}
          </button>
          <span style={{ fontSize: 12, color: "#555", marginLeft: 12 }}>
            Requires HF_TOKEN + Modal secret set on server
          </span>
        </div>
      </div>

      {/* Job status */}
      {job && (
        <div style={S.card}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <span style={{ fontWeight: 600 }}>Job {jobId?.slice(0, 8)}</span>
            <StatusBadge status={job.status} />
          </div>

          {job.status === "completed" && (
            <div style={{ background: "#14532d22", border: "1px solid #14532d", borderRadius: 8, padding: 12, marginBottom: 12 }}>
              <p style={{ color: "#4ade80", fontWeight: 600, margin: 0 }}>
                ✅ Model deployed: <code style={{ background: "#0a0a0a", padding: "2px 6px", borderRadius: 4 }}>{job.model_name} ({job.version})</code>
              </p>
              <p style={{ color: "#888", fontSize: 12, margin: "4px 0 0" }}>
                Cluster rolling update triggered. New model live in ~2 min.
              </p>
            </div>
          )}

          {job.status === "failed" && (
            <div style={{ background: "#7f1d1d22", border: "1px solid #7f1d1d", borderRadius: 8, padding: 12, marginBottom: 12 }}>
              <p style={{ color: "#f87171", margin: 0 }}>❌ {job.error}</p>
            </div>
          )}

          {/* Logs */}
          <div style={{
            background: "#0a0a0a", border: "1px solid #222", borderRadius: 6,
            padding: 12, maxHeight: 240, overflowY: "auto", fontFamily: "monospace", fontSize: 12,
          }}>
            {(job.logs || []).length === 0
              ? <span style={{ color: "#444" }}>Waiting for logs…</span>
              : (job.logs || []).map((l, i) => (
                <div key={i} style={{ color: "#a3e635", marginBottom: 2 }}>› {l}</div>
              ))
            }
            <div ref={logsEndRef} />
          </div>
        </div>
      )}

      {/* JSONL format help */}
      <div style={{ ...S.card, borderColor: "#1e3a8a" }}>
        <p style={{ color: "#93c5fd", fontWeight: 600, margin: "0 0 8px", fontSize: 13 }}>📋 Training data format</p>
        <pre style={{
          background: "#0a0a0a", padding: 12, borderRadius: 6,
          fontSize: 11, color: "#a3e635", overflowX: "auto", margin: 0,
        }}>{`{"conversations": [
  {"role": "user",      "content": "What is Python?"},
  {"role": "assistant", "content": "Python is a programming language."}
]}
{"conversations": [
  {"role": "user",      "content": "Tell me a joke"},
  {"role": "assistant", "content": "Why do programmers prefer dark mode?"}
]}`}</pre>
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Main App
// ══════════════════════════════════════════════════════════════════════════════
export default function App() {
  const [tab, setTab] = useState("chat");
  const [modelInfo, setModelInfo] = useState({ model_name: "—", model_version: "—" });

  useEffect(() => {
    fetch(`${API_BASE}/version`)
      .then(r => r.json())
      .then(setModelInfo)
      .catch(() => setModelInfo({ model_name: "unreachable", model_version: "?" }));
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100dvh", maxWidth: 900, margin: "0 auto", width: "100%" }}>
      {/* Header */}
      <header style={{
        padding: "12px 20px", background: "#111", borderBottom: "1px solid #222",
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <span style={{ fontWeight: 700, fontSize: 18 }}>🤖 LLM Platform</span>
          {/* Tabs */}
          <div style={{ display: "flex", gap: 4 }}>
            {["chat", "training"].map(t => (
              <button key={t} onClick={() => setTab(t)} style={{
                background: tab === t ? "#2563eb" : "transparent",
                color: tab === t ? "#fff" : "#888",
                border: "1px solid " + (tab === t ? "#2563eb" : "#333"),
                borderRadius: 6, padding: "4px 14px", cursor: "pointer",
                fontSize: 13, fontWeight: 600, textTransform: "capitalize",
              }}>
                {t === "chat" ? "💬 Chat" : "🧠 Training"}
              </button>
            ))}
          </div>
        </div>
        <span style={{
          fontSize: 12, background: "#1e3a8a", color: "#93c5fd",
          borderRadius: 20, padding: "4px 12px", fontWeight: 600,
        }}>
          {modelInfo.model_version} · {modelInfo.model_name.split("/").pop()}
        </span>
      </header>

      {/* Tab content */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        {tab === "chat"
          ? <ChatTab modelInfo={modelInfo} setModelInfo={setModelInfo} />
          : <TrainingTab />
        }
      </div>
    </div>
  );
}
