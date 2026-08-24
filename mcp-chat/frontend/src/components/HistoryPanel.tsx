import { useEffect, useState } from "react";
import { HistoryItem } from "../hooks/useChat";

interface Props {
  onSelect: (item: HistoryItem) => void;
  onClose: () => void;
}

export function HistoryPanel({ onSelect, onClose }: Props) {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  useEffect(() => {
    fetch("/history")
      .then((r) => r.json())
      .then((d) => setItems(d.items ?? []))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={panelStyle} onClick={(e) => e.stopPropagation()}>
        <div style={panelHeaderStyle}>
          <span style={{ fontWeight: 600, fontSize: 15, color: "#1e293b" }}>History</span>
          <button style={closeBtnStyle} onClick={onClose}>✕</button>
        </div>

        {loading && <div style={emptyStyle}>Loading…</div>}
        {!loading && items.length === 0 && (
          <div style={emptyStyle}>No history yet.</div>
        )}

        <div style={listStyle}>
          {items.map((item) => (
            <div
              key={item.id}
              style={{
                ...itemStyle,
                background: hoveredId === item.id ? "#f8fafc" : "#fff",
              }}
              onClick={() => onSelect(item)}
              onMouseEnter={() => setHoveredId(item.id)}
              onMouseLeave={() => setHoveredId(null)}
            >
              <div style={itemTopStyle}>
                <span style={badgeStyle(item.source)}>ThoughtSpot</span>
                {item.turn_count && item.turn_count > 1 && (
                  <span style={turnCountStyle}>{item.turn_count} messages</span>
                )}
                <span style={timeStyle}>
                  {new Date(item.created_at).toLocaleString()}
                </span>
              </div>
              <div style={queryStyle}>{item.query}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

const overlayStyle: React.CSSProperties = {
  position: "fixed", inset: 0,
  background: "rgba(0,0,0,0.3)",
  zIndex: 100,
  display: "flex",
  justifyContent: "flex-end",
};

const panelStyle: React.CSSProperties = {
  width: 380,
  height: "100%",
  background: "#fff",
  display: "flex",
  flexDirection: "column",
  boxShadow: "-4px 0 20px rgba(0,0,0,0.12)",
};

const panelHeaderStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "16px 20px",
  borderBottom: "1px solid #e2e8f0",
};

const closeBtnStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  fontSize: 16,
  cursor: "pointer",
  color: "#94a3b8",
};

const listStyle: React.CSSProperties = {
  flex: 1,
  overflowY: "auto",
  padding: "8px 0",
};

const itemStyle: React.CSSProperties = {
  padding: "12px 20px",
  borderBottom: "1px solid #f1f5f9",
  cursor: "pointer",
  transition: "background 0.1s",
};

const itemTopStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  marginBottom: 4,
};

const queryStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: "#1e293b",
  marginBottom: 3,
};

const snippetStyle: React.CSSProperties = {
  fontSize: 12,
  color: "#64748b",
  lineHeight: 1.4,
};

const timeStyle: React.CSSProperties = {
  fontSize: 11,
  color: "#94a3b8",
  marginLeft: "auto",
};

const emptyStyle: React.CSSProperties = {
  textAlign: "center",
  color: "#94a3b8",
  fontSize: 13,
  padding: 32,
};

const badgeStyle = (source: string): React.CSSProperties => ({
  fontSize: 10,
  fontWeight: 600,
  padding: "2px 6px",
  borderRadius: 4,
  background: source === "thoughtspot" ? "#dbeafe" : "#f0fdf4",
  color: source === "thoughtspot" ? "#1d4ed8" : "#15803d",
});

const turnCountStyle: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 500,
  padding: "2px 6px",
  borderRadius: 4,
  background: "#f1f5f9",
  color: "#64748b",
};
