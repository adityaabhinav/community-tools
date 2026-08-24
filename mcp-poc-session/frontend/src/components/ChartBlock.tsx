import { useState } from "react";
import { ContentBlock } from "../hooks/useChat";

/**
 * Renders a single chart block as a conv-assist-answer iframe.
 *
 * Live and history charts are now identical: both carry a `conv-assist-answer`
 * URL (live from the stream, history rebuilt server-side via loadAnswer), and
 * both are swapped for an auth-wired frame by startAutoMCPFrameRenderer (wired
 * in main.tsx). No SearchEmbed, no Liveboard, no token re-resolution.
 *
 * Charts sit behind a "Show chart" button; history charts default collapsed so
 * reopening a long conversation doesn't render every chart at once.
 */
export function ChartBlock({
  block,
  defaultOpen,
}: {
  block: ContentBlock;
  fromHistory?: boolean;
  defaultOpen?: boolean;
}) {
  // Follow the auto rule (only the latest chart expanded) reactively, until the
  // user manually toggles. Using useState(defaultOpen) alone would freeze the
  // mount-time value — so a chart that arrived as "latest" during streaming
  // (e.g. MCP's per-poll intermediate charts) would stay open when the next one
  // arrives. Deriving from defaultOpen keeps intermediates collapsed like the API.
  const [manualOpen, setManualOpen] = useState<boolean | null>(null);
  const open = manualOpen !== null ? manualOpen : !!defaultOpen;
  const [fullscreen, setFullscreen] = useState(false);
  const title = block.answerTitle || "Chart";

  if (!block.url) return null;

  return (
    <div style={wrapStyle}>
      <div style={headerRowStyle}>
        <button style={toggleStyle} onClick={() => setManualOpen(!open)}>
          <span style={chevronStyle(open)}>›</span>
          <span>📊 {open ? "Hide" : "Show"} chart</span>
          <span style={titleStyle}>· {title}</span>
        </button>
        {open && (
          <button style={expandStyle} onClick={() => setFullscreen(true)} title="Expand to full screen">
            ⤢
          </button>
        )}
      </div>

      {open && (
        <div style={chartWrapStyle}>
          <iframe src={block.url} style={iframeStyle} title="ThoughtSpot chart" />
        </div>
      )}

      {fullscreen && (
        <div style={modalOverlayStyle} onClick={() => setFullscreen(false)}>
          <div style={modalStyle} onClick={(e) => e.stopPropagation()}>
            <div style={modalHeaderStyle}>
              <span style={modalTitleStyle}>{title}</span>
              <button style={modalCloseStyle} onClick={() => setFullscreen(false)}>
                Close
              </button>
            </div>
            <div style={modalBodyStyle}>
              <iframe src={block.url} style={modalIframeStyle} title="ThoughtSpot chart (full screen)" />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Styles ─────────────────────────────────────────────────────────────────────

const wrapStyle: React.CSSProperties = { margin: "10px 0" };

const headerRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  marginBottom: 8,
};

const toggleStyle: React.CSSProperties = {
  background: "none",
  border: "1px solid #e2e8f0",
  borderRadius: 6,
  padding: "5px 12px",
  fontSize: 12,
  color: "#475569",
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  gap: 6,
};

const titleStyle: React.CSSProperties = { color: "#94a3b8", fontWeight: 500 };

const expandStyle: React.CSSProperties = {
  background: "#f8fafc",
  border: "1px solid #e2e8f0",
  borderRadius: 6,
  padding: "4px 10px",
  fontSize: 14,
  color: "#475569",
  cursor: "pointer",
  lineHeight: 1,
};

const chevronStyle = (open: boolean): React.CSSProperties => ({
  display: "inline-block",
  transition: "transform 0.15s",
  transform: open ? "rotate(90deg)" : "rotate(0deg)",
  fontSize: 14,
});

const chartWrapStyle: React.CSSProperties = {
  borderRadius: 12,
  overflow: "hidden",
  border: "1px solid #e2e8f0",
  background: "#fff",
  maxWidth: 900,
  minHeight: 560,
};

const iframeStyle: React.CSSProperties = {
  width: "100%",
  height: 600,
  border: "none",
  display: "block",
};

const modalOverlayStyle: React.CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(15,23,42,0.55)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
  padding: 24,
};

const modalStyle: React.CSSProperties = {
  background: "#fff",
  borderRadius: 12,
  width: "100%",
  height: "100%",
  maxWidth: 1400,
  display: "flex",
  flexDirection: "column",
  overflow: "hidden",
};

const modalHeaderStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "14px 20px",
  borderBottom: "1px solid #e2e8f0",
};

const modalTitleStyle: React.CSSProperties = { fontWeight: 700, fontSize: 16, color: "#1e293b" };

const modalCloseStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "#2563eb",
  fontSize: 14,
  fontWeight: 600,
  cursor: "pointer",
};

const modalBodyStyle: React.CSSProperties = { flex: 1, minHeight: 0 };

const modalIframeStyle: React.CSSProperties = {
  width: "100%",
  height: "100%",
  border: "none",
  display: "block",
};
