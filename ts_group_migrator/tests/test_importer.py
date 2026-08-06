"""Tests for Importer — group/user creation, TML import, permissions, ownership."""

import unittest
from unittest.mock import MagicMock, call, patch

from ts_group_migrator.importer import Importer, ImportResult, _extract_dest_id, _topological_sort_groups
from ts_group_migrator.models import (
    MetadataType, MigrationBundle, PermissionType, PrincipalType,
    TSGroup, TSObject, TSPermission, TSUser,
)


def _mock_client(existing_groups=None, existing_users=None):
    c = MagicMock()
    c.search_groups.return_value = existing_groups or []
    c.search_users.return_value = existing_users or []
    c.create_group.return_value = {"id": "new-group-id"}
    c.create_user.return_value = {"id": "new-user-id"}
    c.import_tml.return_value = [
        {"response": {"status": {"status_code": "OK"}, "header": {"id_guid": "dest-obj-id"}}}
    ]
    c.config = MagicMock()
    c.config.username = "admin"
    return c


def _group(name, subs=None):
    return TSGroup(id=f"id-{name}", name=name, display_name=name, sub_group_names=subs or [])


def _user(name, groups=None):
    return TSUser(id=f"id-{name}", name=name, display_name=name, group_names=groups or [])


def _obj(oid, name, otype=MetadataType.LIVEBOARD, author="alice"):
    return TSObject(id=oid, name=name, type=otype, author_id=f"id-{author}", author_name=author, tml="liveboard:\n  name: x")


class TestCreateGroups(unittest.TestCase):
    def test_creates_new_group(self):
        client = _mock_client()
        imp = Importer(client)
        result = ImportResult()
        imp._create_groups([_group("Sales")], result)
        client.create_group.assert_called_once()
        self.assertIn("Sales", result.created_groups)

    def test_skips_existing_group(self):
        client = _mock_client(existing_groups=[{"name": "Sales", "id": "existing-id"}])
        imp = Importer(client)
        result = ImportResult()
        imp._create_groups([_group("Sales")], result)
        client.create_group.assert_not_called()
        self.assertIn("Sales", result.skipped_groups)

    def test_handles_create_error_gracefully(self):
        client = _mock_client()
        client.create_group.side_effect = Exception("API error")
        imp = Importer(client)
        result = ImportResult()
        imp._create_groups([_group("BadGroup")], result)
        self.assertIn("BadGroup", result.skipped_groups)
        self.assertNotIn("BadGroup", result.created_groups)


class TestCreateUsers(unittest.TestCase):
    def test_creates_new_user(self):
        client = _mock_client()
        imp = Importer(client)
        result = ImportResult()
        imp._create_users([_user("alice", ["Sales"])], result)
        client.create_user.assert_called_once()
        payload = client.create_user.call_args[0][0]
        self.assertEqual(payload["name"], "alice")
        self.assertIn("Sales", payload["group_names"])
        self.assertIn("alice", result.created_users)

    def test_skips_existing_user(self):
        client = _mock_client(existing_users=[{"name": "alice", "id": "u1"}])
        imp = Importer(client)
        result = ImportResult()
        imp._create_users([_user("alice")], result)
        client.create_user.assert_not_called()
        self.assertIn("alice", result.skipped_users)

    def test_uses_default_password(self):
        client = _mock_client()
        imp = Importer(client, default_password="Test@456")
        result = ImportResult()
        imp._create_users([_user("bob")], result)
        payload = client.create_user.call_args[0][0]
        self.assertEqual(payload["password"], "Test@456")


class TestImportObjects(unittest.TestCase):
    def test_imports_in_dependency_order(self):
        client = _mock_client()
        call_order = []

        def track_import(tml_list, force_create=True):
            call_order.append(tml_list[0][:20])
            return [{"response": {"status": {"status_code": "OK"}, "header": {"id_guid": f"dest-{len(call_order)}"}}}]

        client.import_tml.side_effect = track_import

        objects = [
            TSObject(id="lb1", name="Liveboard", type=MetadataType.LIVEBOARD, author_id="u1", author_name="alice", tml="liveboard: x"),
            TSObject(id="lt1", name="Worksheet", type=MetadataType.LOGICAL_TABLE, author_id="u1", author_name="alice", tml="worksheet: x"),
            TSObject(id="ans1", name="Answer", type=MetadataType.ANSWER, author_id="u1", author_name="alice", tml="answer: x"),
        ]
        imp = Importer(client)
        result = ImportResult()
        src_to_dest, _ = imp._import_objects(objects, result)

        # Worksheet should be imported before Answer, Answer before Liveboard
        self.assertEqual(call_order[0], "worksheet: x"[:20])
        self.assertEqual(call_order[1], "answer: x"[:20])
        self.assertEqual(call_order[2], "liveboard: x"[:20])
        self.assertEqual(len(result.imported_objects), 3)

    def test_skips_objects_without_tml(self):
        client = _mock_client()
        obj = TSObject(id="lb1", name="NoBML", type=MetadataType.LIVEBOARD,
                       author_id="u1", author_name="alice", tml="")
        imp = Importer(client)
        result = ImportResult()
        imp._import_objects([obj], result)
        client.import_tml.assert_not_called()
        self.assertIn("NoBML", result.failed_objects)

    def test_handles_import_error(self):
        client = _mock_client()
        client.import_tml.side_effect = Exception("500 Server Error")
        obj = _obj("lb1", "LB1")
        imp = Importer(client)
        result = ImportResult()
        imp._import_objects([obj], result)
        self.assertIn("LB1", result.failed_objects)
        self.assertNotIn("LB1", result.imported_objects)


class TestApplyPermissions(unittest.TestCase):
    def test_shares_with_resolved_principal(self):
        client = _mock_client()
        perm = TSPermission(
            object_id="src-lb1", object_type=MetadataType.LIVEBOARD,
            principal_id="src-g1", principal_name="Sales",
            principal_type=PrincipalType.GROUP, permission=PermissionType.READ_ONLY,
        )
        imp = Importer(client)
        result = ImportResult()
        imp._apply_permissions(
            [perm],
            src_id_to_dest_id={"src-lb1": "dest-lb1"},
            group_name_to_id={"Sales": "dest-g1"},
            user_name_to_id={},
            result=result,
        )
        client.share_objects.assert_called_once()
        _, kwargs = client.share_objects.call_args
        self.assertEqual(kwargs["metadata"][0]["identifier"], "dest-lb1")
        self.assertEqual(kwargs["permissions"][0]["share_mode"], "READ_ONLY")
        self.assertEqual(result.permissions_applied, 1)

    def test_skips_unmapped_object(self):
        client = _mock_client()
        perm = TSPermission(
            object_id="unmapped-id", object_type=MetadataType.LIVEBOARD,
            principal_id="g1", principal_name="Sales",
            principal_type=PrincipalType.GROUP, permission=PermissionType.READ_ONLY,
        )
        imp = Importer(client)
        result = ImportResult()
        imp._apply_permissions([perm], {}, {"Sales": "dest-g1"}, {}, result)
        client.share_objects.assert_not_called()

    def test_skips_unknown_principal(self):
        client = _mock_client()
        perm = TSPermission(
            object_id="src-lb1", object_type=MetadataType.LIVEBOARD,
            principal_id="g1", principal_name="UnknownGroup",
            principal_type=PrincipalType.GROUP, permission=PermissionType.READ_ONLY,
        )
        imp = Importer(client)
        result = ImportResult()
        imp._apply_permissions([perm], {"src-lb1": "dest-lb1"}, {}, {}, result)
        client.share_objects.assert_not_called()


class TestTransferOwnership(unittest.TestCase):
    def test_transfers_to_non_admin_authors(self):
        client = _mock_client()
        client.config.username = "admin"
        objects = [_obj("lb1", "LB1", author="alice"), _obj("lb2", "LB2", author="bob")]
        imp = Importer(client)
        result = ImportResult()
        imp._transfer_ownership(
            objects,
            src_id_to_dest_id={"lb1": "dest-lb1", "lb2": "dest-lb2"},
            result=result,
        )
        # Should call transfer for alice and bob separately
        self.assertEqual(client.transfer_ownership.call_count, 2)
        self.assertEqual(result.ownership_transferred, 2)

    def test_skips_objects_owned_by_admin(self):
        client = _mock_client()
        client.config.username = "admin"
        obj = _obj("lb1", "LB1", author="admin")
        imp = Importer(client)
        result = ImportResult()
        imp._transfer_ownership([obj], src_id_to_dest_id={"lb1": "dest-lb1"}, result=result)
        client.transfer_ownership.assert_not_called()

    def test_handles_transfer_error_gracefully(self):
        client = _mock_client()
        client.config.username = "admin"
        client.transfer_ownership.side_effect = Exception("user not found")
        obj = _obj("lb1", "LB1", author="alice")
        imp = Importer(client)
        result = ImportResult()
        # Should not raise
        imp._transfer_ownership([obj], src_id_to_dest_id={"lb1": "dest-lb1"}, result=result)
        self.assertEqual(result.ownership_transferred, 0)


class TestExtractDestId(unittest.TestCase):
    def test_extracts_id_from_ok_response(self):
        responses = [{"response": {"status": {"status_code": "OK"}, "header": {"id_guid": "abc123"}}}]
        self.assertEqual(_extract_dest_id(responses), "abc123")

    def test_returns_none_for_error_response(self):
        responses = [{"response": {"status": {"status_code": "ERROR"}, "header": {}}}]
        self.assertIsNone(_extract_dest_id(responses))

    def test_returns_none_for_empty_list(self):
        self.assertIsNone(_extract_dest_id([]))


class TestTopologicalSortGroups(unittest.TestCase):
    def test_parent_after_children(self):
        # Parent "Sales" has sub-group "APAC Sales"
        parent = TSGroup(id="g1", name="Sales", sub_group_names=["APAC Sales"])
        child = TSGroup(id="g2", name="APAC Sales", sub_group_names=[])
        sorted_groups = _topological_sort_groups([parent, child])
        names = [g.name for g in sorted_groups]
        # Child (APAC Sales) should come before parent (Sales) for creation order
        self.assertLess(names.index("APAC Sales"), names.index("Sales"))

    def test_no_crash_on_missing_sub_group(self):
        # Sub-group not in the migration set — should not crash
        g = TSGroup(id="g1", name="Sales", sub_group_names=["ExternalGroup"])
        result = _topological_sort_groups([g])
        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
