import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"), override=True)

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional, List

logging.basicConfig(level=logging.INFO)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, PlainTextResponse
from pydantic import BaseModel

from services.ts_mcp_client import run_query_stream
from services.ts_tool import run_api_stream, reconstruct_conversation, list_models
from services.claude_agent import chat as claude_chat
from services.token_manager import check_token_valid, refresh_token, _set_token, get_token
from services.db import init_db, save_item, get_conversations

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()


@app.on_event("startup")
async def auto_login():
    """Auto-generate a token on startup when TS_TOKEN is not set in .env.
    Requires TS_USERNAME + TS_PASSWORD (or TS_SECRET_KEY) to be configured."""
    if not get_token():
        logging.info("No TS_TOKEN in env — attempting auto-login with username/password…")
        token = await refresh_token()
        if token:
            logging.info("Auto-login succeeded.")
        else:
            logging.warning(
                "Auto-login failed. Set TS_TOKEN, or add TS_USERNAME + TS_PASSWORD to .env"
            )


class ChatRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None
    mode: str = "mcp"   # "mcp" | "api" | "claude_mcp"
    data_source_id: Optional[str] = None  # selected model; falls back to env default


async def _api_stream(query: str, conversation_id: Optional[str], data_source_id: Optional[str] = None):
    """Direct agent-conversation streaming path. Delegates to run_api_stream,
    which emits the same normalized events as the MCP path (thinking,
    thinking_text, token, frame_url, done) but over a true SSE stream."""
    async for event in run_api_stream(query, conversation_id=conversation_id, data_source_id=data_source_id):
        yield event


async def _claude_mcp_stream(query: str, conversation_id: Optional[str]):
    """Wrap Claude-orchestrated MCP as an SSE-compatible async generator."""
    yield {"type": "thinking", "text": "Claude orchestrating ThoughtSpot MCP…"}
    result = await claude_chat(query, conversation_id=conversation_id)
    if result.get("text"):
        yield {"type": "token", "text": result["text"]}
    if result.get("frame_url"):
        yield {"type": "frame_url", "frame_url": result["frame_url"]}
    yield {
        "type": "done",
        "iframe_url": result.get("frame_url"),
        "conversation_id": result.get("conversation_id"),
    }


# ── SSE chat endpoint ──────────────────────────────────────────────────────────

@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """
    SSE endpoint. Yields normalized events:
      data: {"type": "thinking",       "text": "..."}
      data: {"type": "thinking_text",  "text": "..."}
      data: {"type": "token",          "text": "..."}
      data: {"type": "conversation_id","conversation_id": "..."}
      data: {"type": "frame_url",      "frame_url": "..."}
      data: {"type": "done"}
    """
    async def generate():
        full_text: list[str] = []
        # Ordered, interleaved text + chart blocks for this turn. Persisting the
        # full block list (not just a flattened string + one url) is what lets
        # history re-render each chart via SearchEmbed from its own tokens.
        blocks: list[dict] = []
        iframe_url = None
        conv_id = None

        def push_text(t: str):
            if blocks and blocks[-1]["kind"] == "text":
                blocks[-1]["text"] += t
            else:
                blocks.append({"kind": "text", "text": t})

        if req.mode == "api":
            stream = _api_stream(req.query, req.conversation_id, req.data_source_id)
        elif req.mode == "claude_mcp":
            stream = _claude_mcp_stream(req.query, req.conversation_id)
        else:
            stream = run_query_stream(req.query, conversation_id=req.conversation_id,
                                      data_source_id=req.data_source_id)

        async for event in stream:
            etype = event.get("type")

            if etype in ("thinking", "thinking_text"):
                yield f"data: {json.dumps(event)}\n\n"

            elif etype == "token":
                text = event.get("text", "")
                full_text.append(text)
                push_text(text)
                yield f"data: {json.dumps(event)}\n\n"

            elif etype == "frame_url":
                iframe_url = event.get("frame_url")
                blocks.append({
                    "kind": "chart",
                    "url": event.get("frame_url"),
                    "data_source_id": event.get("data_source_id"),
                    "answer_query": event.get("answer_query"),
                    "answer_id": event.get("answer_id"),
                    "answer_title": event.get("answer_title"),
                })
                yield f"data: {json.dumps(event)}\n\n"

            elif etype == "done":
                conv_id = event.get("conversation_id")
                if conv_id:
                    yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': conv_id})}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                save_item({
                    "id": uuid.uuid4().hex,
                    "query": req.query,
                    "source": "thoughtspot",
                    "text": "".join(full_text),
                    "frame_url": iframe_url,
                    "conversation_id": conv_id,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "content_blocks": json.dumps(blocks),
                })

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── History ────────────────────────────────────────────────────────────────────

class HistoryItem(BaseModel):
    id: str
    query: str
    source: str
    text: str
    frame_url: Optional[str] = None
    conversation_id: Optional[str] = None
    created_at: str
    turn_count: Optional[int] = None
    content_blocks: Optional[str] = None  # JSON string of ordered text/chart blocks


class HistoryResponse(BaseModel):
    items: List[HistoryItem]


class ModelItem(BaseModel):
    id: str
    name: str


class ModelsResponse(BaseModel):
    models: List[ModelItem]


@app.get("/models", response_model=ModelsResponse)
async def get_models():
    """Spotter-enabled models available on the cluster, for the model selector."""
    return ModelsResponse(models=await list_models())


@app.get("/history", response_model=HistoryResponse)
async def get_history():
    """List saved conversations (one entry per conversation, first turn as title)."""
    return HistoryResponse(items=[HistoryItem(**row) for row in get_conversations()])


class Block(BaseModel):
    kind: str                       # "text" | "chart"
    text: Optional[str] = None      # for text blocks
    frame_url: Optional[str] = None # for chart blocks
    title: Optional[str] = None     # for chart blocks


class ConversationTurn(BaseModel):
    query: str
    thinking_text: str = ""
    blocks: List[Block] = []


class ConversationResponse(BaseModel):
    turns: List[ConversationTurn]


@app.get("/history/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: str):
    """Rebuild a past conversation entirely from the server: getConversation for
    the transcript (prompts, reasoning, answer text) and loadAnswer per answer to
    produce a conv-assist-answer frame_url. No locally stored answer content."""
    turns = await reconstruct_conversation(conversation_id)
    return ConversationResponse(turns=turns)


# ── Auth / health ──────────────────────────────────────────────────────────────

@app.get("/ts-token")
async def ts_token():
    token = _set_token.__module__ and None  # just to import
    from services.token_manager import get_token
    status = await check_token_valid()
    if not status["valid"]:
        await refresh_token()
    from services.token_manager import get_token
    return PlainTextResponse(get_token() or "")


@app.get("/health")
async def health():
    status = await check_token_valid()
    return {"thoughtspot_token": status}


class TokenUpdate(BaseModel):
    token: str


@app.post("/token")
async def update_token(req: TokenUpdate):
    _set_token(req.token)
    status = await check_token_valid()
    return {"updated": True, "thoughtspot_token": status}


@app.post("/token/refresh")
async def do_refresh_token():
    new_token = await refresh_token()
    if new_token:
        status = await check_token_valid()
        return {"refreshed": True, "thoughtspot_token": status}
    return {"refreshed": False, "reason": "No TS_SECRET_KEY or TS_PASSWORD in .env"}


# ── Static frontend ────────────────────────────────────────────────────────────

frontend_dist = os.path.join(os.path.dirname(__file__), "../frontend/dist")
if os.path.isdir(frontend_dist):
    app.mount("/assets", StaticFiles(directory=f"{frontend_dist}/assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        return FileResponse(f"{frontend_dist}/index.html")
