"""Tests for ThoughtSpotClient — all HTTP calls are mocked."""

import unittest
from unittest.mock import MagicMock, patch, call
import requests

from ts_group_migrator.client import ThoughtSpotClient, TSConfig


def _make_client():
    return ThoughtSpotClient(TSConfig(url="https://ts.example.com", username="admin", password="secret"))


def _mock_response(json_data=None, status_code=200):
    r = MagicMock(spec=requests.Response)
    r.status_code = status_code
    r.content = b"ok"
    r.json.return_value = json_data or {}
    r.raise_for_status = MagicMock()
    return r


class TestLogin(unittest.TestCase):
    def test_login_posts_credentials(self):
        client = _make_client()
        with patch.object(client._s, "post", return_value=_mock_response()) as mock_post:
            client.login()
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["username"], "admin")
        self.assertEqual(kwargs["json"]["password"], "secret")
        self.assertTrue(client._authenticated)

    def test_login_raises_on_http_error(self):
        client = _make_client()
        resp = _mock_response(status_code=401)
        resp.raise_for_status.side_effect = requests.HTTPError("401")
        with patch.object(client._s, "post", return_value=resp):
            with self.assertRaises(requests.HTTPError):
                client.login()
        self.assertFalse(client._authenticated)

    def test_context_manager_logs_in_and_out(self):
        client = _make_client()
        with patch.object(client._s, "post", return_value=_mock_response()):
            with client:
                self.assertTrue(client._authenticated)
            self.assertFalse(client._authenticated)


class TestSearchGroups(unittest.TestCase):
    def test_returns_parsed_list(self):
        client = _make_client()
        payload = [{"id": "g1", "name": "Sales"}]
        with patch.object(client._s, "post", return_value=_mock_response(payload)) as mock_post:
            client._authenticated = True
            result = client.search_groups("Sales")
        self.assertEqual(result, payload)

    def test_paginates_until_short_page(self):
        client = _make_client()
        client._authenticated = True
        full_page = [{"id": f"g{i}", "name": f"g{i}"} for i in range(200)]
        short_page = [{"id": "last", "name": "last"}]
        with patch.object(client._s, "post", side_effect=[
            _mock_response(full_page),
            _mock_response(short_page),
        ]):
            result = client.search_groups()
        self.assertEqual(len(result), 201)


class TestSearchUsers(unittest.TestCase):
    def test_returns_users_for_groups(self):
        client = _make_client()
        client._authenticated = True
        payload = [{"id": "u1", "name": "alice"}]
        with patch.object(client._s, "post", return_value=_mock_response(payload)):
            result = client.search_users(group_identifiers=["g1"])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "alice")


class TestExportTml(unittest.TestCase):
    def test_sends_correct_payload(self):
        client = _make_client()
        client._authenticated = True
        expected = [{"edoc": "liveboard:\n  name: LB1", "status": {"status_code": "OK"}}]
        with patch.object(client._s, "post", return_value=_mock_response(expected)) as mock_post:
            result = client.export_tml([{"identifier": "lb1", "type": "LIVEBOARD"}], export_associated=True)
        _, kwargs = mock_post.call_args
        self.assertTrue(kwargs["json"]["export_associated"])
        self.assertEqual(result, expected)


class TestImportTml(unittest.TestCase):
    def test_sends_tml_strings(self):
        client = _make_client()
        client._authenticated = True
        resp = [{"response": {"status": {"status_code": "OK"}, "header": {"id_guid": "new-id"}}}]
        with patch.object(client._s, "post", return_value=_mock_response(resp)) as mock_post:
            result = client.import_tml(["liveboard:\n  name: LB1"])
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["metadata_tmls"], ["liveboard:\n  name: LB1"])
        self.assertTrue(kwargs["json"]["force_create"])


class TestTransferOwnership(unittest.TestCase):
    def test_calls_v1_endpoint(self):
        client = _make_client()
        client._authenticated = True
        with patch.object(client._s, "post", return_value=_mock_response({})) as mock_post:
            client.transfer_ownership("admin", "alice", ["obj1", "obj2"])
        url_called = mock_post.call_args[0][0]
        self.assertIn("/tspublic/v1/user/transfer/ownership", url_called)


if __name__ == "__main__":
    unittest.main()
