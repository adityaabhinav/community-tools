"""Data models for the ThoughtSpot group migrator."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class PermissionType(str, Enum):
    READ_ONLY = "READ_ONLY"
    MODIFY = "MODIFY"
    NO_ACCESS = "NO_ACCESS"


class PrincipalType(str, Enum):
    USER = "USER"
    GROUP = "USER_GROUP"


class MetadataType(str, Enum):
    LIVEBOARD = "LIVEBOARD"
    ANSWER = "ANSWER"
    LOGICAL_TABLE = "LOGICAL_TABLE"
    CONNECTION = "CONNECTION"


# Dependency import order: connections first, then tables, then answers, then liveboards
IMPORT_ORDER = [
    MetadataType.CONNECTION,
    MetadataType.LOGICAL_TABLE,
    MetadataType.ANSWER,
    MetadataType.LIVEBOARD,
]


@dataclass
class TSGroup:
    id: str
    name: str
    display_name: str = ""
    description: str = ""
    visibility: str = "SHARABLE"
    privileges: List[str] = field(default_factory=list)
    sub_group_names: List[str] = field(default_factory=list)


@dataclass
class TSUser:
    id: str
    name: str
    display_name: str = ""
    email: str = ""
    account_type: str = "LOCAL_USER"
    account_status: str = "ACTIVE"
    group_names: List[str] = field(default_factory=list)


@dataclass
class TSObject:
    id: str
    name: str
    type: MetadataType
    author_id: str
    author_name: str
    tml: str = ""  # raw TML string


@dataclass
class TSPermission:
    object_id: str
    object_type: MetadataType
    principal_id: str
    principal_name: str
    principal_type: PrincipalType
    permission: PermissionType


@dataclass
class MigrationBundle:
    """Everything collected from the source cluster, ready to apply to destination."""
    groups: List[TSGroup] = field(default_factory=list)
    users: List[TSUser] = field(default_factory=list)
    objects: List[TSObject] = field(default_factory=list)
    permissions: List[TSPermission] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Groups: {len(self.groups)}, Users: {len(self.users)}, "
            f"Objects: {len(self.objects)}, Permission entries: {len(self.permissions)}"
        )
