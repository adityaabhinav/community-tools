"""Tests for GroupMigrator — end-to-end flow with mocked export/import phases."""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from ts_group_migrator.client import TSConfig
from ts_group_migrator.migrator import GroupMigrator
from ts_group_migrator.models import (
    MetadataType, MigrationBundle, PermissionType, PrincipalType,
    TSGroup, TSObject, TSPermission, TSUser,
)


def _cfg(url="https://src.example.com"):
    return TSConfig(url=url, username="admin", password="secret")


def _make_bundle():
    return MigrationBundle(
        groups=[TSGroup(id="g1", name="Sales", display_name="Sales Team")],
        users=[TSUser(id="u1", name="alice", display_name="Alice", group_names=["Sales"])],
        objects=[
            TSObject(
                id="lb1", name="Q3 Liveboard", type=MetadataType.LIVEBOARD,
                author_id="u1", author_name="alice", tml="liveboard:\n  name: Q3 Liveboard",
            )
        ],
        permissions=[
            TSPermission(
                object_id="lb1", object_type=MetadataType.LIVEBOARD,
                principal_id="g1", principal_name="Sales",
                principal_type=PrincipalType.GROUP, permission=PermissionType.READ_ONLY,
            )
        ],
    )


class TestGroupMigratorMigrate(unittest.TestCase):
    @patch("ts_group_migrator.migrator.Importer")
    @patch("ts_group_migrator.migrator.Exporter")
    @patch("ts_group_migrator.migrator.ThoughtSpotClient")
    def test_full_pipeline_called(self, MockClient, MockExporter, MockImporter):
        bundle = _make_bundle()
        mock_ctx = MagicMock()
        MockClient.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        mock_exporter_inst = MagicMock()
        mock_exporter_inst.export.return_value = bundle
        MockExporter.return_value = mock_exporter_inst

        from ts_group_migrator.importer import ImportResult
        mock_result = ImportResult()
        mock_result.created_groups = ["Sales"]
        mock_result.created_users = ["alice"]
        mock_result.imported_objects = ["Q3 Liveboard"]
        mock_importer_inst = MagicMock()
        mock_importer_inst.apply.return_value = mock_result
        MockImporter.return_value = mock_importer_inst

        migrator = GroupMigrator(source=_cfg(), destination=_cfg("https://dst.example.com"))
        result = migrator.migrate("Sales")

        mock_exporter_inst.export.assert_called_once_with("Sales")
        mock_importer_inst.apply.assert_called_once_with(bundle)
        self.assertIn("Q3 Liveboard", result.imported_objects)

    @patch("ts_group_migrator.migrator.Importer")
    @patch("ts_group_migrator.migrator.Exporter")
    @patch("ts_group_migrator.migrator.ThoughtSpotClient")
    def test_bundle_saved_when_path_provided(self, MockClient, MockExporter, MockImporter):
        bundle = _make_bundle()
        mock_ctx = MagicMock()
        MockClient.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        mock_exporter_inst = MagicMock()
        mock_exporter_inst.export.return_value = bundle
        MockExporter.return_value = mock_exporter_inst

        from ts_group_migrator.importer import ImportResult
        MockImporter.return_value.apply.return_value = ImportResult()

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "bundle.json")
            migrator = GroupMigrator(
                source=_cfg(), destination=_cfg("https://dst.example.com"),
                bundle_cache_path=bundle_path,
            )
            migrator.migrate("Sales")
            self.assertTrue(os.path.exists(bundle_path))
            with open(bundle_path) as f:
                data = json.load(f)
            self.assertEqual(data["groups"][0]["name"], "Sales")
            self.assertEqual(data["users"][0]["name"], "alice")


class TestGroupMigratorBundleRoundTrip(unittest.TestCase):
    @patch("ts_group_migrator.migrator.Importer")
    @patch("ts_group_migrator.migrator.ThoughtSpotClient")
    def test_migrate_from_bundle_reloads_correctly(self, MockClient, MockImporter):
        bundle = _make_bundle()
        mock_ctx = MagicMock()
        MockClient.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        MockClient.return_value.__exit__ = MagicMock(return_value=False)

        from ts_group_migrator.importer import ImportResult
        mock_result = ImportResult()
        mock_result.imported_objects = ["Q3 Liveboard"]
        MockImporter.return_value.apply.return_value = mock_result

        with tempfile.TemporaryDirectory() as tmpdir:
            bundle_path = os.path.join(tmpdir, "bundle.json")
            GroupMigrator._save_bundle(bundle, bundle_path)

            migrator = GroupMigrator(source=_cfg(), destination=_cfg("https://dst.example.com"))
            result = migrator.migrate_from_bundle(bundle_path)

            # Verify the bundle was correctly reloaded and passed to importer
            applied_bundle = MockImporter.return_value.apply.call_args[0][0]
            self.assertEqual(applied_bundle.groups[0].name, "Sales")
            self.assertEqual(applied_bundle.users[0].name, "alice")
            self.assertEqual(applied_bundle.objects[0].type, MetadataType.LIVEBOARD)
            self.assertEqual(applied_bundle.permissions[0].permission, PermissionType.READ_ONLY)


class TestMigrationBundleSummary(unittest.TestCase):
    def test_summary_counts(self):
        bundle = _make_bundle()
        summary = bundle.summary()
        self.assertIn("Groups: 1", summary)
        self.assertIn("Users: 1", summary)
        self.assertIn("Objects: 1", summary)
        self.assertIn("Permission entries: 1", summary)


class TestImportResultSummary(unittest.TestCase):
    def test_summary_format(self):
        from ts_group_migrator.importer import ImportResult
        r = ImportResult()
        r.created_groups = ["Sales"]
        r.created_users = ["alice", "bob"]
        r.imported_objects = ["LB1", "LB2"]
        r.permissions_applied = 5
        r.ownership_transferred = 2
        summary = r.summary()
        self.assertIn("created=1", summary)
        self.assertIn("created=2", summary)
        self.assertIn("imported=2", summary)
        self.assertIn("Permissions=5", summary)
        self.assertIn("Ownership transfers=2", summary)


if __name__ == "__main__":
    unittest.main()
