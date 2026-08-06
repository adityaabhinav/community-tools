"""ThoughtSpot REST API client (v2 primary, v1 fallback for ownership transfer)."""

from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import requests

logger = logging.getLogger(__name__)

_DEFAULT_PAGE = 200  # records per paginated request


@dataclass
class TSConfig:
    url: str
    username: str
    password: str
    verify_ssl: bool = True


class ThoughtSpotClient:
    """Session-based client for ThoughtSpot REST API."""

    V2 = "/api/rest/2.0"
    V1 = "/tspublic/v1"

    def __init__(self, config: TSConfig):
        self.config = config
        self.base = config.url.rstrip("/")
        self._s = requests.Session()
        self._s.headers.update({"X-Requested-By": "ThoughtSpot", "Accept": "application/json"})
        self._s.verify = config.verify_ssl
        self._authenticated = False

    # ------------------------------------------------------------------ auth

    def login(self) -> None:
        resp = self._s.post(
            f"{self.base}{self.V2}/auth/session/login",
            json={"username": self.config.username, "password": self.config.password},
        )
        resp.raise_for_status()
        self._authenticated = True
        logger.info("Authenticated to %s as %s", self.base, self.config.username)

    def logout(self) -> None:
        if self._authenticated:
            try:
                self._s.post(f"{self.base}{self.V2}/auth/session/logout")
            except Exception:
                pass
            self._authenticated = False

    def __enter__(self) -> "ThoughtSpotClient":
        self.login()
        return self

    def __exit__(self, *_: Any) -> None:
        self.logout()

    # ---------------------------------------------------------- low-level I/O

    def _ensure_auth(self) -> None:
        if not self._authenticated:
            self.login()

    def _get(self, path: str, **kwargs: Any) -> Any:
        self._ensure_auth()
        r = self._s.get(f"{self.base}{path}", **kwargs)
        r.raise_for_status()
        return r.json() if r.content else {}

    def _post(self, path: str, **kwargs: Any) -> Any:
        self._ensure_auth()
        r = self._s.post(f"{self.base}{path}", **kwargs)
        r.raise_for_status()
        return r.json() if r.content else {}

    # ---------------------------------------------------------------- groups

    def search_groups(self, group_identifier: Optional[str] = None) -> List[Dict]:
        """Return groups matching identifier (name or GUID), or all groups."""
        payload: Dict[str, Any] = {"record_size": _DEFAULT_PAGE, "record_offset": 0}
        if group_identifier:
            payload["group_identifier"] = group_identifier
        results: List[Dict] = []
        while True:
            page = self._post(f"{self.V2}/groups/search", json=payload)
            if not page:
                break
            results.extend(page)
            if len(page) < _DEFAULT_PAGE:
                break
            payload["record_offset"] += _DEFAULT_PAGE
        return results

    def create_group(self, payload: Dict) -> Dict:
        return self._post(f"{self.V2}/groups/create", json=payload)

    # ----------------------------------------------------------------- users

    def search_users(self, group_identifiers: Optional[List[str]] = None) -> List[Dict]:
        payload: Dict[str, Any] = {"record_size": _DEFAULT_PAGE, "record_offset": 0}
        if group_identifiers:
            payload["group_identifiers"] = group_identifiers
        results: List[Dict] = []
        while True:
            page = self._post(f"{self.V2}/users/search", json=payload)
            if not page:
                break
            results.extend(page)
            if len(page) < _DEFAULT_PAGE:
                break
            payload["record_offset"] += _DEFAULT_PAGE
        return results

    def create_user(self, payload: Dict) -> Dict:
        return self._post(f"{self.V2}/users/create", json=payload)

    # -------------------------------------------------------------- metadata

    def search_metadata(self, metadata_types: List[str], **filters: Any) -> List[Dict]:
        """Search metadata with optional filters (created_by_user_identifiers, etc.)."""
        payload: Dict[str, Any] = {
            "metadata": [{"type": t} for t in metadata_types],
            "record_size": _DEFAULT_PAGE,
            "record_offset": 0,
            **filters,
        }
        results: List[Dict] = []
        while True:
            page = self._post(f"{self.V2}/metadata/search", json=payload)
            if not page:
                break
            results.extend(page)
            if len(page) < _DEFAULT_PAGE:
                break
            payload["record_offset"] += _DEFAULT_PAGE
        return results

    def export_tml(self, metadata: List[Dict], export_associated: bool = False) -> List[Dict]:
        """Export TML for a list of {identifier, type} dicts."""
        return self._post(
            f"{self.V2}/metadata/tml/export",
            json={"metadata": metadata, "export_associated": export_associated},
        )

    def import_tml(self, tml_strings: List[str], force_create: bool = True) -> List[Dict]:
        """Import a list of raw TML strings. Returns per-object status."""
        return self._post(
            f"{self.V2}/metadata/tml/import",
            json={
                "metadata_tmls": tml_strings,
                "import_policy": "PARTIAL",
                "force_create": force_create,
            },
        )

    # ----------------------------------------------------------- permissions

    def fetch_permissions(self, metadata: List[Dict]) -> List[Dict]:
        """metadata: list of {identifier, type} dicts."""
        return self._post(
            f"{self.V2}/security/metadata/fetch",
            json={"metadata_list": metadata},
        )

    def share_objects(self, metadata: List[Dict], permissions: List[Dict]) -> None:
        """
        metadata: [{identifier, type}, ...]
        permissions: [{principal_id, principal_type, share_mode}, ...]
        """
        self._post(
            f"{self.V2}/security/metadata/share",
            json={"metadata_list": metadata, "permissions": permissions},
        )

    # ------------------------------------------------------- ownership (v1)

    def transfer_ownership(self, from_username: str, to_username: str, object_ids: List[str]) -> None:
        """Transfer object ownership via the v1 API (still the reliable path for this)."""
        self._post(
            f"{self.V1}/user/transfer/ownership",
            params={"fromUserName": from_username, "toUserName": to_username},
            json={"objectsID": object_ids},
        )
