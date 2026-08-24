"""
Claude as the orchestrator using the REAL ThoughtSpot MCP server.

Anthropic's MCP connector (beta) connects Claude directly to
agent.thoughtspot.app/token/mcp — no hand-rolled tool implementations.

Claude uses the Spotter3 V2 tools (CreateAnalysisSession, SendSessionMessage,
GetSessionUpdates) or V1 tools (getAnswer) depending on what the server exposes.

Multi-turn: we maintain a message history per analytical_session_id so Claude
can reuse the same ThoughtSpot session across follow-up questions.
"""

import os
import json
import logging
from typing import Optional
import anthropic

from services.token_manager import get_token, check_token_valid, refresh_token

logger = logging.getLogger(__name__)

TS_HOST = os.getenv("TS_HOST", "")

TS_WORKSHEET_ID = os.getenv("TS_WORKSHEET_ID", "")

SYSTEM_PROMPT = (
    "You are a helpful data assistant with access to ThoughtSpot analytics. "
    f"Always use data_source_id='{TS_WORKSHEET_ID}' when creating an analysis session. "
    "For data and analytics questions, use the ThoughtSpot tools silently — "
    "do NOT narrate your tool calls or say things like 'I'll create a session' or 'let me poll'. "
    "Just present the final answer naturally and concisely. "
    "For general questions (greetings, how-to, explanations), answer directly without using tools."
)

# In-memory conversation history keyed by analytical_session_id
# Each value is a list of message dicts (user/assistant turns)
_sessions: dict[str, list] = {}


def _ts_domain() -> str:
    return TS_HOST.replace("https://", "").replace("http://", "").rstrip("/")


def _mcp_auth_token() -> str:
    """ThoughtSpot MCP auth format: {bearer_token}@{ts_host_domain}"""
    return f"{get_token()}@{_ts_domain()}"


def _mcp_server() -> dict:
    return {
        "type": "url",
        "url": "https://agent.thoughtspot.app/token/mcp",
        "name": "thoughtspot",
        "authorization_token": _mcp_auth_token(),
    }


def _extract_iframe_url(response) -> Optional[str]:
    """Parse mcp_tool_result blocks to find iframe_url / frame_url."""
    for block in response.content:
        if getattr(block, "type", None) == "mcp_tool_result":
            for item in getattr(block, "content", []):
                text = getattr(item, "text", None)
                if not text:
                    continue
                try:
                    data = json.loads(text)
                    # V2: GetSessionUpdates → session_updates[].iframe_url
                    for update in data.get("session_updates", []):
                        if update.get("type") == "answer" and update.get("iframe_url"):
                            return update["iframe_url"]
                    # V1: getAnswer → frame_url
                    if data.get("frame_url"):
                        return data["frame_url"]
                except (json.JSONDecodeError, AttributeError):
                    pass
    return None


def _extract_session_id(response) -> Optional[str]:
    """Extract analytical_session_id from CreateAnalysisSession result."""
    for block in response.content:
        if getattr(block, "type", None) == "mcp_tool_result":
            for item in getattr(block, "content", []):
                text = getattr(item, "text", None)
                if not text:
                    continue
                try:
                    data = json.loads(text)
                    if data.get("analytical_session_id"):
                        return data["analytical_session_id"]
                except (json.JSONDecodeError, AttributeError):
                    pass
    return None


def _used_ts_tools(response) -> bool:
    return any(
        getattr(b, "type", "") in ("mcp_tool_use", "mcp_tool_result")
        for b in response.content
    )


async def chat(query: str, conversation_id: Optional[str] = None) -> dict:
    """
    Send a query through Claude + ThoughtSpot MCP server.

    Returns:
      { text, frame_url, source, conversation_id }
    """
    # Auto-refresh token if expired
    status = await check_token_valid()
    if not status["valid"]:
        await refresh_token()

    # Read key fresh each call so .env changes are picked up without restart
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    # OAT tokens (sk-ant-oat01-) require auth_token=; standard keys use api_key=
    if api_key.startswith("sk-ant-oat"):
        client = anthropic.Anthropic(auth_token=api_key)
    else:
        client = anthropic.Anthropic(api_key=api_key)

    # Build message history for this session
    if conversation_id and conversation_id in _sessions:
        history = _sessions[conversation_id]
    else:
        history = []

    # If we have a known session, remind Claude to reuse it
    user_content = query
    if conversation_id and conversation_id in _sessions:
        user_content = (
            f"{query}\n\n"
            f"[Use the existing ThoughtSpot session: {conversation_id}]"
        )

    messages = history + [{"role": "user", "content": user_content}]

    response = client.beta.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=messages,
        mcp_servers=[_mcp_server()],
        tools=[{"type": "mcp_toolset", "mcp_server_name": "thoughtspot"}],
        betas=["mcp-client-2025-11-20"],
    )

    # Take only the last text block — intermediate blocks are tool-call narration
    text_blocks = [
        getattr(b, "text", "")
        for b in response.content
        if getattr(b, "type", "") == "text"
    ]
    text = text_blocks[-1].strip() if text_blocks else ""

    iframe_url = _extract_iframe_url(response)
    new_session_id = _extract_session_id(response)
    used_ts = _used_ts_tools(response)

    source = "thoughtspot" if (used_ts or iframe_url) else "claude"
    session_id = new_session_id or conversation_id

    logger.info(
        f"[chat] source={source} session_id={session_id} iframe_url={'yes' if iframe_url else 'no'}"
    )

    # Persist conversation history for multi-turn
    if session_id:
        # Serialize response content for history (keep text + tool blocks)
        assistant_content = []
        for b in response.content:
            btype = getattr(b, "type", "")
            if btype == "text":
                assistant_content.append({"type": "text", "text": b.text})
        if assistant_content:
            updated_history = messages + [{"role": "assistant", "content": assistant_content}]
            _sessions[session_id] = updated_history

    return {
        "text": text,
        "frame_url": iframe_url,
        "source": source,
        "conversation_id": session_id,
    }
