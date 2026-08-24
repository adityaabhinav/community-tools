"""
Token manager — session-cookie auth for ps-internal cluster.

Instead of a bearer token, we authenticate once via username+password,
let ThoughtSpot set a session cookie, and reuse that cookie for all
subsequent API calls. No TS_TOKEN or TS_SECRET_KEY needed.

On 401, automatically re-authenticates and retries.
"""

import os
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

TS_HOST     = os.getenv("TS_HOST")
TS_USERNAME = os.getenv("TS_USERNAME")
TS_PASSWORD = os.getenv("TS_PASSWORD")
_TS_ORG_ID  = os.getenv("TS_ORG_ID")

# In-memory session cookie jar — shared across all requests.
_session_cookies: dict[str, str] = {}


def get_cookies() -> dict[str, str]:
    return _session_cookies


async def login() -> bool:
    """
    POST /api/rest/2.0/auth/session/login with username+password.
    ThoughtSpot sets JSESSIONID (and optionally clientId) as cookies.
    We capture and reuse them for every subsequent call.
    """
    global _session_cookies
    url = f"{TS_HOST}/api/rest/2.0/auth/session/login"
    payload: dict = {
        "username": TS_USERNAME,
        "password": TS_PASSWORD,
        "remember_me": True,
    }
    if _TS_ORG_ID:
        payload["org_id"] = int(_TS_ORG_ID)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, timeout=15)
            if resp.status_code == 204 or resp.status_code == 200:
                # Capture all cookies ThoughtSpot set
                _session_cookies = dict(resp.cookies)
                logger.info(f"Session login succeeded — cookies: {list(_session_cookies.keys())}")
                return True
            else:
                logger.error(f"Session login failed: {resp.status_code} {resp.text}")
                return False
    except Exception as e:
        logger.error(f"Session login error: {e}")
        return False


async def ensure_session() -> bool:
    """Ensure we have an active session, logging in if needed."""
    if _session_cookies:
        return True
    return await login()


# Kept for compatibility with existing code that calls refresh_token()
async def refresh_token() -> Optional[str]:
    success = await login()
    return "session" if success else None


async def check_token_valid() -> dict:
    """Verify session is alive by calling a lightweight endpoint."""
    if not _session_cookies:
        ok = await login()
        if not ok:
            return {"valid": False, "reason": "Login failed"}

    url = f"{TS_HOST}/api/rest/2.0/auth/session/user"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, cookies=_session_cookies, timeout=10)
            if resp.status_code == 200:
                return {"valid": True, "user": resp.json().get("name", TS_USERNAME)}
            elif resp.status_code == 401:
                # Session expired — re-login
                ok = await login()
                return {"valid": ok, "reason": None if ok else "Re-login failed"}
            else:
                return {"valid": False, "reason": f"Status {resp.status_code}"}
    except Exception as e:
        return {"valid": False, "reason": str(e)}


# Bearer token for MCP server auth (needed for Direct MCP and Claude+MCP modes).
# Format expected by agent.thoughtspot.app/token/mcp: {token}@{ts_domain}
_TS_TOKEN = os.getenv("TS_TOKEN", "")


def get_token() -> Optional[str]:
    return _TS_TOKEN or None


def _set_token(token: str):
    global _TS_TOKEN
    _TS_TOKEN = token
