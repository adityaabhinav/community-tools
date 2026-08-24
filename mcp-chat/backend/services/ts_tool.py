"""
ThoughtSpot tool implementation for the MCP-style POC.

Calls the Spotter Agent API (SSE stream), collects:
  - Final text answer tokens
  - session_id + generation_number from the 'answer' event

Constructs frame_url directly from the same session — no double computation.
Auto-retries once on 401 after refreshing the token.
"""

import os
import json
import httpx
import logging
from typing import Optional

from services.token_manager import get_token, refresh_token

logger = logging.getLogger(__name__)

TS_HOST = os.getenv("TS_HOST")
TS_WORKSHEET_ID = os.getenv("TS_WORKSHEET_ID")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_token()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


async def list_models() -> list[dict]:
    """Spotter-enabled worksheets/models on the cluster, for the model selector.
    aiAnswerGenerationDisabled=False reliably tracks Spotter-enablement. Business
    models sort first; system ('TS:') and sample models sort last."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{TS_HOST}/api/rest/2.0/metadata/search",
            headers=_headers(),
            json={"metadata": [{"type": "LOGICAL_TABLE"}], "record_size": 200},
        )
        if r.status_code == 401:
            await refresh_token()
            r = await client.post(
                f"{TS_HOST}/api/rest/2.0/metadata/search",
                headers=_headers(),
                json={"metadata": [{"type": "LOGICAL_TABLE"}], "record_size": 200},
            )
        r.raise_for_status()
        models = []
        for it in r.json():
            h = it.get("metadata_header", {}) or {}
            name = h.get("name", "")
            if (h.get("type") == "WORKSHEET"
                    and h.get("aiAnswerGenerationDisabled") is False
                    and "deprecated" not in name.lower()):
                models.append({"id": it.get("metadata_id"), "name": name})
        def rank(m):
            n = m["name"]
            return (n.startswith("TS:"), n.startswith("(Sample)"), n.lower())
        return sorted(models, key=rank)


async def _create_conversation(data_source_id: Optional[str] = None) -> str:
    url = f"{TS_HOST}/api/rest/2.0/ai/agent/conversation/create"
    # "auto" => let the agent auto-discover the most relevant dataset per query.
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
            "enable_save_chat": True,
        },
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=_headers(), json=payload, timeout=30)

        if resp.status_code == 401:
            logger.warning("401 on conversation create — refreshing token and retrying")
            new_token = await refresh_token()
            if not new_token:
                resp.raise_for_status()
            resp = await client.post(url, headers=_headers(), json=payload, timeout=30)

        resp.raise_for_status()
        return resp.json()["conversation_identifier"]


def build_frame_url(session_id, gen_no, txn_id, ac_gen_no) -> Optional[str]:
    """Construct the conv-assist-answer embed URL from a Spotter answer's
    session identity. Used for both the live stream and history re-render, so a
    reopened answer renders through the exact same iframe path as a live one."""
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
    Direct agent-conversation streaming path. Yields the SAME normalized events
    as the MCP path (run_query_stream), so main.py and the frontend are agnostic:
      {"type": "thinking",      "text": "<step label>"}      # tool-call notifications
      {"type": "thinking_text", "text": "<reasoning delta>"} # streamed reasoning
      {"type": "token",         "text": "<answer delta>"}    # streamed answer text
      {"type": "frame_url",     "frame_url": "...", ...}      # renderable chart
      {"type": "done",          "iframe_url": "...", "conversation_id": "..."}

    Unlike MCP (which polls every 2s), this is a true SSE stream, and it also
    surfaces the agent's reasoning that the old get_answer() discarded.
    """
    conv_id = conversation_id or await _create_conversation(data_source_id)
    url = f"{TS_HOST}/api/rest/2.0/ai/agent/conversation/{conv_id}/send/stream"
    payload = {"messages": [question]}

    session_id = gen_no = txn_id = ac_gen_no = None

    async def _events(headers):
        async with httpx.AsyncClient(timeout=180) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
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
                        yield event

    headers = {**_headers(), "Accept": "text/event-stream"}
    try:
        gen = _events(headers)
        async for event in gen:
            etype = event.get("type")
            meta = event.get("metadata", {}) or {}
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
                sid = meta.get("session_id") or event.get("session_id")
                gno = meta.get("gen_no") if meta.get("gen_no") is not None else event.get("gen_no")
                txn = meta.get("transaction_id") or event.get("transaction_id")
                agno = meta.get("generation_number") if meta.get("generation_number") is not None else event.get("generation_number")
                if sid:
                    session_id = sid
                if gno is not None:
                    gen_no = gno
                if txn:
                    txn_id = txn
                if agno is not None:
                    ac_gen_no = agno
                frame_url = build_frame_url(session_id, gen_no, txn_id, ac_gen_no)
                if frame_url:
                    yield {"type": "frame_url", "frame_url": frame_url,
                           "session_id": session_id, "generation_number": gen_no}
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            await refresh_token()
            # single retry with a fresh token
            async for event in run_api_stream(question, conv_id):
                yield event
            return
        raise

    yield {"type": "done",
           "iframe_url": build_frame_url(session_id, gen_no, txn_id, ac_gen_no),
           "conversation_id": conv_id}


async def _load_chart(client, base: str, answer_id: str) -> Optional[dict]:
    """loadAnswer -> a renderable chart block, or None."""
    ra = await client.get(f"{base}/answers/{answer_id}/details", headers=_headers())
    if ra.status_code == 401:
        await refresh_token()
        ra = await client.get(f"{base}/answers/{answer_id}/details", headers=_headers())
    if ra.status_code != 200:
        return None
    a = ra.json().get("answer", {})
    ac = a.get("ac_state", {}) or {}
    fu = build_frame_url(a.get("session_identifier"), a.get("generation_number"),
                         ac.get("transaction_identifier"), ac.get("generation_number"))
    if not fu:
        return None
    return {"kind": "chart", "frame_url": fu, "title": a.get("title") or "Chart"}


async def reconstruct_conversation(conv_id: str) -> list[dict]:
    """
    Rebuild a saved conversation for history display, entirely from the server,
    faithful to the original streamed response: the full reasoning trace (all
    thinking steps) plus every chart (intermediate + final), in order.

      getConversation -> ordered response_items per message
      loadAnswer      -> per answer_id: session identity -> conv-assist-answer frame_url

    Returns a list of turns:
      {"query": str,
       "thinking_text": str,                      # all thinking steps + reasoning
       "blocks": [{"kind":"text","text":...} | {"kind":"chart","frame_url":...,"title":...}]}
    """
    base = f"{TS_HOST}/api/rest/2.0/ai/agent/conversations/{conv_id}"
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.get(f"{base}/messages", headers=_headers())
        if r.status_code == 401:
            await refresh_token()
            r = await client.get(f"{base}/messages", headers=_headers())
        r.raise_for_status()
        messages = r.json().get("messages", [])

        turns = []
        for m in messages:
            query = ((m.get("user_prompt", {}) or {}).get("message", {}) or {}).get("content", "")
            thinking_parts: list[str] = []
            blocks: list[dict] = []

            def push_text(t: str):
                if blocks and blocks[-1]["kind"] == "text":
                    blocks[-1]["text"] += t
                else:
                    blocks.append({"kind": "text", "text": t})

            for it in m.get("response_items", []):
                itype = it.get("type")
                content = it.get("content") or ""
                if it.get("is_thinking"):
                    # Capture every thinking step: its label and any reasoning text.
                    st = it.get("step_title")
                    if st:
                        thinking_parts.append(f"**{st}**")
                    if content and itype in ("text", "tool_result"):
                        thinking_parts.append(content)
                    # Intermediate charts are is_thinking answer items — render them too.
                    if itype == "answer" and it.get("answer_id"):
                        chart = await _load_chart(client, base, it["answer_id"])
                        if chart:
                            blocks.append(chart)
                else:
                    if itype == "text" and content:
                        push_text(content)
                    elif itype == "answer" and it.get("answer_id"):
                        chart = await _load_chart(client, base, it["answer_id"])
                        if chart:
                            blocks.append(chart)

            turns.append({
                "query": query,
                "thinking_text": "\n\n".join(thinking_parts).strip(),
                "blocks": blocks,
            })
        return turns


async def get_answer(question: str, conversation_id: Optional[str] = None) -> dict:
    """
    Run a question through the ThoughtSpot Spotter Agent.

    Returns:
      {
        "text": "<final narrative answer>",
        "frame_url": "<iframe URL for the interactive chart>",
        "conversation_id": "<TS conversation id for multi-turn>",
        "session_id": "...",
        "generation_number": ...,
        "error": None | "<message>"
      }
    """
    try:
        conv_id = conversation_id or await _create_conversation()

        url = f"{TS_HOST}/api/rest/2.0/ai/agent/conversation/{conv_id}/send/stream"
        payload = {"messages": [question]}

        text_tokens: list[str] = []
        session_id: Optional[str] = None
        gen_no: Optional[int] = None
        transaction_id: Optional[str] = None
        generation_number: Optional[int] = None

        async def _stream(headers: dict):
            nonlocal text_tokens, session_id, gen_no, transaction_id, generation_number
            text_tokens = []
            session_id = None
            gen_no = None
            transaction_id = None
            generation_number = None
            async with httpx.AsyncClient(timeout=120) as client:
                async with client.stream("POST", url, headers=headers, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[len("data:"):].strip()
                        if not raw:
                            continue
                        try:
                            events = json.loads(raw)
                        except json.JSONDecodeError:
                            continue

                        for event in events:
                            etype = event.get("type")
                            if etype == "text-chunk":
                                meta = event.get("metadata", {})
                                if meta.get("type") == "text":
                                    text_tokens.append(event.get("content", ""))
                            elif etype == "answer":
                                meta = event.get("metadata", {})
                                # Correct mapping confirmed from MCP server streaming-utils.ts:
                                # sessionId       = metadata.session_id
                                # genNo           = metadata.gen_no
                                # acSessionId     = metadata.transaction_id
                                # acGenNo         = metadata.generation_number
                                sid = meta.get("session_id") or event.get("session_id")
                                gno = meta.get("gen_no") if meta.get("gen_no") is not None else event.get("gen_no")
                                txn = meta.get("transaction_id") or event.get("transaction_id")
                                gen_number = meta.get("generation_number") if meta.get("generation_number") is not None else event.get("generation_number")
                                logger.info(f"[answer event] session_id={sid} gen_no={gno} transaction_id={txn} generation_number={gen_number}")
                                if sid:
                                    session_id = sid
                                if gno is not None:
                                    gen_no = gno
                                if txn:
                                    transaction_id = txn
                                if gen_number is not None:
                                    generation_number = gen_number

        stream_headers = {**_headers(), "Accept": "text/event-stream"}
        try:
            await _stream(stream_headers)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.warning("401 on stream — refreshing token and retrying")
                new_token = await refresh_token()
                if not new_token:
                    raise
                await _stream({**_headers(), "Accept": "text/event-stream"})
            else:
                raise

        text = "".join(text_tokens).strip()

        frame_url = None
        if session_id and gen_no is not None:
            frame_url = (
                f"{TS_HOST}/?tsmcp=true"
                f"#/embed/conv-assist-answer"
                f"?sessionId={session_id}&genNo={gen_no}"
                f"&acSessionId={transaction_id}&acGenNo={generation_number}"
            )
            logger.info(f"[frame_url] {frame_url}")
        else:
            logger.warning(f"[frame_url] Could not construct — session_id={session_id} gen_no={gen_no} transaction_id={transaction_id}")

        return {
            "text": text,
            "frame_url": frame_url,
            "conversation_id": conv_id,
            "session_id": session_id,
            "generation_number": gen_no,
            "error": None,
        }

    except Exception as e:
        logger.error(f"ThoughtSpot tool error: {e}")
        return {
            "text": "",
            "frame_url": None,
            "conversation_id": conversation_id,
            "session_id": None,
            "generation_number": None,
            "error": str(e),
        }
