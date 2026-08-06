"""Tests for Exporter — verifies group BFS, user collection, object collection, permissions."""

import unittest
from unittest.mock import MagicMock, patch

from ts_group_migrator.exporter import Exporter, _parse_group, _parse_user, _parse_object_header
from ts_group_migrator.models import MetadataType, PermissionType, PrincipalType


def _mock_client():
    return MagicMock()


class TestParseGroup(unittest.TestCase):
    def test_basic_fields(self):
        raw = {
            "id": "g1", "name": "Sales", "display_name": "Sales Team",
            "description": "desc", "visibility": "SHARABLE",
            "privileges": ["JOBSCHEDULING"],
            "groups": [{"id": "sg1", "name": "APAC Sales"}],
        }
        g = _parse_group(raw)
        self.assertEqual(g.id, "g1")
        self.assertEqual(g.name, "Sales")
        self.assertEqual(g.sub_group_names, ["APAC Sales"])
        self.assertIn("JOBSCHEDULING", g.privileges)

    def test_missing_optional_fields(self):
        raw = {"id": "g2", "name": "Marketing"}
        g = _parse_group(raw)
        self.assertEqual(g.display_name, "Marketing")
        self.assertEqual(g.sub_group_names, [])


class TestParseUser(unittest.TestCase):
    def test_filters_groups_to_known_set(self):
        raw = {
            "id": "u1", "name": "alice", "display_name": "Alice A",
            "email": "alice@x.com", "account_type": "LOCAL_USER", "account_status": "ACTIVE",
            "groups": [{"name": "Sales"}, {"name": "AllUsers"}],
        }
        u = _parse_user(raw, keep_group_names={"Sales"})
        self.assertEqual(u.group_names, ["Sales"])
        self.assertNotIn("AllUsers", u.group_names)


class TestParseObjectHeader(unittest.TestCase):
    def test_liveboard(self):
        raw = {
            "metadata_id": "lb1", "metadata_name": "Q3 Sales", "metadata_type": "LIVEBOARD",
            "author_id": "u1", "author_name": "alice",
        }
        o = _parse_object_header(raw)
        self.assertEqual(o.type, MetadataType.LIVEBOARD)
        self.assertEqual(o.id, "lb1")

    def test_unknown_type_defaults_to_liveboard(self):
        raw = {"metadata_id": "x", "metadata_name": "x", "metadata_type": "UNKNOWN_FUTURE_TYPE",
               "author_id": "u1", "author_name": "alice"}
        o = _parse_object_header(raw)
        self.assertEqual(o.type, MetadataType.LIVEBOARD)


class TestExporterCollectGroups(unittest.TestCase):
    def test_bfs_traverses_sub_groups(self):
        client = _mock_client()
        # Root group has one sub-group; sub-group has no further sub-groups
        client.search_groups.side_effect = lambda group_identifier=None: (
            [{"id": "g1", "name": "Sales", "display_name": "Sales", "description": "",
              "visibility": "SHARABLE", "privileges": [],
              "groups": [{"id": "sg1", "name": "APAC Sales"}]}]
            if group_identifier == "Sales"
            else [{"id": "sg1", "name": "APAC Sales", "display_name": "APAC Sales",
                   "description": "", "visibility": "SHARABLE", "privileges": [], "groups": []}]
        )

        exp = Exporter(client)
        groups = exp._collect_groups("Sales")
        self.assertEqual({g.name for g in groups}, {"Sales", "APAC Sales"})

    def test_handles_missing_group(self):
        client = _mock_client()
        client.search_groups.return_value = []
        exp = Exporter(client)
        groups = exp._collect_groups("NonExistent")
        self.assertEqual(groups, [])

    def test_no_infinite_loop_on_circular_reference(self):
        client = _mock_client()
        # Group A references B, B references A
        def side_effect(group_identifier=None):
            if group_identifier == "A":
                return [{"id": "ga", "name": "A", "display_name": "A", "description": "",
                         "visibility": "SHARABLE", "privileges": [], "groups": [{"id": "gb", "name": "B"}]}]
            return [{"id": "gb", "name": "B", "display_name": "B", "description": "",
                     "visibility": "SHARABLE", "privileges": [], "groups": [{"id": "ga", "name": "A"}]}]
        client.search_groups.side_effect = side_effect
        exp = Exporter(client)
        groups = exp._collect_groups("A")
        # Should terminate and return both groups exactly once
        self.assertEqual(len(groups), 2)


class TestExporterCollectUsers(unittest.TestCase):
    def test_deduplicates_users(self):
        client = _mock_client()
        user = {"id": "u1", "name": "alice", "display_name": "Alice",
                "email": "", "account_type": "LOCAL_USER", "account_status": "ACTIVE",
                "groups": [{"name": "Sales"}]}
        client.search_users.return_value = [user, user]  # duplicate
        exp = Exporter(client)
        users = exp._collect_users(["g1"], {"Sales"})
        self.assertEqual(len(users), 1)


class TestExporterEnrichWithTml(unittest.TestCase):
    def _make_object(self, oid, name, otype=MetadataType.LIVEBOARD):
        from ts_group_migrator.models import TSObject
        return TSObject(id=oid, name=name, type=otype, author_id="u1", author_name="alice")

    def test_enriches_objects_with_tml(self):
        client = _mock_client()
        client.export_tml.return_value = [
            {"status": {"status_code": "OK"}, "edoc": "liveboard:\n  name: LB1",
             "info": {"id": "lb1"}}
        ]
        obj = self._make_object("lb1", "LB1")
        exp = Exporter(client)
        result = exp._enrich_with_tml([obj])
        self.assertEqual(result[0].tml, "liveboard:\n  name: LB1")

    def test_drops_objects_without_tml(self):
        client = _mock_client()
        client.export_tml.return_value = [
            {"status": {"status_code": "ERROR"}, "edoc": "", "info": {"id": "lb1"}}
        ]
        obj = self._make_object("lb1", "LB1")
        exp = Exporter(client)
        result = exp._enrich_with_tml([obj])
        # Object with empty TML should be dropped
        self.assertEqual(len(result), 0)

    def test_handles_export_api_error(self):
        client = _mock_client()
        client.export_tml.side_effect = Exception("API error")
        obj = self._make_object("lb1", "LB1")
        exp = Exporter(client)
        result = exp._enrich_with_tml([obj])
        # Should return original list (with empty TML), not crash
        self.assertEqual(result[0].tml, "")


class TestExporterCollectPermissions(unittest.TestCase):
    def test_filters_to_known_principals(self):
        client = _mock_client()
        client.fetch_permissions.return_value = [
            {
                "metadata_id": "lb1", "metadata_type": "LIVEBOARD",
                "permissions": [
                    {"principal_id": "g1", "principal_name": "Sales",
                     "principal_type": "USER_GROUP", "permission_type": "READ_ONLY"},
                    {"principal_id": "x", "principal_name": "OtherGroup",
                     "principal_type": "USER_GROUP", "permission_type": "MODIFY"},
                ],
            }
        ]
        from ts_group_migrator.models import TSObject
        obj = TSObject(id="lb1", name="LB1", type=MetadataType.LIVEBOARD, author_id="u1", author_name="alice")
        exp = Exporter(client)
        perms = exp._collect_permissions([obj], group_names={"Sales"}, user_names=set())
        self.assertEqual(len(perms), 1)
        self.assertEqual(perms[0].principal_name, "Sales")
        self.assertEqual(perms[0].permission, PermissionType.READ_ONLY)


if __name__ == "__main__":
    unittest.main()
