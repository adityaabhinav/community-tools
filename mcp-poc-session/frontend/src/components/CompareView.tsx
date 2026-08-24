import { memo, useCallback, useEffect, useRef, useState } from "react";
import { SpotterEmbed } from "@thoughtspot/visual-embed-sdk/react";
import { useChat } from "../hooks/useChat";
import { ChatMessage } from "./ChatMessage";

// SpotterEmbed needs a concrete data source (it can't do "auto"). When the
// model selector is on Auto, fall back to VITE_TS_WORKSHEET_ID (set from
// TS_WORKSHEET_ID in .env). If neither is set, the Spotter column prompts to
// pick a specific model.
const DEFAULT_WS = (import.meta.env.VITE_TS_WORKSHEET_ID as string) || "";

// Isolated + memoized so the parent's 100ms timer re-renders never reach the
// embed. Without this, each re-render hands SpotterEmbed fresh searchOptions/
// frameParams object refs and it re-initializes → the query fires more than
// once. It only re-mounts when runId/query/wsId change (i.e. a new submit).
const SpotterPane = memo(function SpotterPane({
  runId, query, wsId, onData,
}: {
  runId: number; query: string; wsId: string; onData: () => void;
}) {
  return (
    <div className="spotter-fill" style={{ flex: 1, minHeight: 0, display: "flex" }}>
      <SpotterEmbed
        key={runId}
        worksheetId={wsId}
        searchOptions={{ searchQuery: query }}
        frameParams={{ width: "100%", height: "100%" }}
        onData={onData}
      />
    </div>
  );
});

type Elapsed = { api: number | null; mcp: number | null; spotter: number | null };
const BLANK: Elapsed = { api: null, mcp: null, spotter: null };

/**
 * Side-by-side parity test: one query fired at the same instant to Direct API,
 * Direct MCP, and the native Spotter Embed, with a response-latency timer on
 * each column so you can compare thinking steps, formatting, charts, and speed.
 */
export function CompareView({ model }: { model?: string }) {
  const api = useChat("api", model);
  const mcp = useChat("mcp", model);
  const [input, setInput] = useState("");
  const [spotterQuery, setSpotterQuery] = useState("");
  const [runId, setRunId] = useState(0);

  const [startAt, setStartAt] = useState(0);
  const [elapsed, setElapsed] = useState<Elapsed>(BLANK);
  const [now, setNow] = useState(0);
  const startAtRef = useRef(0);

  // Stable callback (deps []) so SpotterPane's memo isn't broken every render.
  const onSpotterData = useCallback(() => {
    const s = startAtRef.current;
    setElapsed((e) => (e.spotter === null && s ? { ...e, spotter: performance.now() - s } : e));
  }, []);

  const busy = api.loading || mcp.loading;
  const wsId = model && model !== "auto" ? model : DEFAULT_WS;
  // Live tick runs only while our two streams are pending. The Spotter Embed is
  // a cross-origin iframe we can't time precisely; its timer stops on the embed's
  // onData event if it fires, otherwise it freezes when API+MCP finish (shown
  // with a "~" to signal best-effort), rather than counting forever.
  const running = startAt > 0 && (elapsed.api === null || elapsed.mcp === null);

  // live tick while anything is still running
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setNow(performance.now()), 100);
    return () => clearInterval(id);
  }, [running]);

  // stop the API / MCP timers when their last answer finishes streaming
  useEffect(() => {
    const last = api.messages[api.messages.length - 1];
    if (startAt && last?.streamingDone && elapsed.api === null)
      setElapsed((e) => ({ ...e, api: performance.now() - startAt }));
  }, [api.messages, startAt, elapsed.api]);

  useEffect(() => {
    const last = mcp.messages[mcp.messages.length - 1];
    if (startAt && last?.streamingDone && elapsed.mcp === null)
      setElapsed((e) => ({ ...e, mcp: performance.now() - startAt }));
  }, [mcp.messages, startAt, elapsed.mcp]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = input.trim();
    if (!q || busy) return;
    setInput("");
    const t0 = performance.now();
    startAtRef.current = t0;
    setStartAt(t0);
    setNow(t0);
    setElapsed(BLANK);
    // fire all three at the same moment
    api.sendMessage(q);
    mcp.sendMessage(q);
    setSpotterQuery(q);
    setRunId((n) => n + 1); // remount SpotterEmbed so it re-runs the new query
  };

  const timer = (col: keyof Elapsed): string => {
    const v = elapsed[col];
    if (v !== null) return (v / 1000).toFixed(1) + "s";
    if (startAt) return ((now - startAt) / 1000).toFixed(1) + "s";
    return "—";
  };

  return (
    <div style={wrap}>
      <style>{`
        .spotter-fill > div { flex: 1; min-height: 0; display: flex; flex-direction: column; }
        .spotter-fill iframe { width: 100% !important; height: 100% !important; border: none; display: block; }
      `}</style>
      <form onSubmit={submit} style={formStyle}>
        <input
          style={inputStyle}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask once — runs on API, MCP, and Spotter Embed simultaneously…"
          disabled={busy}
        />
        <button type="submit" style={btn} disabled={busy || !input.trim()}>
          {busy ? "Running…" : "Run on all 3"}
        </button>
      </form>

      <div style={cols}>
        <Column title="Direct API" color="#0f766e" timer={timer("api")} pending={elapsed.api === null && startAt > 0}>
          {api.messages.length === 0 ? <Hint text="REST /send/stream" /> :
            api.messages.map((m) => <ChatMessage key={m.id} msg={m} />)}
        </Column>

        <Column title="Direct MCP" color="#204ec4" timer={timer("mcp")} pending={elapsed.mcp === null && startAt > 0}>
          {mcp.messages.length === 0 ? <Hint text="get_session_updates" /> :
            mcp.messages.map((m) => <ChatMessage key={m.id} msg={m} />)}
        </Column>

        <Column title="Spotter Embed" color="#7c3aed" timer={"~ " + timer("spotter")} pending={elapsed.spotter === null && startAt > 0} fill>
          {spotterQuery && wsId ? (
            <SpotterPane runId={runId} query={spotterQuery} wsId={wsId} onData={onSpotterData} />
          ) : spotterQuery && !wsId ? (
            <Hint text="Pick a specific model — Spotter Embed needs a data source" />
          ) : (
            <Hint text="Native Spotter chat renders here" />
          )}
        </Column>
      </div>
    </div>
  );
}

function Column({
  title, color, timer, pending, fill, children,
}: {
  title: string; color: string; timer?: string; pending?: boolean; fill?: boolean; children: React.ReactNode;
}) {
  return (
    <div style={colStyle}>
      <div style={{ ...colHeadStyle, color }}>
        <span style={{ ...dot, background: color }} /> {title}
        {timer !== undefined && (
          <span style={{ ...timerStyle, color: pending ? "#94a3b8" : "#0f172a", background: pending ? "#f1f5f9" : "#e2e8f0" }}>
            {timer}
          </span>
        )}
      </div>
      <div style={fill ? colBodyFillStyle : colBodyStyle}>{children}</div>
    </div>
  );
}

const Hint = ({ text }: { text: string }) => <div style={hint}>{text}</div>;

// ── styles ──────────────────────────────────────────────────────────────────
const wrap: React.CSSProperties = { display: "flex", flexDirection: "column", flex: 1, minHeight: 0 };

const formStyle: React.CSSProperties = {
  display: "flex", gap: 8, padding: "12px 20px",
  background: "#ffffff", borderBottom: "1px solid #e2e8f0",
};
const inputStyle: React.CSSProperties = {
  flex: 1, padding: "10px 14px", border: "1px solid #e2e8f0", borderRadius: 8,
  fontSize: 14, outline: "none", background: "#f8fafc", color: "#1e293b",
};
const btn: React.CSSProperties = {
  padding: "10px 20px", borderRadius: 8, border: "none",
  background: "#1e293b", color: "#fff", fontWeight: 600, fontSize: 14, cursor: "pointer",
};

const cols: React.CSSProperties = {
  flex: 1, display: "flex", gap: 1, minHeight: 0, background: "#e2e8f0", overflowX: "auto",
};
const colStyle: React.CSSProperties = {
  flex: 1, minWidth: 380, display: "flex", flexDirection: "column", background: "#f8fafc", minHeight: 0,
};
const colHeadStyle: React.CSSProperties = {
  display: "flex", alignItems: "center", gap: 8, padding: "10px 16px",
  fontWeight: 700, fontSize: 13, background: "#fff", borderBottom: "1px solid #e2e8f0",
};
const dot: React.CSSProperties = { width: 8, height: 8, borderRadius: "50%", display: "inline-block" };
const timerStyle: React.CSSProperties = {
  marginLeft: "auto", fontSize: 12, fontWeight: 700, fontVariantNumeric: "tabular-nums",
  padding: "2px 8px", borderRadius: 20,
};
const colBodyStyle: React.CSSProperties = { flex: 1, overflowY: "auto", padding: "8px 4px" };
const colBodyFillStyle: React.CSSProperties = { flex: 1, minHeight: 0, display: "flex", flexDirection: "column" };
const hint: React.CSSProperties = { color: "#94a3b8", fontSize: 12, textAlign: "center", marginTop: 40 };
