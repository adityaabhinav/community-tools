# Spotter MCP POC

A chat interface for ThoughtSpot Spotter. Streams Spotter's reasoning steps, answer text, and interactive charts to the browser in real time, and lets you revisit past conversations with the charts rebuilt on demand.

Three integration modes are available in the UI:

- **Direct API** — ThoughtSpot's REST agent-conversation streaming endpoint (`/ai/agent/conversation/{id}/send/stream`).
- **Direct MCP** — the ThoughtSpot MCP server (`agent.thoughtspot.app/token/mcp`) over JSON-RPC.
- **Claude + MCP** — Claude orchestrating the ThoughtSpot MCP tools (requires an Anthropic API key).

---

## Prerequisites

- Python 3.9+
- Node 18+
- A ThoughtSpot cluster on **26.7+** with Spotter enabled (chat-history APIs require 26.7)
- Your app origin allowlisted in the cluster's CORS + CSP visual-embed hosts (needed for the chart iframe to render)

---

## Setup

### 1. Environment variables

Copy `.env.example` to `.env` at the project root and fill in your values:

```bash
cp .env.example .env
```

```
TS_HOST=https://your-cluster.thoughtspot.cloud
TS_USERNAME=your.name@thoughtspot.com
TS_PASSWORD=your_password
TS_WORKSHEET_ID=your_worksheet_uuid
ANTHROPIC_API_KEY=sk-ant-...     # required for "Claude + MCP" mode only
TS_ORG_ID=                       # optional — numeric org id for multi-org clusters
TS_TOKEN=                        # optional — auto-fetched from credentials if blank
```

The app authenticates via **session cookie** (username + password). A bearer token is also needed for the ThoughtSpot MCP server and the Embed SDK iframe renderer — the backend fetches it automatically from `POST /api/rest/2.0/auth/token/full` using the same credentials, so you don't need to set `TS_TOKEN` manually. Set it only if you want to pin a specific token.

`TS_WORKSHEET_ID` is the default data source Spotter queries. You can also pick a model per-question in the UI, or choose **Auto** to let Spotter select the dataset.

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --port 8080
```

Backend runs at `http://localhost:8080`.

Refresh the token any time (bearer tokens expire):

```bash
curl -X POST http://localhost:8080/token/refresh
```

### 3. Frontend

In a new terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5184`. (The Vite dev server proxies `/chat`, `/models`, `/history`, `/token`, `/health` to the backend on `:8080`.)

---

## Token expiry

ThoughtSpot bearer tokens are short-lived. Handle it with either:

- **Auto-refresh** — set `TS_PASSWORD` or `TS_SECRET_KEY` in `.env`; the backend re-mints on expiry.
- **Manual** — `POST http://localhost:8080/token/refresh`, or `GET /health` to check status.

---

## How it works

**Live chat.** Each query streams to the browser over SSE. Depending on the mode, the backend either consumes ThoughtSpot's REST agent stream or drives the MCP tools (`initialize` → `create_analysis_session` → `send_session_message` → poll `get_session_updates`). Thinking steps, answer text, and charts appear inline as Spotter generates them. Each chart arrives as a session-scoped `conv-assist-answer` iframe URL, auto-wired by `startAutoMCPFrameRenderer`.

**Answer text is rendered as markdown** (`react-markdown` + `remark-gfm`) so GFM tables, bold, lists, and code render correctly.

**Step headings** arrive as `step_notification` events (`is_thinking: true`, heading text in `text`, e.g. *"Fetching dataset context…"*). Render each as its own progress step for the Spotter-UI-style "now doing X, now doing Y" experience. The POC maps them to distinct `thinking` step events — see `backend/services/ts_mcp_client.py`. (Released server-side; no client flag. A separate opt-in flag for the full internal tool-call detail is planned but off by default to avoid extra token cost.)

> **Streaming note (important for the MCP path):** `get_session_updates` **drains** — each poll returns only the *new* batch of updates since the previous call, **not** a cumulative list (its length rises and falls across polls, e.g. `13, 39, 5, 1, 18, 21`). So **process every item in each batch, in order.** Do **not** de-duplicate chunks by content (that drops legitimately-repeated tokens/whitespace and corrupts markdown — "missing characters"), and do **not** track a position offset across polls (the list resets between polls, so an offset misaligns and drops whole batches — cutting off the middle/end of the answer). See `backend/services/ts_mcp_client.py`.

## Compare view (parity test)

The **⚖ Compare** toggle (top bar) runs one question against **Direct API**, **Direct MCP**, and the native **Spotter Embed** simultaneously, side by side, with a response-latency timer on each column. Use it to eyeball parity across surfaces — step headings, answer text/formatting, charts, and speed. Pick a specific model (not Auto) so all three query the same dataset; on Auto, the Spotter Embed column falls back to `TS_WORKSHEET_ID`.

## Chart history persistence (26.7 native APIs)

The per-answer `iframe_url` is session-scoped and expires (~8h), so it can't be saved and replayed. Instead, only each answer's durable identity is stored and the chart is rebuilt on demand:

- Persist just the `conversation_id` (and `answer_id`s) — no answer content.
- To revisit a conversation, the backend calls **`getConversation`** for the transcript (prompts, reasoning, answer text) and **`loadAnswer`** (`.../answers/{answer_id}/details`) per answer to mint a fresh session, then builds a new `conv-assist-answer` iframe URL at view time.
- Live and history charts render through the **same** `conv-assist-answer` iframe path — no SearchEmbed, no Liveboard, no token re-resolution.

Because the 8h expiry applies to any rendered chart, a chart left idle past that window will show ThoughtSpot's "answer expired" frame; call `loadAnswer` again to re-render (the native Spotter UI behaves the same way — charts are re-rendered on demand, not persisted).
