"""
ThoughtSpot tool — session-cookie auth + durable answer_id history fix.

Key changes vs original:
1. All HTTP calls use cookies (from token_manager.get_cookies()) instead of
   a Bearer token header.
2. During live chat, we store answer_id (durable) in content_blocks instead
   of frame_url (ephemeral session identity).
3. reconstruct_conversation() always calls /answers/{answer_id}/details to
   get a FRESH session identity at render time — so history charts never break.
"""

import os
import json
import httpx
import logging
from typing import Optional

from services.token_manager import get_cookies, login, refresh_token

logger = logging.getLogger(__name__)

TS_HOST          = os.getenv("TS_HOST")
TS_WORKSHEET_ID  = os.getenv("TS_WORKSHEET_ID")


def _cookies() -> dict:
    return get_cookies()


async def _ensure_session():
    if not _cookies():
        await login()


async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """GET with automatic session re-login on 401."""
    resp = await client.get(url, cookies=_cookies(), timeout=90)
    if resp.status_code == 401:
        logger.warning(f"401 on GET {url} — re-logging in")
        await login()
        resp = await client.get(url, cookies=_cookies(), timeout=90)
    return resp


async def _post(client: httpx.AsyncClient, url: str, json_body: dict) -> httpx.Response:
    """POST with automatic session re-login on 401."""
    resp = await client.post(url, json=json_body, cookies=_cookies(), timeout=90)
    if resp.status_code == 401:
        logger.warning(f"401 on POST {url} — re-logging in")
        await login()
        resp = await client.post(url, json=json_body, cookies=_cookies(), timeout=90)
    return resp


async def list_models() -> list[dict]:
    """Spotter-enabled worksheets for the model selector."""
    await _ensure_session()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await _post(client, f"{TS_HOST}/api/rest/2.0/metadata/search",
                        {"metadata": [{"type": "LOGICAL_TABLE"}], "record_size": 200})
        r.raise_for_status()
        models = []
        for it in r.json():
            h = it.get("metadata_header", {}) or {}
            name = h.get("name", "")
            if (h.get("type") == "WORKSHEET"
                    and not h.get("aiAnswerGenerationDisabled", False)
                    and "deprecated" not in name.lower()):
                models.append({"id": it.get("metadata_id"), "name": name})
        def rank(m):
            n = m["name"]
            return (n.startswith("TS:"), n.startswith("(Sample)"), n.lower())
        return sorted(models, key=rank)


async def _create_conversation(data_source_id: Optional[str] = None) -> str:
    await _ensure_session()
    url = f"{TS_HOST}/api/rest/2.0/ai/agent/conversation/create"
    if data_source_id == "auto":
        metadata_context = {"type": "AUTO_MODE"}
    else:
        metadata_context = {
            "type": "DATA_SOURCE",
            "data_source_context": {
                "data_source_identifier": data_source_id or TS_WORKSHEET_ID,
            },
        }
    payload = {
        "metadata_context": metadata_context,
        "conversation_settings": {
            "enable_contextual_change_analysis": True,
            "enable_natural_language_answer_generation": True,
            "enable_reasoning": True,
            "enable_save_chat": True,      # required for history to work
        },
    }
    async with httpx.AsyncClient() as client:
        resp = await _post(client, url, payload)
        resp.raise_for_status()
        return resp.json()["conversation_identifier"]


def build_frame_url(session_id, gen_no, txn_id, ac_gen_no) -> Optional[str]:
    """Construct conv-assist-answer embed URL from fresh session identity."""
    if not session_id or gen_no is None:
        return None
    return (
        f"{TS_HOST}/?tsmcp=true"
        f"#/embed/conv-assist-answer"
        f"?sessionId={session_id}&genNo={gen_no}"
        f"&acSessionId={txn_id}&acGenNo={ac_gen_no}"
    )


async def run_api_stream(question: str, conversation_id: Optional[str] = None,
                         data_source_id: Optional[str] = None):
    """
    Stream a Spotter answer. Yields normalized events:
      thinking / thinking_text / token / frame_url / done

    Crucially, the frame_url event now also carries answer_id so the caller
    can persist the durable ID instead of the ephemeral session identity.
    """
    await _ensure_session()
    conv_id = conversation_id or await _create_conversation(data_source_id)
    url = f"{TS_HOST}/api/rest/2.0/ai/agent/conversation/{conv_id}/send/stream"
    payload = {"messages": [question]}

    session_id = gen_no = txn_id = ac_gen_no = None
    current_answer_id = None

    headers = {"Accept": "text/event-stream", "Content-Type": "application/json"}

    async def _stream_events():
        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream("POST", url, headers=headers,
                                     cookies=_cookies(), json=payload) as resp:
                if resp.status_code == 401:
                    await login()
                    # retry with fresh cookies
                    async with client.stream("POST", url, headers=headers,
                                             cookies=_cookies(), json=payload) as resp2:
                        resp2.raise_for_status()
                        async for line in resp2.aiter_lines():
                            yield line
                    return
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    yield line

    async for line in _stream_events():
        if not line.startswith("data:"):
            continue
        raw = line[len("data:"):].strip()
        if not raw:
            continue
        try:
            batch = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for event in batch:
            etype = event.get("type")
            meta  = event.get("metadata", {}) or {}
            mtype = meta.get("type")

            if etype == "notification" and mtype == "thinking":
                label = meta.get("tool_title") or meta.get("title")
                if label:
                    yield {"type": "thinking", "text": label}

            elif etype in ("text-chunk", "text") and mtype == "thinking":
                c = event.get("content", "")
                if c:
                    yield {"type": "thinking_text", "text": c}

            elif etype == "text-chunk" and mtype == "text":
                c = event.get("content", "")
                if c:
                    yield {"type": "token", "text": c}

            elif etype == "answer":
                sid  = meta.get("session_id")    or event.get("session_id")
                gno  = meta.get("gen_no")         if meta.get("gen_no")         is not None else event.get("gen_no")
                txn  = meta.get("transaction_id") or event.get("transaction_id")
                agno = meta.get("generation_number") if meta.get("generation_number") is not None else event.get("generation_number")
                aid  = meta.get("answer_id")      or event.get("answer_id")

                if sid:  session_id = sid
                if gno  is not None: gen_no    = gno
                if txn:  txn_id     = txn
                if agno is not None: ac_gen_no = agno
                if aid:  current_answer_id = aid

                frame_url = build_frame_url(session_id, gen_no, txn_id, ac_gen_no)
                if frame_url:
                    yield {
                        "type":       "frame_url",
                        "frame_url":  frame_url,
                        # ✅ Pass answer_id so main.py can store it (durable)
                        "answer_id":  current_answer_id,
                        "answer_title": meta.get("title") or event.get("title"),
                    }

    yield {
        "type":            "done",
        "iframe_url":      build_frame_url(session_id, gen_no, txn_id, ac_gen_no),
        "conversation_id": conv_id,
    }


async def _load_chart_fresh(client: httpx.AsyncClient, base: str,
                             answer_id: str) -> Optional[dict]:
    """
    Call /answers/{answer_id}/details to get a FRESH session identity,
    then build a new frame_url from it.

    This is the core of the history fix: answer_id is durable (lives for
    the full 180-day retention window), while session_id expires quickly.
    We never store session_id — we always re-derive it here at render time.
    """
    ra = await _get(client, f"{base}/answers/{answer_id}/details")
    if ra.status_code != 200:
        logger.warning(f"Could not load answer {answer_id}: {ra.status_code}")
        return None

    a  = ra.json().get("answer", {})
    ac = a.get("ac_state", {}) or {}

    fu = build_frame_url(
        a.get("session_identifier"),
        a.get("generation_number"),
        ac.get("transaction_identifier"),
        ac.get("generation_number"),
    )
    if not fu:
        return None
    return {"kind": "chart", "frame_url": fu, "title": a.get("title") or "Chart"}


async def reconstruct_conversation(conv_id: str) -> list[dict]:
    """
    Rebuild a saved conversation for history display.

    Flow:
      1. GET /conversations/{conv_id}/messages  — full transcript
      2. For every answer_id found:
         GET /conversations/{conv_id}/answers/{answer_id}/details
         → fresh session_identifier + generation_number
         → build_frame_url()  ← always valid, never stale

    Returns turns:
      [{ query, thinking_text, blocks: [{kind, text} | {kind, frame_url, title}] }]
    """
    await _ensure_session()
    base = f"{TS_HOST}/api/rest/2.0/ai/agent/conversations/{conv_id}"

    async with httpx.AsyncClient(timeout=90) as client:
        r = await _get(client, f"{base}/messages")
        r.raise_for_status()
        messages = r.json().get("messages", [])

        turns = []
        for m in messages:
            query = (
                (m.get("user_prompt", {}) or {})
                .get("message", {}) or {}
            ).get("content", "")

            thinking_parts: list[str] = []
            blocks: list[dict] = []

            def push_text(t: str):
                if blocks and blocks[-1]["kind"] == "text":
                    blocks[-1]["text"] += t
                else:
                    blocks.append({"kind": "text", "text": t})

            for it in m.get("response_items", []):
                itype   = it.get("type")
                content = it.get("content") or ""

                if it.get("is_thinking"):
                    st = it.get("step_title")
                    if st:
                        thinking_parts.append(f"**{st}**")
                    if content and itype in ("text", "tool_result"):
                        thinking_parts.append(content)
                    if itype == "answer" and it.get("answer_id"):
                        # ✅ Fresh frame_url for intermediate thinking charts too
                        chart = await _load_chart_fresh(client, base, it["answer_id"])
                        if chart:
                            blocks.append(chart)
                else:
                    if itype == "text" and content:
                        push_text(content)
                    elif itype == "answer" and it.get("answer_id"):
                        # ✅ Fresh frame_url — never stale
                        chart = await _load_chart_fresh(client, base, it["answer_id"])
                        if chart:
                            blocks.append(chart)

            turns.append({
                "query":        query,
                "thinking_text": "\n\n".join(thinking_parts).strip(),
                "blocks":       blocks,
            })
        return turns
