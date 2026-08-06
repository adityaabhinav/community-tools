"""Read all groups, users, objects, and permissions from the source cluster."""

from __future__ import annotations
import logging
from typing import List, Set

from .client import ThoughtSpotClient
from .models import (
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

_MIGRATABLE_TYPES = [
    MetadataType.LIVEBOARD.value,
    MetadataType.ANSWER.value,
    MetadataType.LOGICAL_TABLE.value,
]


class Exporter:
    """Collects everything needed for migration from a source ThoughtSpot cluster."""

    def __init__(self, client: ThoughtSpotClient):
        self._c = client

    def export(self, root_group_name: str) -> MigrationBundle:
        bundle = MigrationBundle()

        # 1. Collect group tree
        logger.info("Collecting groups rooted at '%s'", root_group_name)
        bundle.groups = self._collect_groups(root_group_name)
        group_names = {g.name for g in bundle.groups}
        group_ids = {g.id for g in bundle.groups}
        logger.info("Found %d group(s)", len(bundle.groups))

        # 2. Collect users who belong to any of those groups
        logger.info("Collecting users in %d group(s)", len(group_ids))
        bundle.users = self._collect_users(list(group_ids), group_names)
        user_ids = {u.id for u in bundle.users}
        user_names = {u.name for u in bundle.users}
        logger.info("Found %d user(s)", len(bundle.users))

        # 3. Collect objects owned by those users OR shared with those groups
        logger.info("Collecting metadata objects")
        bundle.objects = self._collect_objects(list(user_ids), list(group_ids))
        logger.info("Found %d object(s)", len(bundle.objects))

        # 4. Collect permissions for all collected objects
        logger.info("Collecting permissions")
        bundle.permissions = self._collect_permissions(bundle.objects, group_names, user_names)
        logger.info("Found %d permission entries", len(bundle.permissions))

        return bundle

    # ---------------------------------------------------------------- groups

    def _collect_groups(self, root_name: str) -> List[TSGroup]:
        """BFS over the group hierarchy starting from root_name."""
        visited: Set[str] = set()
        result: List[TSGroup] = []
        queue = [root_name]

        while queue:
            name = queue.pop(0)
            if name in visited:
                continue
            visited.add(name)

            raw_list = self._c.search_groups(group_identifier=name)
            if not raw_list:
                logger.warning("Group not found: %s", name)
                continue

            for raw in raw_list:
                g = _parse_group(raw)
                result.append(g)
                # Enqueue sub-groups for recursive collection
                for sub in g.sub_group_names:
                    if sub not in visited:
                        queue.append(sub)

        return result

    # ----------------------------------------------------------------- users

    def _collect_users(self, group_ids: List[str], group_names: Set[str]) -> List[TSUser]:
        raw_users = self._c.search_users(group_identifiers=group_ids)
        users: List[TSUser] = []
        seen: Set[str] = set()
        for raw in raw_users:
            uid = raw.get("id", "")
            if uid in seen:
                continue
            seen.add(uid)
            u = _parse_user(raw, group_names)
            users.append(u)
        return users

    # --------------------------------------------------------------- objects

    def _collect_objects(self, user_ids: List[str], group_ids: List[str]) -> List[TSObject]:
        seen: Set[str] = set()
        objects: List[TSObject] = []

        # Objects owned by users in the group
        owned_raw = self._c.search_metadata(
            _MIGRATABLE_TYPES,
            created_by_user_identifiers=user_ids,
        )
        for raw in owned_raw:
            oid = raw.get("metadata_id", "")
            if oid and oid not in seen:
                seen.add(oid)
                objects.append(_parse_object_header(raw))

        # Objects explicitly shared with the groups
        shared_raw = self._c.search_metadata(
            _MIGRATABLE_TYPES,
            permission_filter_type="DEFINED",
            group_identifiers=group_ids,
        )
        for raw in shared_raw:
            oid = raw.get("metadata_id", "")
            if oid and oid not in seen:
                seen.add(oid)
                objects.append(_parse_object_header(raw))

        # Export TML for all collected objects
        return self._enrich_with_tml(objects)

    def _enrich_with_tml(self, objects: List[TSObject]) -> List[TSObject]:
        if not objects:
            return objects

        metadata_refs = [{"identifier": o.id, "type": o.type.value} for o in objects]
        try:
            tml_responses = self._c.export_tml(metadata_refs, export_associated=False)
        except Exception as exc:
            logger.error("TML export failed: %s", exc)
            return objects

        tml_by_id: dict = {}
        for item in tml_responses:
            status = item.get("status", {}).get("status_code", "")
            if status == "OK":
                # TML responses don't always carry the source GUID back directly;
                # match by position when the list order matches the request order.
                tml_by_id[item.get("info", {}).get("id", "")] = item.get("edoc", "")

        for obj in objects:
            tml = tml_by_id.get(obj.id, "")
            if tml:
                obj.tml = tml
            else:
                logger.warning("No TML exported for %s (%s)", obj.name, obj.id)

        return [o for o in objects if o.tml]  # drop objects with no TML

    # ----------------------------------------------------------- permissions

    def _collect_permissions(
        self,
        objects: List[TSObject],
        group_names: Set[str],
        user_names: Set[str],
    ) -> List[TSPermission]:
        if not objects:
            return []

        metadata_refs = [{"identifier": o.id, "type": o.type.value} for o in objects]
        try:
            perm_responses = self._c.fetch_permissions(metadata_refs)
        except Exception as exc:
            logger.error("Permission fetch failed: %s", exc)
            return []

        permissions: List[TSPermission] = []
        for item in perm_responses:
            oid = item.get("metadata_id", "")
            otype_str = item.get("metadata_type", "")
            try:
                otype = MetadataType(otype_str)
            except ValueError:
                continue

            for perm in item.get("permissions", []):
                principal_name = perm.get("principal_name", "")
                # Only carry over permissions for principals in our migration set
                if principal_name not in group_names and principal_name not in user_names:
                    continue
                try:
                    ptype = PrincipalType(perm.get("principal_type", ""))
                    perm_type = PermissionType(perm.get("permission_type", ""))
                except ValueError:
                    continue

                permissions.append(
                    TSPermission(
                        object_id=oid,
                        object_type=otype,
                        principal_id=perm.get("principal_id", ""),
                        principal_name=principal_name,
                        principal_type=ptype,
                        permission=perm_type,
                    )
                )

        return permissions


# ------------------------------------------------------------------ parsers

def _parse_group(raw: dict) -> TSGroup:
    return TSGroup(
        id=raw.get("id", ""),
        name=raw.get("name", ""),
        display_name=raw.get("display_name", raw.get("name", "")),
        description=raw.get("description", ""),
        visibility=raw.get("visibility", "SHARABLE"),
        privileges=raw.get("privileges", []),
        sub_group_names=[g.get("name", "") for g in raw.get("groups", [])],
    )


def _parse_user(raw: dict, keep_group_names: Set[str]) -> TSUser:
    all_groups = [g.get("name", "") for g in raw.get("groups", [])]
    return TSUser(
        id=raw.get("id", ""),
        name=raw.get("name", ""),
        display_name=raw.get("display_name", raw.get("name", "")),
        email=raw.get("email", ""),
        account_type=raw.get("account_type", "LOCAL_USER"),
        account_status=raw.get("account_status", "ACTIVE"),
        group_names=[g for g in all_groups if g in keep_group_names],
    )


def _parse_object_header(raw: dict) -> TSObject:
    type_str = raw.get("metadata_type", "LIVEBOARD")
    try:
        obj_type = MetadataType(type_str)
    except ValueError:
        obj_type = MetadataType.LIVEBOARD
    return TSObject(
        id=raw.get("metadata_id", ""),
        name=raw.get("metadata_name", ""),
        type=obj_type,
        author_id=raw.get("author_id", ""),
        author_name=raw.get("author_name", ""),
    )
