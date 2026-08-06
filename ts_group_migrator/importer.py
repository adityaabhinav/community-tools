"""Apply a MigrationBundle to the destination ThoughtSpot cluster."""

from __future__ import annotations
import logging
from collections import defaultdict
from typing import Dict, List, Optional

from .client import ThoughtSpotClient
from .models import (
    IMPORT_ORDER,
    MigrationBundle,
    MetadataType,
    PermissionType,
    PrincipalType,
    TSGroup,
    TSObject,
    TSPermission,
    TSUser,
)

logger = logging.getLogger(__name__)

# Map from source-cluster principal name → destination-cluster id
_NameToId = Dict[str, str]


class ImportResult:
    def __init__(self) -> None:
        self.created_groups: List[str] = []
        self.skipped_groups: List[str] = []
        self.created_users: List[str] = []
        self.skipped_users: List[str] = []
        self.imported_objects: List[str] = []
        self.failed_objects: List[str] = []
        self.permissions_applied: int = 0
        self.ownership_transferred: int = 0

    def summary(self) -> str:
        return (
            f"Groups created={len(self.created_groups)} skipped={len(self.skipped_groups)} | "
            f"Users created={len(self.created_users)} skipped={len(self.skipped_users)} | "
            f"Objects imported={len(self.imported_objects)} failed={len(self.failed_objects)} | "
            f"Permissions={self.permissions_applied} Ownership transfers={self.ownership_transferred}"
        )


class Importer:
    """Applies a MigrationBundle to a destination ThoughtSpot cluster."""

    def __init__(self, client: ThoughtSpotClient, default_password: str = "Changeme@123"):
        self._c = client
        self._default_password = default_password

    def apply(self, bundle: MigrationBundle) -> ImportResult:
        result = ImportResult()

        # 1. Groups
        logger.info("Creating groups")
        group_name_to_dest_id = self._create_groups(bundle.groups, result)

        # 2. Users
        logger.info("Creating users")
        user_name_to_dest_id = self._create_users(bundle.users, result)

        # 3. Objects (TML import, ordered by type dependency)
        logger.info("Importing objects")
        src_id_to_dest_id, src_name_to_author = self._import_objects(bundle.objects, result)

        # 4. Permissions
        logger.info("Applying permissions")
        self._apply_permissions(
            bundle.permissions,
            src_id_to_dest_id,
            group_name_to_dest_id,
            user_name_to_dest_id,
            result,
        )

        # 5. Ownership transfer
        logger.info("Transferring ownership")
        self._transfer_ownership(bundle.objects, src_id_to_dest_id, result)

        logger.info("Import complete: %s", result.summary())
        return result

    # ---------------------------------------------------------------- groups

    def _create_groups(self, groups: List[TSGroup], result: ImportResult) -> _NameToId:
        name_to_id: _NameToId = {}

        # Look up existing groups first to avoid duplicates
        existing = {g.get("name", ""): g.get("id", "") for g in self._c.search_groups()}
        name_to_id.update(existing)

        # Create in dependency order: parent groups before child groups
        ordered = _topological_sort_groups(groups)

        for group in ordered:
            if group.name in existing:
                logger.debug("Group already exists, skipping: %s", group.name)
                result.skipped_groups.append(group.name)
                continue
            try:
                resp = self._c.create_group(
                    {
                        "name": group.name,
                        "display_name": group.display_name or group.name,
                        "description": group.description,
                        "visibility": group.visibility,
                        "privileges": group.privileges,
                        "group_names": group.sub_group_names,
                    }
                )
                gid = resp.get("id", "")
                name_to_id[group.name] = gid
                result.created_groups.append(group.name)
                logger.info("Created group: %s", group.name)
            except Exception as exc:
                logger.error("Failed to create group %s: %s", group.name, exc)
                result.skipped_groups.append(group.name)

        return name_to_id

    # ----------------------------------------------------------------- users

    def _create_users(self, users: List[TSUser], result: ImportResult) -> _NameToId:
        name_to_id: _NameToId = {}

        existing = {u.get("name", ""): u.get("id", "") for u in self._c.search_users()}
        name_to_id.update(existing)

        for user in users:
            if user.name in existing:
                logger.debug("User already exists, skipping: %s", user.name)
                result.skipped_users.append(user.name)
                continue
            try:
                resp = self._c.create_user(
                    {
                        "name": user.name,
                        "display_name": user.display_name or user.name,
                        "email": user.email,
                        "account_type": user.account_type,
                        "password": self._default_password,
                        "group_names": user.group_names,
                    }
                )
                uid = resp.get("id", "")
                name_to_id[user.name] = uid
                result.created_users.append(user.name)
                logger.info("Created user: %s", user.name)
            except Exception as exc:
                logger.error("Failed to create user %s: %s", user.name, exc)
                result.skipped_users.append(user.name)

        return name_to_id

    # --------------------------------------------------------------- objects

    def _import_objects(
        self,
        objects: List[TSObject],
        result: ImportResult,
    ) -> tuple[Dict[str, str], Dict[str, str]]:
        """Returns (src_id → dest_id mapping, src_id → author_name mapping)."""
        src_id_to_dest_id: Dict[str, str] = {}
        src_id_to_author: Dict[str, str] = {o.id: o.author_name for o in objects}

        # Group objects by type and import in dependency order
        by_type: Dict[MetadataType, List[TSObject]] = defaultdict(list)
        for obj in objects:
            by_type[obj.type].append(obj)

        for mtype in IMPORT_ORDER:
            batch = by_type.get(mtype, [])
            if not batch:
                continue
            logger.info("Importing %d %s object(s)", len(batch), mtype.value)

            # Import individually to capture per-object results and IDs
            for obj in batch:
                if not obj.tml:
                    logger.warning("Skipping %s — no TML available", obj.name)
                    result.failed_objects.append(obj.name)
                    continue
                try:
                    responses = self._c.import_tml([obj.tml], force_create=True)
                    dest_id = _extract_dest_id(responses)
                    if dest_id:
                        src_id_to_dest_id[obj.id] = dest_id
                        result.imported_objects.append(obj.name)
                        logger.info("Imported %s → dest id %s", obj.name, dest_id)
                    else:
                        logger.error("No dest id returned for %s; response: %s", obj.name, responses)
                        result.failed_objects.append(obj.name)
                except Exception as exc:
                    logger.error("Failed to import %s: %s", obj.name, exc)
                    result.failed_objects.append(obj.name)

        return src_id_to_dest_id, src_id_to_author

    # ----------------------------------------------------------- permissions

    def _apply_permissions(
        self,
        permissions: List[TSPermission],
        src_id_to_dest_id: Dict[str, str],
        group_name_to_id: _NameToId,
        user_name_to_id: _NameToId,
        result: ImportResult,
    ) -> None:
        # Group permissions by (dest_object_id, object_type)
        by_object: Dict[tuple, List[dict]] = defaultdict(list)

        for perm in permissions:
            dest_oid = src_id_to_dest_id.get(perm.object_id)
            if not dest_oid:
                continue

            if perm.principal_type == PrincipalType.GROUP:
                principal_dest_id = group_name_to_id.get(perm.principal_name)
            else:
                principal_dest_id = user_name_to_id.get(perm.principal_name)

            if not principal_dest_id:
                logger.warning("Cannot resolve principal %s on destination, skipping", perm.principal_name)
                continue

            by_object[(dest_oid, perm.object_type.value)].append(
                {
                    "principal_id": principal_dest_id,
                    "principal_type": perm.principal_type.value,
                    "share_mode": perm.permission.value,
                }
            )

        for (dest_oid, type_str), perms in by_object.items():
            try:
                self._c.share_objects(
                    metadata=[{"identifier": dest_oid, "type": type_str}],
                    permissions=perms,
                )
                result.permissions_applied += len(perms)
                logger.debug("Applied %d permission(s) to %s", len(perms), dest_oid)
            except Exception as exc:
                logger.error("Failed to apply permissions to %s: %s", dest_oid, exc)

    # ------------------------------------------------------- ownership

    def _transfer_ownership(
        self,
        objects: List[TSObject],
        src_id_to_dest_id: Dict[str, str],
        result: ImportResult,
    ) -> None:
        # Group dest IDs by author username
        by_author: Dict[str, List[str]] = defaultdict(list)
        for obj in objects:
            dest_id = src_id_to_dest_id.get(obj.id)
            if dest_id and obj.author_name:
                by_author[obj.author_name].append(dest_id)

        # Objects are imported under the calling admin user; transfer to original owner
        admin_user = self._c.config.username
        for author_name, dest_ids in by_author.items():
            if author_name == admin_user:
                continue  # already owned by admin, nothing to transfer
            try:
                self._c.transfer_ownership(
                    from_username=admin_user,
                    to_username=author_name,
                    object_ids=dest_ids,
                )
                result.ownership_transferred += len(dest_ids)
                logger.info("Transferred %d object(s) to %s", len(dest_ids), author_name)
            except Exception as exc:
                logger.error("Ownership transfer to %s failed: %s", author_name, exc)


# ------------------------------------------------------------------ helpers

def _extract_dest_id(responses: List[dict]) -> Optional[str]:
    """Pull the newly created object GUID from a TML import response."""
    for item in responses:
        resp = item.get("response", item)  # v2 wraps in 'response'
        status = resp.get("status", {}).get("status_code", "")
        if status == "OK":
            return resp.get("header", {}).get("id_guid", "")
    return None


def _topological_sort_groups(groups: List[TSGroup]) -> List[TSGroup]:
    """Sort groups so that parent groups (no sub-group deps yet to be created) come first."""
    name_set = {g.name for g in groups}
    by_name = {g.name: g for g in groups}

    visited: set = set()
    result: List[TSGroup] = []

    def visit(name: str) -> None:
        if name in visited or name not in by_name:
            return
        visited.add(name)
        g = by_name[name]
        # Visit sub-groups that are in our migration set first
        for sub in g.sub_group_names:
            if sub in name_set:
                visit(sub)
        result.append(g)

    for group in groups:
        visit(group.name)

    return result
