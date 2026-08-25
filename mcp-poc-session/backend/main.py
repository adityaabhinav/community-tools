import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../.env"), override=True)

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, AsyncGenerator

logging.basicConfig(level=logging.INFO)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, PlainTextResponse
from pydantic import BaseModel

from services.ts_tool import run_api_stream, reconstruct_conversation, list_models
from services.ts_mcp_client import run_query_stream
from services.claude_agent import chat as claude_chat
from services.token_manager import check_token_valid, login, get_token
from services.db import init_db, save_item, get_conversations


@asynccontextmanager
async def lifespan(app: FastAPI):
    await login()
    status = await check_token_valid()
    logging.getLogger(__name__).info(f"Startup auth: {status}")
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()


class ChatRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None
    mode: str = "api"
    data_source_id: Optional[str] = None


async def _claude_mcp_stream(query: str, conversation_id: Optional[str]) -> AsyncGenerator[dict, None]:
    """Wrap the non-streaming claude_agent.chat() in a generator compatible with the SSE loop."""
    result = await claude_chat(query, conversation_id=conversation_id)
    if result.get("text"):
        yield {"type": "token", "text": result["text"]}
    if result.get("frame_url"):
        yield {"type": "frame_url", "frame_url": result["frame_url"]}
    yield {"type": "done", "conversation_id": result.get("conversation_id")}


# ── SSE chat endpoint ──────────────────────────────────────────────────────────

@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    async def generate():
        full_text: list[str] = []
        blocks: list[dict] = []
        iframe_url = None
        conv_id = None

        def push_text(t: str):
            if blocks and blocks[-1]["kind"] == "text":
                blocks[-1]["text"] += t
            else:
                blocks.append({"kind": "text", "text": t})

        if req.mode == "mcp":
            event_stream = run_query_stream(
                req.query,
                conversation_id=req.conversation_id,
                data_source_id=req.data_source_id,
            )
        elif req.mode == "claude_mcp":
            event_stream = _claude_mcp_stream(req.query, conversation_id=req.conversation_id)
        else:
            event_stream = run_api_stream(
                req.query,
                conversation_id=req.conversation_id,
                data_source_id=req.data_source_id,
            )

        try:
            async for event in event_stream:
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
                        "kind":         "chart",
                        "url":          event.get("frame_url"),
                        "answer_id":    event.get("answer_id"),
                        "answer_title": event.get("answer_title"),
                    })
                    yield f"data: {json.dumps(event)}\n\n"

                elif etype == "done":
                    conv_id = event.get("conversation_id")
                    if conv_id:
                        yield f"data: {json.dumps({'type': 'conversation_id', 'conversation_id': conv_id})}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"

                    save_item({
                        "id":             uuid.uuid4().hex,
                        "query":          req.query,
                        "source":         "thoughtspot",
                        "text":           "".join(full_text),
                        "frame_url":      iframe_url,
                        "conversation_id": conv_id,
                        "created_at":     datetime.now(timezone.utc).isoformat(),
                        "content_blocks": json.dumps(blocks),
                    })

        except Exception as exc:
            logging.getLogger(__name__).error(f"Stream error [{req.mode}]: {exc}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

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
    content_blocks: Optional[str] = None


class HistoryResponse(BaseModel):
    items: List[HistoryItem]


class ModelItem(BaseModel):
    id: str
    name: str


class ModelsResponse(BaseModel):
    models: List[ModelItem]


@app.get("/models", response_model=ModelsResponse)
async def get_models():
    return ModelsResponse(models=await list_models())


@app.get("/history", response_model=HistoryResponse)
async def get_history():
    return HistoryResponse(items=[HistoryItem(**row) for row in get_conversations()])


class Block(BaseModel):
    kind: str
    text: Optional[str] = None
    frame_url: Optional[str] = None
    title: Optional[str] = None


class ConversationTurn(BaseModel):
    query: str
    thinking_text: str = ""
    blocks: List[Block] = []


class ConversationResponse(BaseModel):
    turns: List[ConversationTurn]


@app.get("/history/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: str):
    """
    Reconstruct a past conversation entirely from ThoughtSpot:
      - GET /conversations/{id}/messages  → transcript
      - GET /conversations/{id}/answers/{answer_id}/details  → fresh session identity
      - build_frame_url()  → always-valid iframe URL

    No stored session IDs are replayed — every chart gets a fresh frame_url.
    """
    turns = await reconstruct_conversation(conversation_id)
    return ConversationResponse(turns=turns)


# ── Auth / health ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    status = await check_token_valid()
    return {"thoughtspot_session": status}


@app.post("/auth/login")
async def do_login():
    ok = await login()
    status = await check_token_valid()
    return {"logged_in": ok, "thoughtspot_session": status}


# Returns the bearer token used by the frontend Embed SDK for iframe auth.
# Requires TS_TOKEN to be set in .env; returns empty string if not configured.
@app.get("/ts-token")
async def ts_token():
    return PlainTextResponse(get_token() or "")


@app.post("/token/refresh")
async def do_refresh_token():
    ok = await login()
    return {"refreshed": ok}


# ── Static frontend ────────────────────────────────────────────────────────────

frontend_dist = os.path.join(os.path.dirname(__file__), "../frontend/dist")
if os.path.isdir(frontend_dist):
    app.mount("/assets", StaticFiles(directory=f"{frontend_dist}/assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        return FileResponse(f"{frontend_dist}/index.html")
