"""
Token manager — session-cookie auth + auto-fetched bearer token.

Authentication flow:
  1. POST /auth/session/login  — sets JSESSIONID cookie used by all REST calls.
  2. POST /auth/token/full     — fetches a bearer token using the same credentials.
     The bearer token is used by the ThoughtSpot MCP server and the Embed SDK
     (iframe auth). It is refreshed automatically whenever login() is called.

Only TS_HOST, TS_USERNAME, and TS_PASSWORD are required in .env.
TS_TOKEN is optional — if set, it overrides the auto-fetched token.
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

# Bearer token — auto-fetched after login, or overridden by TS_TOKEN in .env.
_TS_TOKEN: str = os.getenv("TS_TOKEN", "")


def get_cookies() -> dict[str, str]:
    return _session_cookies


async def _fetch_bearer_token(client: httpx.AsyncClient) -> str:
    """
    POST /api/rest/2.0/auth/token/full with username+password to get a bearer
    token. Called automatically after a successful session login so callers
    never have to set TS_TOKEN manually.
    """
    url = f"{TS_HOST}/api/rest/2.0/auth/token/full"
    payload: dict = {
        "username": TS_USERNAME,
        "password": TS_PASSWORD,
        "validity_time_in_sec": 86400,   # 24 h; re-fetched on every login()
    }
    if _TS_ORG_ID:
        payload["org_id"] = int(_TS_ORG_ID)
    try:
        resp = await client.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            token = resp.json().get("token", "")
            logger.info("Bearer token fetched successfully")
            return token
        else:
            logger.warning(f"Bearer token fetch failed: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"Bearer token fetch error: {e}")
    return ""


async def login() -> bool:
    """
    1. POST /auth/session/login  → captures session cookies.
    2. POST /auth/token/full     → fetches bearer token for MCP + Embed SDK.
    """
    global _session_cookies, _TS_TOKEN
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
            if resp.status_code in (200, 204):
                _session_cookies = dict(resp.cookies)
                logger.info(f"Session login succeeded — cookies: {list(_session_cookies.keys())}")
                # Only auto-fetch if TS_TOKEN wasn't pinned in .env
                if not os.getenv("TS_TOKEN"):
                    _TS_TOKEN = await _fetch_bearer_token(client)
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
                ok = await login()
                return {"valid": ok, "reason": None if ok else "Re-login failed"}
            else:
                return {"valid": False, "reason": f"Status {resp.status_code}"}
    except Exception as e:
        return {"valid": False, "reason": str(e)}


def get_token() -> Optional[str]:
    return _TS_TOKEN or None


def _set_token(token: str):
    global _TS_TOKEN
    _TS_TOKEN = token
