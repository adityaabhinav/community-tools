"""
Direct client for the ThoughtSpot MCP server (agent.thoughtspot.app/token/mcp).

MCP over HTTP is JSON-RPC 2.0 — no SDK needed.
We implement only what we need:
  - initialize (handshake)
  - tools/call: CreateAnalysisSession
  - tools/call: SendSessionMessage
  - tools/call: GetSessionUpdates (polled until is_done)

This lets us stream thinking steps to the frontend via SSE while using
the REAL ThoughtSpot MCP server, not our DIY REST API calls.
"""

import os
import json
import asyncio
import logging
from typing import AsyncGenerator, Optional
import httpx

from services.token_manager import get_token

logger = logging.getLogger(__name__)

TS_HOST = os.getenv("TS_HOST", "")
TS_WORKSHEET_ID = os.getenv("TS_WORKSHEET_ID", "")
MCP_URL = "https://agent.thoughtspot.app/token/mcp"


def _ts_domain() -> str:
    return TS_HOST.replace("https://", "").replace("http://", "").rstrip("/")


def _auth_header() -> dict:
    return {"Authorization": f"Bearer {get_token()}@{_ts_domain()}"}


def _rpc(method: str, params: dict, req_id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}


async def _call(client: httpx.AsyncClient, method: str, params: dict, req_id: int = 1, session_id: Optional[str] = None) -> dict:
    """Send a JSON-RPC request and return the result."""
    body = _rpc(method, params, req_id)
    headers = {**_auth_header(), "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session_id:
        headers["mcp-session-id"] = session_id
    resp = await client.post(MCP_URL, json=body, headers=headers, timeout=30)
    if resp.status_code >= 400:
        logger.error(f"MCP {method} HTTP {resp.status_code}: {resp.text[:500]}")
    resp.raise_for_status()

    # Response may be plain JSON or SSE — handle both
    content_type = resp.headers.get("content-type", "")
    if "text/event-stream" in content_type:
        # Parse SSE and extract the first data line
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                raw = line[5:].strip()
                if raw and raw != "[DONE]":
                    parsed = json.loads(raw)
                    if "result" in parsed:
                        return parsed["result"]
                    if "error" in parsed:
                        raise RuntimeError(f"MCP error: {parsed['error']}")
        return {}
    else:
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"MCP error: {data['error']}")
        return data.get("result", {})


def _parse_tool_result(result: dict) -> dict:
    """Extract JSON from MCP tool result content."""
    for item in result.get("content", []):
        if item.get("type") == "text":
            try:
                return json.loads(item["text"])
            except json.JSONDecodeError:
                return {"raw": item["text"]}
    return {}


async def run_query_stream(
    question: str,
    conversation_id: Optional[str] = None,
    data_source_id: Optional[str] = None,
) -> AsyncGenerator[dict, None]:
    """
    Call ThoughtSpot MCP server tools and yield normalized events:
      {"type": "thinking",      "text": "<step label>"}
      {"type": "thinking_text", "text": "<reasoning text>"}
      {"type": "token",         "text": "<final answer chunk>"}
      {"type": "done",          "iframe_url": "...", "conversation_id": "..."}
    """
    async with httpx.AsyncClient(timeout=120) as client:
        mcp_session_id: Optional[str] = None

        # ── Initialize MCP session ─────────────────────────────────────────
        try:
            init_body = _rpc("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "spotter-mcp-poc", "version": "1.0"},
            }, req_id=1)
            init_resp = await client.post(
                MCP_URL,
                json=init_body,
                headers={**_auth_header(), "Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
                timeout=30,
            )
            init_resp.raise_for_status()
            mcp_session_id = init_resp.headers.get("mcp-session-id")
            logger.info(f"[MCP] mcp-session-id={mcp_session_id}")
        except Exception as e:
            logger.warning(f"MCP initialize failed: {e}")

        req = 2

        # ── CreateAnalysisSession ──────────────────────────────────────────
        if conversation_id:
            analytical_session_id = conversation_id
        else:
            yield {"type": "thinking", "text": "Creating ThoughtSpot session…"}
            result = await _call(client, "tools/call", {
                "name": "create_analysis_session",
                # "auto" => omit data_source_id so the agent auto-selects the source.
                "arguments": ({} if data_source_id == "auto"
                              else {"data_source_id": data_source_id or TS_WORKSHEET_ID}),
            }, req_id=req, session_id=mcp_session_id)
            req += 1
            data = _parse_tool_result(result)
            analytical_session_id = data.get("analytical_session_id", "")
            if not analytical_session_id:
                yield {"type": "done", "iframe_url": None, "conversation_id": None}
                return
            logger.info(f"[MCP] analytical_session_id={analytical_session_id}")

        yield {"type": "thinking", "text": "Sending question to ThoughtSpot…"}

        # ── SendSessionMessage ─────────────────────────────────────────────
        await _call(client, "tools/call", {
            "name": "send_session_message",
            "arguments": {
                "analytical_session_id": analytical_session_id,
                "message": question,
            },
        }, req_id=req, session_id=mcp_session_id)
        req += 1

        # ── Poll GetSessionUpdates ─────────────────────────────────────────
        iframe_url: Optional[str] = None
        answer_text: list[str] = []
        is_done = False
        poll_count = 0
        max_polls = 60  # 60 × 2s = 2 min max

        while not is_done and poll_count < max_polls:
            await asyncio.sleep(2)
            poll_count += 1

            result = await _call(client, "tools/call", {
                "name": "get_session_updates",
                "arguments": {"analytical_session_id": analytical_session_id},
            }, req_id=req, session_id=mcp_session_id)
            req += 1

            data = _parse_tool_result(result)
            is_done = data.get("is_done", False)

            # get_session_updates DRAINS: each poll returns only the NEW updates
            # since the previous call. The list is NOT cumulative — its length
            # rises AND falls across polls (observed e.g. 13, 39, 5, 1, 18, 21)
            # as batches drain. So process EVERY item in each batch, in order:
            #   - do NOT dedup by content — that drops legitimately repeated
            #     tokens/whitespace and corrupts markdown ("missing characters");
            #   - do NOT track a position offset — the list resets between polls,
            #     so an offset misaligns and drops whole batches (e.g. the middle
            #     rows of a table, cutting off the final text).
            for msg in data.get("session_updates", []):
                mtype = msg.get("type", "")
                is_thinking = msg.get("is_thinking", False)

                if mtype == "step_notification":
                    # Discrete step heading, e.g. "Fetching dataset context…".
                    # Surface it as its own step so the UI shows Spotter-style
                    # progress (frequent, labelled steps) instead of one blob —
                    # this is what gives perceived-latency parity with the
                    # Spotter UI. (`step_notification` events carry the heading
                    # in `text`; released server-side, no client flag needed.)
                    yield {"type": "thinking", "text": msg.get("text", "")}

                elif mtype in ("text", "text_chunk"):
                    text = msg.get("text", "")
                    if is_thinking:
                        yield {"type": "thinking_text", "text": text}
                    else:
                        answer_text.append(text)
                        yield {"type": "token", "text": text}

                elif mtype == "answer":
                    url = msg.get("iframe_url")
                    # answer_data_source_id + answer_query are what let us
                    # re-render this chart later via SearchEmbed once the
                    # session-scoped iframe_url has expired (8h). Surface them
                    # so the frontend can persist them with the turn.
                    if url:
                        iframe_url = url  # track last for done event
                        logger.info(f"[MCP] iframe_url={url}")
                    yield {
                        "type": "frame_url",
                        "frame_url": url,
                        "data_source_id": msg.get("answer_data_source_id"),
                        "answer_query": msg.get("answer_query"),
                        "answer_id": msg.get("answer_id"),
                        "answer_title": msg.get("answer_title"),
                    }

            if is_done:
                break

        yield {
            "type": "done",
            "iframe_url": iframe_url,
            "conversation_id": analytical_session_id,
        }
