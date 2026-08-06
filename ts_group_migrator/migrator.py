"""Top-level orchestrator: export from source, import to destination."""

from __future__ import annotations
import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .client import ThoughtSpotClient, TSConfig
from .exporter import Exporter
from .importer import ImportResult, Importer
from .models import MigrationBundle

logger = logging.getLogger(__name__)


class GroupMigrator:
    """
    Migrate a ThoughtSpot group (and everything related to it) from one cluster to another.

    Usage
    -----
    migrator = GroupMigrator(
        source=TSConfig(url="https://src.thoughtspot.cloud", username="admin", password="..."),
        destination=TSConfig(url="https://dst.thoughtspot.cloud", username="admin", password="..."),
    )
    result = migrator.migrate("Sales Team")
    print(result.summary())
    """

    def __init__(
        self,
        source: TSConfig,
        destination: TSConfig,
        default_user_password: str = "Changeme@123",
        bundle_cache_path: Optional[str] = None,
    ):
        self._src_cfg = source
        self._dst_cfg = destination
        self._default_password = default_user_password
        self._bundle_cache_path = bundle_cache_path

    def migrate(self, group_name: str) -> ImportResult:
        """
        Full migration pipeline for the given group.

        Steps
        -----
        1. Export group tree, users, objects (with TML), and permissions from source.
        2. Optionally save bundle to disk for inspection / replay.
        3. Apply everything to the destination cluster.
        """
        bundle = self._export(group_name)
        logger.info("Bundle: %s", bundle.summary())

        if self._bundle_cache_path:
            self._save_bundle(bundle, self._bundle_cache_path)

        return self._import(bundle)

    def migrate_from_bundle(self, bundle_path: str) -> ImportResult:
        """Re-run the import phase from a previously saved bundle (useful for retries)."""
        bundle = self._load_bundle(bundle_path)
        logger.info("Loaded bundle from %s: %s", bundle_path, bundle.summary())
        return self._import(bundle)

    # ---------------------------------------------------------------- phases

    def _export(self, group_name: str) -> MigrationBundle:
        with ThoughtSpotClient(self._src_cfg) as client:
            return Exporter(client).export(group_name)

    def _import(self, bundle: MigrationBundle) -> ImportResult:
        with ThoughtSpotClient(self._dst_cfg) as client:
            return Importer(client, default_password=self._default_password).apply(bundle)

    # --------------------------------------------------------- bundle I/O

    @staticmethod
    def _save_bundle(bundle: MigrationBundle, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(asdict(bundle), fh, indent=2)
        logger.info("Bundle saved to %s", path)

    @staticmethod
    def _load_bundle(path: str) -> MigrationBundle:
        from dataclasses import fields
        from .models import TSGroup, TSUser, TSObject, TSPermission, MetadataType, PermissionType, PrincipalType

        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)

        groups = [TSGroup(**g) for g in raw.get("groups", [])]
        users = [TSUser(**u) for u in raw.get("users", [])]
        objects = [
            TSObject(
                id=o["id"], name=o["name"],
                type=MetadataType(o["type"]),
                author_id=o["author_id"], author_name=o["author_name"],
                tml=o.get("tml", ""),
            )
            for o in raw.get("objects", [])
        ]
        permissions = [
            TSPermission(
                object_id=p["object_id"],
                object_type=MetadataType(p["object_type"]),
                principal_id=p["principal_id"],
                principal_name=p["principal_name"],
                principal_type=PrincipalType(p["principal_type"]),
                permission=PermissionType(p["permission"]),
            )
            for p in raw.get("permissions", [])
        ]
        return MigrationBundle(groups=groups, users=users, objects=objects, permissions=permissions)
