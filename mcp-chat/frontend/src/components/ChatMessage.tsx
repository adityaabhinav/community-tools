import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Message, ThinkingStep } from "../hooks/useChat";
import { ChartBlock } from "./ChartBlock";

export function ChatMessage({ msg }: { msg: Message }) {
  // One collapsible for the whole reasoning block (step headers + their text),
  // like Spotter embed: auto-expanded while thinking, auto-collapsed once done,
  // and the user can toggle it either way.
  const [workManual, setWorkManual] = useState<boolean | null>(null);
  const workOpen = workManual !== null ? workManual : !!msg.streaming;
  const toggleWork = () => setWorkManual(!workOpen);

  // Live charts auto-open the most recent one when the answer finishes.
  // History charts stay collapsed to avoid rendering many iframes at once.
  const lastChartIndex = (msg.blocks ?? []).reduce(
    (acc, b, i) => (b.kind === "chart" ? i : acc),
    -1
  );

  if (msg.role === "user") {
    return (
      <div style={userRowStyle}>
        <div style={userBubbleStyle}>{msg.text}</div>
      </div>
    );
  }

  const steps = msg.thinkingSteps ?? [];

  return (
    <div style={botRowStyle}>
      <div style={botBubbleStyle}>
        {/* Thinking steps — persistent list; last one is active while streaming */}
        {steps.length > 0 && (
          <div style={stepsWrapStyle}>
            <button style={showWorkToggleStyle} onClick={toggleWork}>
              <span style={chevronStyle(workOpen)}>›</span>{" "}
              {workOpen ? "Hide work" : `Show work · ${steps.length} steps`}
            </button>
            {workOpen &&
              steps.map((s, i) => (
                <StepRow key={i} step={s} active={!!msg.streaming && i === steps.length - 1} open />
              ))}
          </div>
        )}

        {/* Show work — only for history-loaded messages; live uses per-step reasoning above */}
        {steps.length === 0 && msg.thinkingText && (
          <div style={showWorkWrapStyle}>
            <button style={showWorkToggleStyle} onClick={toggleWork}>
              <span style={chevronStyle(workOpen)}>›</span> {workOpen ? "Hide work" : "Show work"}
            </button>
            {workOpen && (
              <div style={showWorkBodyStyle}>
                {parseThinkingSegments(msg.thinkingText).map((seg, i) =>
                  seg.type === "json" ? (
                    <div key={i} style={jsonBlockStyle}>
                      <div style={jsonBlockLabelStyle}>Dataset context</div>
                      <pre style={jsonBlockPreStyle}>{seg.text}</pre>
                    </div>
                  ) : (
                    <div key={i} style={showWorkMdStyle}>
                      <Markdown remarkPlugins={[remarkGfm]}>{seg.text}</Markdown>
                    </div>
                  )
                )}
              </div>
            )}
          </div>
        )}

        {/* Inline content blocks — text and charts interleaved */}
        {msg.blocks && msg.blocks.length > 0 && (
          <>
            {msg.blocks.map((block, i) =>
              block.kind === "text" ? (
                <div key={i} style={mdStyle}>
                  <Markdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                    {block.text}
                  </Markdown>
                </div>
              ) : (
                <ChartBlock
                  key={i}
                  block={block}
                  fromHistory={msg.fromHistory}
                  defaultOpen={!msg.fromHistory && i === lastChartIndex}
                />
              )
            )}
          </>
        )}

        {/* Loading dots when no content yet */}
        {(!msg.blocks || msg.blocks.length === 0) && steps.length === 0 && msg.streaming && (
          <div style={loadingStyle}>
            <span style={dotStyle(0)} />
            <span style={dotStyle(1)} />
            <span style={dotStyle(2)} />
          </div>
        )}
      </div>
    </div>
  );
}

// One reasoning step: heading (with spinner/check) + its own collapsible text,
// like the Spotter UI shows each step. Active step is expanded while streaming.
// Heading is always visible (live progress); its reasoning text shows only when
// the parent "Show work" toggle (`open`) is on — collapsible like before, but
// keeping the per-step format.
function StepRow({ step, active, open }: { step: ThinkingStep; active: boolean; open: boolean }) {
  const hasText = step.text.trim().length > 0;
  return (
    <div style={stepBlockStyle}>
      <div style={stepHeadRowStyle}>
        {active ? <span style={spinnerStyle} /> : <span style={stepCheckStyle}>✓</span>}
        <span
          style={{
            ...stepTextStyle,
            color: active ? "#334155" : "#64748b",
            fontStyle: active ? "italic" : "normal",
          }}
        >
          {step.heading}
        </span>
      </div>
      {hasText && open && (
        <div style={stepBodyStyle}>
          {parseThinkingSegments(step.text).map((seg, i) =>
            seg.type === "json" ? (
              <div key={i} style={jsonBlockStyle}>
                <div style={jsonBlockLabelStyle}>Dataset context</div>
                <pre style={jsonBlockPreStyle}>{seg.text}</pre>
              </div>
            ) : (
              <div key={i} style={showWorkMdStyle}>
                <Markdown remarkPlugins={[remarkGfm]}>{seg.text}</Markdown>
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
}

// ── Styles ─────────────────────────────────────────────────────────────────────

const userRowStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "flex-end",
  padding: "6px 20px",
};

const userBubbleStyle: React.CSSProperties = {
  background: "#1e293b",
  color: "#fff",
  borderRadius: "18px 18px 4px 18px",
  padding: "10px 16px",
  maxWidth: "70%",
  fontSize: 14,
  lineHeight: 1.5,
};

const botRowStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  padding: "6px 20px",
  gap: 12,
};

const botBubbleStyle: React.CSSProperties = {
  background: "#ffffff",
  border: "1px solid #e2e8f0",
  borderRadius: "4px 18px 18px 18px",
  padding: "14px 18px",
  maxWidth: "80%",
  fontSize: 14,
  lineHeight: 1.6,
  alignSelf: "flex-start",
};

const thinkingRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 8,
  marginBottom: 6,
};

const spinnerStyle: React.CSSProperties = {
  display: "inline-block",
  width: 12,
  height: 12,
  border: "2px solid #e2e8f0",
  borderTopColor: "#64748b",
  borderRadius: "50%",
  animation: "spin 0.8s linear infinite",
};

const thinkingLabelStyle: React.CSSProperties = {
  fontSize: 12,
  color: "#64748b",
  fontStyle: "italic",
};

const showWorkWrapStyle: React.CSSProperties = { marginBottom: 8 };

const showWorkToggleStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  padding: "2px 0",
  fontSize: 12,
  color: "#64748b",
  cursor: "pointer",
  display: "flex",
  alignItems: "center",
  gap: 4,
};

const chevronStyle = (open: boolean): React.CSSProperties => ({
  display: "inline-block",
  transition: "transform 0.15s",
  transform: open ? "rotate(90deg)" : "rotate(0deg)",
  fontSize: 14,
});

const showWorkBodyStyle: React.CSSProperties = {
  marginTop: 6,
  background: "#f8fafc",
  borderRadius: 6,
  padding: "8px 12px",
  border: "1px solid #e2e8f0",
};

const showWorkPreStyle: React.CSSProperties = {
  margin: 0,
  fontSize: 11,
  color: "#475569",
  whiteSpace: "pre-wrap",
  fontFamily: "monospace",
};

const stepsWrapStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 3,
  marginBottom: 8,
};

const stepRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 7,
};

const stepCheckStyle: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  width: 12,
  height: 12,
  fontSize: 9,
  color: "#22c55e",
  flexShrink: 0,
};

const stepTextStyle: React.CSSProperties = { fontSize: 12 };

const stepBlockStyle: React.CSSProperties = { display: "flex", flexDirection: "column" };

const stepHeadRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 7,
};

const stepChevronStyle: React.CSSProperties = {
  marginLeft: 4,
  fontSize: 13,
  color: "#cbd5e1",
  transition: "transform 0.15s",
  display: "inline-block",
};

const stepBodyStyle: React.CSSProperties = {
  margin: "3px 0 4px 19px",
  paddingLeft: 10,
  borderLeft: "2px solid #e2e8f0",
};

const showWorkMdStyle: React.CSSProperties = {
  fontSize: 11.5,
  color: "#475569",
  lineHeight: 1.5,
};

const textStyle: React.CSSProperties = {
  margin: 0,
  color: "#1e293b",
  whiteSpace: "pre-wrap",
};

// Markdown rendering for answer text — GFM tables, bold, lists, code.
const mdStyle: React.CSSProperties = {
  color: "#1e293b",
  fontSize: 14,
  lineHeight: 1.5,
  overflowX: "auto",
};

const mdTableStyle: React.CSSProperties = {
  borderCollapse: "collapse",
  margin: "8px 0",
  fontSize: 13,
  width: "auto",
};

const mdThStyle: React.CSSProperties = {
  border: "1px solid #e2e8f0",
  background: "#f8fafc",
  padding: "6px 10px",
  textAlign: "left",
  fontWeight: 600,
  whiteSpace: "nowrap",
};

const mdTdStyle: React.CSSProperties = {
  border: "1px solid #e2e8f0",
  padding: "6px 10px",
  textAlign: "left",
};

const mdComponents = {
  p: (props: any) => <p style={{ margin: "6px 0" }} {...props} />,
  table: (props: any) => (
    <div style={{ overflowX: "auto" }}>
      <table style={mdTableStyle} {...props} />
    </div>
  ),
  th: (props: any) => <th style={mdThStyle} {...props} />,
  td: (props: any) => <td style={mdTdStyle} {...props} />,
  ul: (props: any) => <ul style={{ margin: "6px 0", paddingLeft: 20 }} {...props} />,
  ol: (props: any) => <ol style={{ margin: "6px 0", paddingLeft: 20 }} {...props} />,
  code: (props: any) => (
    <code style={{ background: "#f1f5f9", padding: "1px 5px", borderRadius: 4, fontSize: 12.5 }} {...props} />
  ),
};

const loadingStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 4,
  minHeight: 24,
};

function dotStyle(i: number): React.CSSProperties {
  return {
    display: "inline-block",
    width: 7,
    height: 7,
    borderRadius: "50%",
    background: "#94a3b8",
    animation: `bounce 1.2s ${i * 0.2}s ease-in-out infinite`,
  };
}

// ── Thinking text parser ────────────────────────────────────────────────────────

type ThinkingSegment = { type: "text" | "json"; text: string };

function parseThinkingSegments(raw: string): ThinkingSegment[] {
  const segments: ThinkingSegment[] = [];
  const regex = /```(?:json)?\n([\s\S]*?)```/g;
  let last = 0;
  let match;
  while ((match = regex.exec(raw)) !== null) {
    if (match.index > last) {
      const text = raw.slice(last, match.index).trim();
      if (text) segments.push({ type: "text", text });
    }
    try {
      const parsed = JSON.parse(match[1]);
      segments.push({ type: "json", text: JSON.stringify(parsed, null, 2) });
    } catch {
      segments.push({ type: "json", text: match[1] });
    }
    last = match.index + match[0].length;
  }
  const tail = raw.slice(last).trim();
  if (tail) segments.push({ type: "text", text: tail });
  return segments;
}

const jsonBlockStyle: React.CSSProperties = {
  margin: "8px 0",
  background: "#0f172a",
  borderRadius: 6,
  border: "1px solid #334155",
  overflow: "hidden",
};

const jsonBlockLabelStyle: React.CSSProperties = {
  padding: "4px 10px",
  fontSize: 10,
  fontWeight: 600,
  color: "#94a3b8",
  background: "#1e293b",
  letterSpacing: "0.05em",
  textTransform: "uppercase",
};

const jsonBlockPreStyle: React.CSSProperties = {
  margin: 0,
  padding: "10px 12px",
  fontSize: 11,
  color: "#7dd3fc",
  whiteSpace: "pre-wrap",
  fontFamily: "monospace",
  maxHeight: 220,
  overflowY: "auto",
};

