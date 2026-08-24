"""
Token manager for ThoughtSpot bearer tokens.

On 401, automatically fetches a fresh token using username + secret_key
and retries the request. Token is cached in memory.
"""

import os
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

TS_HOST = os.getenv("TS_HOST")
TS_USERNAME = os.getenv("TS_USERNAME")
TS_SECRET_KEY = os.getenv("TS_SECRET_KEY")  # ThoughtSpot trusted auth secret key
TS_PASSWORD = os.getenv("TS_PASSWORD")       # fallback: plain password auth
_TS_ORG_ID = os.getenv("TS_ORG_ID")         # optional: required for multi-org clusters

# In-memory token cache (starts with the static token from .env, if provided)
_current_token: Optional[str] = os.getenv("TS_TOKEN") or None


def get_token() -> Optional[str]:
    return _current_token


def _set_token(token: str):
    global _current_token
    _current_token = token
    logger.info("ThoughtSpot token refreshed successfully")


async def refresh_token() -> Optional[str]:
    """
    Fetch a fresh token from ThoughtSpot.
    Tries secret-key auth first, falls back to password auth.
    Returns the new token or None if both fail.
    """
    global _current_token

    if TS_SECRET_KEY:
        url = f"{TS_HOST}/api/rest/2.0/auth/token/full"
        payload = {
            "username": TS_USERNAME,
            "secret_key": TS_SECRET_KEY,
            "validity_time_in_sec": 86400,
            **( {"org_id": int(_TS_ORG_ID)} if _TS_ORG_ID else {} ),
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    token = data.get("token")
                    if token:
                        _set_token(token)
                        return token
        except Exception as e:
            logger.warning(f"Secret-key token refresh failed: {e}")

    if TS_PASSWORD:
        url = f"{TS_HOST}/api/rest/2.0/auth/token/full"
        payload = {
            "username": TS_USERNAME,
            "password": TS_PASSWORD,
            "validity_time_in_sec": 86400,
            **( {"org_id": int(_TS_ORG_ID)} if _TS_ORG_ID else {} ),
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    token = data.get("token")
                    if token:
                        _set_token(token)
                        return token
        except Exception as e:
            logger.warning(f"Password token refresh failed: {e}")

    logger.error("All token refresh methods failed — update TS_TOKEN in .env manually")
    return None


async def check_token_valid() -> dict:
    """Check if the current token is valid by calling a lightweight endpoint."""
    token = get_token()
    if not token:
        return {"valid": False, "reason": "No token configured"}

    url = f"{TS_HOST}/api/rest/2.0/auth/session/user"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return {"valid": True, "user": data.get("name", TS_USERNAME)}
            elif resp.status_code == 401:
                return {"valid": False, "reason": "Token expired (401)"}
            else:
                return {"valid": False, "reason": f"Unexpected status {resp.status_code}"}
    except Exception as e:
        return {"valid": False, "reason": str(e)}
