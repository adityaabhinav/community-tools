import { useEffect, useRef, useState } from "react";
import { useChat, ChatMode } from "./hooks/useChat";
import { ChatMessage } from "./components/ChatMessage";
import { HistoryPanel } from "./components/HistoryPanel";
import { ModelSelector } from "./components/ModelSelector";
import { CompareView } from "./components/CompareView";

const MODES: { key: ChatMode; label: string; color: string }[] = [
  { key: "api",        label: "Direct API",    color: "#0f766e" },
  { key: "mcp",        label: "Direct MCP",    color: "#204ec4" },
  { key: "claude_mcp", label: "Claude + MCP",  color: "#7c3aed" },
];

export default function App() {
  const [mode, setMode] = useState<ChatMode>("api");
  const [model, setModel] = useState<string | undefined>(undefined);
  const {
    messages,
    loading,
    viewingHistory,
    sendMessage,
    loadConversation,
    clearMessages,
    dismissHistoryBanner,
  } = useChat(mode, model);
  const [input, setInput] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const [compare, setCompare] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = input.trim();
    if (!q || loading) return;
    setInput("");
    sendMessage(q);
  };

  return (
    <div style={appStyle}>
      <header style={headerStyle}>
        <span style={logoStyle}>Spotter Integration POC</span>
        <div style={modeBarStyle}>
          {!compare && MODES.map((m) => (
            <button
              key={m.key}
              style={{
                ...modePillStyle,
                background: mode === m.key ? m.color : "#f1f5f9",
                color: mode === m.key ? "#fff" : "#475569",
                borderColor: mode === m.key ? m.color : "#e2e8f0",
              }}
              onClick={() => { setMode(m.key); clearMessages(); }}
            >
              {m.label}
            </button>
          ))}
          <button
            style={{
              ...modePillStyle,
              background: compare ? "#1e293b" : "#f1f5f9",
              color: compare ? "#fff" : "#475569",
              borderColor: compare ? "#1e293b" : "#e2e8f0",
            }}
            onClick={() => setCompare((v) => !v)}
          >
            ⚖ Compare
          </button>
        </div>
        <ModelSelector
          value={model}
          onChange={(id) => { setModel(id); clearMessages(); }}
        />
        {viewingHistory && (
          <button
            style={{ ...historyBtnStyle, background: "#1e293b", color: "#fff", borderColor: "#1e293b" }}
            onClick={() => { clearMessages(); }}
          >
            + New chat
          </button>
        )}
        <button style={historyBtnStyle} onClick={() => setShowHistory(true)}>History</button>
      </header>

      {showHistory && (
        <HistoryPanel
          onSelect={(item) => { loadConversation(item); setShowHistory(false); }}
          onClose={() => setShowHistory(false)}
        />
      )}

      {viewingHistory && (
        <div style={bannerStyle}>
          <span>ℹ️ This data may have changed since the last time you had a chat.</span>
          <button style={bannerCloseStyle} onClick={dismissHistoryBanner}>✕</button>
        </div>
      )}

      {compare ? (
        <CompareView model={model} />
      ) : (
        <>
          <div style={threadStyle}>
            {messages.length === 0 && (
              <div style={emptyStyle}>
                Ask a data question to get started.
              </div>
            )}
            {messages.map((msg) => (
              <ChatMessage key={msg.id} msg={msg} />
            ))}
            <div ref={bottomRef} />
          </div>

          <form onSubmit={handleSubmit} style={formStyle}>
            <input
              style={inputStyle}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask a question…"
              disabled={loading}
            />
            <button type="submit" style={btnStyle} disabled={loading || !input.trim()}>
              Send
            </button>
          </form>
        </>
      )}

      <style>{`
        @keyframes bounce {
          0%, 80%, 100% { transform: scale(0.8); opacity: 0.5; }
          40% { transform: scale(1.2); opacity: 1; }
        }
        div[style*="padding: 12px 20px"]:hover {
          background: #f8fafc;
        }
      `}</style>
    </div>
  );
}

const appStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  height: "100dvh",
  background: "#f1f5f9",
  fontFamily: "'Inter', system-ui, sans-serif",
};

const headerStyle: React.CSSProperties = {
  padding: "14px 20px",
  background: "#ffffff",
  borderBottom: "1px solid #e2e8f0",
  display: "flex",
  alignItems: "center",
  gap: 12,
};

const logoStyle: React.CSSProperties = {
  fontWeight: 700,
  fontSize: 16,
  color: "#1e293b",
};

const modeBarStyle: React.CSSProperties = {
  display: "flex",
  gap: 6,
  marginLeft: 16,
};

const modePillStyle: React.CSSProperties = {
  padding: "5px 12px",
  borderRadius: 20,
  border: "1px solid",
  fontSize: 12,
  fontWeight: 600,
  cursor: "pointer",
  transition: "all 0.15s",
};

const historyBtnStyle: React.CSSProperties = {
  marginLeft: "auto",
  padding: "6px 14px",
  borderRadius: 6,
  border: "1px solid #e2e8f0",
  background: "#f8fafc",
  color: "#475569",
  fontSize: 13,
  fontWeight: 500,
  cursor: "pointer",
};

const bannerStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 12,
  padding: "10px 20px",
  background: "#eff6ff",
  borderBottom: "1px solid #bfdbfe",
  color: "#1e40af",
  fontSize: 13,
};

const bannerCloseStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "#1e40af",
  fontSize: 14,
  cursor: "pointer",
  lineHeight: 1,
};

const threadStyle: React.CSSProperties = {
  flex: 1,
  overflowY: "auto",
  padding: "16px 0",
  display: "flex",
  flexDirection: "column",
  gap: 4,
};

const emptyStyle: React.CSSProperties = {
  textAlign: "center",
  color: "#94a3b8",
  fontSize: 14,
  marginTop: 60,
};

const formStyle: React.CSSProperties = {
  display: "flex",
  gap: 8,
  padding: "12px 20px",
  background: "#ffffff",
  borderTop: "1px solid #e2e8f0",
};

const inputStyle: React.CSSProperties = {
  flex: 1,
  padding: "10px 14px",
  border: "1px solid #e2e8f0",
  borderRadius: 8,
  fontSize: 14,
  outline: "none",
  background: "#f8fafc",
  color: "#1e293b",
};

const btnStyle: React.CSSProperties = {
  padding: "10px 20px",
  borderRadius: 8,
  border: "none",
  background: "#1e293b",
  color: "#ffffff",
  fontWeight: 600,
  fontSize: 14,
  cursor: "pointer",
};
