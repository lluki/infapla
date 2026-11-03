import io
import json
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

from infapla.config import Config
from infapla.storage import Storage
from infapla.sandbox import SandboxRunner
from infapla.alexa_sync import (
    ALEXA_PARSE_PROMPT,
    parse_model_items,
    HttpAlexaBackend,
    DynamoDBAlexaBackend,
    NativeAlexaBackend,
    AlexaSyncService
)
from infapla.server import create_app
from infapla.daemon import InFaPlaDaemon


class TestAlexaSync(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.storage = Storage(self.temp_dir)
        self.config = Config(
            data_dir=self.temp_dir,
            alexa_sync_interval=60,
            alexa_sync_url="https://fake-lambda-url.amazonaws.com/sync",
            alexa_sync_secret="test-secret",
            alexa_sync_enabled=True
        )
        self.mock_sandbox = MagicMock(spec=SandboxRunner)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parse_model_items(self):
        # Case 1: Standard markdown bullet points
        output1 = (
            "Here are the items for your shopping list:\n"
            "- Organic Whole Milk\n"
            "- 2 Bananas\n"
            "- Sourdough Bread\n"
        )
        items1 = parse_model_items(output1)
        self.assertEqual(items1, ["Organic Whole Milk", "2 Bananas", "Sourdough Bread"])

        # Case 2: Numbered lists and checkmarks
        output2 = (
            "1. Fresh Basil\n"
            "2. Garlic (1 bulb)\n"
            "3. [ ] Dish soap\n"
        )
        items2 = parse_model_items(output2)
        self.assertEqual(items2, ["Fresh Basil", "Garlic (1 bulb)", "Dish soap"])

        # Case 3: Comma separated fallback
        output3 = "apples, bananas, 2 cartons of orange juice"
        items3 = parse_model_items(output3)
        self.assertEqual(items3, ["apples", "bananas", "2 cartons of orange juice"])

        # Case 4: Empty string
        self.assertEqual(parse_model_items(""), [])
        self.assertEqual(parse_model_items("   \n  "), [])

    @patch("urllib.request.urlopen")
    def test_http_backend_fetch_and_clear(self, mock_urlopen):
        backend = HttpAlexaBackend("https://example.com/sync", "my-secret")

        # Test fetch
        mock_resp_fetch = MagicMock()
        mock_resp_fetch.read.return_value = json.dumps({
            "items": [
                {"id": "1", "text": "milk and honey"},
                {"id": "2", "text": "coffee beans"}
            ]
        }).encode("utf-8")
        mock_resp_fetch.__enter__.return_value = mock_resp_fetch
        mock_urlopen.return_value = mock_resp_fetch

        items = backend.fetch_items()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["text"], "milk and honey")

        # Test clear
        mock_resp_clear = MagicMock()
        mock_resp_clear.read.return_value = json.dumps({"success": True}).encode("utf-8")
        mock_resp_clear.__enter__.return_value = mock_resp_clear
        mock_urlopen.return_value = mock_resp_clear

        cleared = backend.clear_items(["1", "2"])
        self.assertTrue(cleared)

    def test_dynamodb_backend(self):
        backend = DynamoDBAlexaBackend("test-table", "us-east-1")
        mock_table = MagicMock()
        mock_table.scan.return_value = {
            "Items": [
                {"id": "d1", "text": "almond milk", "status": "pending"},
                {"id": "d2", "text": "apples", "status": "completed"}
            ]
        }
        backend._table = mock_table

        items = backend.fetch_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], "almond milk")

        cleared = backend.clear_items(["d1"])
        self.assertTrue(cleared)
        mock_table.delete_item.assert_called_once_with(Key={"id": "d1"})

    @patch("urllib.request.urlopen")
    def test_native_alexa_backend_legacy(self, mock_urlopen):
        backend = NativeAlexaBackend("fake-cookie", "fake-csrf", "amazon.de")

        # First calls fail with 404 (modern API unavailable)
        # Fallback call succeeds with /api/todos format
        def fake_urlopen(req, *args, **kwargs):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            mock_resp = MagicMock()
            if "/api/todos" in url and req.get_method() == "GET":
                mock_resp.read.return_value = json.dumps({
                    "values": [
                        {"id": "nat-1", "text": "oat milk", "complete": False},
                        {"id": "nat-2", "text": "apples", "complete": True}
                    ]
                }).encode("utf-8")
                mock_resp.__enter__.return_value = mock_resp
                return mock_resp
            elif req.get_method() == "DELETE":
                mock_resp.__enter__.return_value = mock_resp
                return mock_resp
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

        mock_urlopen.side_effect = fake_urlopen

        items = backend.fetch_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], "oat milk")

        cleared = backend.clear_items(["nat-1"])
        self.assertTrue(cleared)

    @patch("urllib.request.urlopen")
    def test_native_alexa_backend_modern(self, mock_urlopen):
        backend = NativeAlexaBackend("fake-cookie", "fake-csrf", "amazon.com")

        def fake_urlopen(req, *args, **kwargs):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            mock_resp = MagicMock()
            if "alexashoppinglists/api/v2/lists/fetch" in url:
                mock_resp.read.return_value = json.dumps({
                    "listInfoList": [
                        {"listId": "lid-123", "listType": "SHOP"}
                    ]
                }).encode("utf-8")
                mock_resp.__enter__.return_value = mock_resp
                return mock_resp
            elif "/items/fetch" in url:
                mock_resp.read.return_value = json.dumps({
                    "itemInfoList": [
                        {"itemId": "item-abc", "itemName": "Oat Milk", "itemStatus": "ACTIVE", "version": 2},
                        {"itemId": "item-def", "itemName": "Bread", "itemStatus": "COMPLETED", "version": 1}
                    ]
                }).encode("utf-8")
                mock_resp.__enter__.return_value = mock_resp
                return mock_resp
            elif req.get_method() == "DELETE":
                mock_resp.__enter__.return_value = mock_resp
                return mock_resp
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)

        mock_urlopen.side_effect = fake_urlopen

        items = backend.fetch_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], "Oat Milk")
        self.assertEqual(items[0]["id"], "item-abc")

        cleared = backend.clear_items(["item-abc"])
        self.assertTrue(cleared)

    def test_sync_once_success_flow(self):
        # Setup mock backend
        mock_backend = MagicMock()
        mock_backend.fetch_items.return_value = [
            {"id": "item-101", "text": "apples and bananas"},
            {"id": "item-102", "text": "dish soap"}
        ]
        mock_backend.clear_items.return_value = True

        # Model output when prompted
        self.mock_sandbox.execute_prompt.return_value = {
            "response": "- Apples\n- Bananas\n- Dish soap\n",
            "files_modified": []
        }

        service = AlexaSyncService(
            config=self.config,
            storage=self.storage,
            sandbox=self.mock_sandbox,
            backend=mock_backend
        )

        res = service.sync_once()

        self.assertTrue(res["success"])
        self.assertEqual(res["raw_count"], 2)
        self.assertEqual(res["items_added"], ["Apples", "Bananas", "Dish soap"])
        self.assertTrue(res["cleared"])

        # Verify prompt contained user's exact required prompt text
        self.mock_sandbox.execute_prompt.assert_called_once()
        sent_prompt = self.mock_sandbox.execute_prompt.call_args[0][0]
        self.assertIn("Add only items to shopping list", sent_prompt)
        self.assertIn("Each item of input shopping list may contain items that are in fact multiple items", sent_prompt)
        self.assertIn("parse them and add them as separat items", sent_prompt)
        self.assertIn("apples and bananas", sent_prompt)
        self.assertIn("dish soap", sent_prompt)

        # Verify items were added to InFaPla shopping list
        shopping_data = self.storage.get_shopping_data()
        item_texts = [i["text"] for i in shopping_data["items"]]
        self.assertIn("Apples", item_texts)
        self.assertIn("Bananas", item_texts)
        self.assertIn("Dish soap", item_texts)

        # Verify backend cleared with proper IDs
        mock_backend.clear_items.assert_called_once_with(["item-101", "item-102"])

    def test_sync_once_does_not_clear_on_model_error(self):
        mock_backend = MagicMock()
        mock_backend.fetch_items.return_value = [
            {"id": "item-201", "text": "milk and bread"}
        ]
        mock_backend.clear_items.return_value = True

        # Model returns error
        self.mock_sandbox.execute_prompt.return_value = {
            "response": "",
            "error": "Agent process timeout"
        }

        service = AlexaSyncService(
            config=self.config,
            storage=self.storage,
            sandbox=self.mock_sandbox,
            backend=mock_backend
        )

        res = service.sync_once()

        self.assertFalse(res["success"])
        self.assertIn("Model failed", res["error"])
        # Crucial requirement: DO NOT clear Alexa list on failure!
        mock_backend.clear_items.assert_not_called()

    def test_sync_once_idle_when_no_items(self):
        mock_backend = MagicMock()
        mock_backend.fetch_items.return_value = []

        service = AlexaSyncService(
            config=self.config,
            storage=self.storage,
            sandbox=self.mock_sandbox,
            backend=mock_backend
        )

        res = service.sync_once()

        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 0)
        self.mock_sandbox.execute_prompt.assert_not_called()
        mock_backend.clear_items.assert_not_called()

    def test_service_start_and_stop(self):
        mock_backend = MagicMock()
        mock_backend.fetch_items.return_value = []

        service = AlexaSyncService(
            config=self.config,
            storage=self.storage,
            sandbox=self.mock_sandbox,
            backend=mock_backend
        )

        service.start()
        self.assertTrue(service.running)
        service.stop()
        self.assertFalse(service.running)

    def test_service_disabled_by_default(self):
        default_cfg = Config(data_dir=self.temp_dir)
        self.assertFalse(default_cfg.alexa_sync_enabled)
        mock_backend = MagicMock()
        mock_backend.fetch_items.return_value = []
        service = AlexaSyncService(
            config=default_cfg,
            storage=self.storage,
            sandbox=self.mock_sandbox,
            backend=mock_backend
        )
        service.start()
        self.assertFalse(service.running)

    def test_server_api_alexa_status_and_sync(self):
        daemon = InFaPlaDaemon(self.config)
        try:
            # Mock backend
            mock_backend = MagicMock()
            mock_backend.fetch_items.return_value = [
                {"id": "test-1", "text": "fresh eggs"}
            ]
            mock_backend.clear_items.return_value = True
            daemon.alexa_sync.backend = mock_backend
            daemon.sandbox.execute_prompt = MagicMock(return_value={
                "response": "- Fresh eggs\n"
            })

            app = create_app(daemon)
            client = app.test_client()

            # Test status endpoint
            resp_status = client.get("/api/alexa/status")
            self.assertEqual(resp_status.status_code, 200)
            status_json = resp_status.get_json()
            self.assertTrue(status_json["configured"])

            # Test manual sync trigger endpoint
            resp_sync = client.post("/api/alexa/sync")
            self.assertEqual(resp_sync.status_code, 200)
            sync_json = resp_sync.get_json()
            self.assertTrue(sync_json["sync_result"]["success"])
            self.assertIn("Fresh eggs", sync_json["sync_result"]["items_added"])
        finally:
            daemon.stop()

    def test_direct_alexa_skill_webhook(self):
        daemon = InFaPlaDaemon(self.config)
        try:
            daemon.sandbox.execute_prompt = MagicMock(return_value={
                "response": "- Bananas\n- Sourdough bread\n"
            })
            app = create_app(daemon)
            client = app.test_client()

            # 1. Test LaunchRequest
            launch_payload = {
                "version": "1.0",
                "request": {"type": "LaunchRequest"}
            }
            res_launch = client.post("/api/alexa/skill", json=launch_payload)
            self.assertEqual(res_launch.status_code, 200)
            data = res_launch.get_json()
            self.assertRegex(data["response"]["outputSpeech"]["text"], r"Hello Maya, you should snip \d+ times")
            self.assertTrue(data["response"]["shouldEndSession"])

            # 2. Test AddShoppingItemIntent
            add_payload = {
                "version": "1.0",
                "request": {
                    "type": "IntentRequest",
                    "intent": {
                        "name": "AddShoppingItemIntent",
                        "slots": {
                            "items": {"value": "bananas and sourdough bread"}
                        }
                    }
                }
            }
            res_add = client.post("/api/alexa/skill", json=add_payload)
            self.assertEqual(res_add.status_code, 200)
            add_json = res_add.get_json()
            self.assertIn("Added Bananas, Sourdough bread", add_json["response"]["outputSpeech"]["text"])
            self.assertTrue(add_json["response"]["shouldEndSession"])

            # Verify items were saved into InFaPla shopping list
            shopping_data = daemon.storage.get_shopping_data()
            item_texts = [i["text"] for i in shopping_data["items"]]
            self.assertIn("Bananas", item_texts)
            self.assertIn("Sourdough bread", item_texts)
        finally:
            daemon.stop()

    def test_session_persistence_and_reload(self):
        from infapla.alexa_sync import (
            save_session_data,
            load_saved_session,
            delete_saved_session,
            get_session_file_path
        )

        # 1. Initially no session
        self.assertIsNone(load_saved_session(self.temp_dir))

        # 2. Save session
        saved = save_session_data(self.temp_dir, cookie="my-cookie=abc", csrf="csrf-123", domain="amazon.de")
        self.assertEqual(saved["cookie"], "my-cookie=abc")
        self.assertEqual(saved["csrf"], "csrf-123")
        self.assertEqual(saved["domain"], "amazon.de")

        # 3. Load session
        loaded = load_saved_session(self.temp_dir)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["cookie"], "my-cookie=abc")

        # 4. Service reload
        service = AlexaSyncService(config=Config(data_dir=self.temp_dir), storage=self.storage, sandbox=self.mock_sandbox)
        self.assertTrue(service.is_configured())
        self.assertIsInstance(service.backend, NativeAlexaBackend)
        self.assertEqual(service.backend.cookie, "my-cookie=abc")

        # 5. Test connection
        with patch.object(service.backend, "fetch_items", return_value=[{"id": "1", "text": "onions"}]):
            res = service.test_connection()
            self.assertTrue(res["success"])
            self.assertEqual(res["count"], 1)
            self.assertEqual(res["samples"], ["onions"])

        # 6. Delete session
        deleted = delete_saved_session(self.temp_dir)
        self.assertTrue(deleted)
        self.assertIsNone(load_saved_session(self.temp_dir))
        service.reload_backend()
        self.assertFalse(service.is_configured())

    def test_alexa_login_proxy_and_server_endpoints(self):
        daemon = InFaPlaDaemon(self.config)
        try:
            app = create_app(daemon)
            client = app.test_client()

            # 1. Test POST /api/alexa/session
            res_save = client.post("/api/alexa/session", json={
                "cookie": "test-cookie=123",
                "csrf": "test-csrf",
                "domain": "amazon.de"
            })
            self.assertEqual(res_save.status_code, 200)
            self.assertTrue(res_save.get_json()["success"])

            # Status check
            res_status = client.get("/api/alexa/status")
            status_json = res_status.get_json()
            self.assertTrue(status_json["configured"])
            self.assertEqual(status_json["domain"], "amazon.de")

            # 2. Test POST /api/alexa/test
            with patch.object(daemon.alexa_sync.backend, "fetch_items", return_value=[{"id": "a", "text": "tomatoes"}]):
                res_test = client.post("/api/alexa/test")
                self.assertEqual(res_test.status_code, 200)
                self.assertTrue(res_test.get_json()["success"])
                self.assertEqual(res_test.get_json()["count"], 1)

            # 3. Test DELETE /api/alexa/session
            res_del = client.delete("/api/alexa/session")
            self.assertEqual(res_del.status_code, 200)
            self.assertTrue(res_del.get_json()["success"])

            # 4. Test GET /api/alexa/login/start (redirects to proxy)
            res_start = client.get("/api/alexa/login/start?domain=amazon.de")
            self.assertEqual(res_start.status_code, 302)
            self.assertIn("proxy?sid=", res_start.headers["Location"])

            # 4b. Test GET /api/alexa/login/start with dynamic reverse-proxy prefix
            res_start_pre = client.get("/api/alexa/login/start?domain=amazon.com&prefix=/infapla")
            self.assertEqual(res_start_pre.status_code, 302)
            self.assertIn("/infapla/api/alexa/login/proxy?sid=", res_start_pre.headers["Location"])

            # 5. Test GET /api/alexa/login/success
            res_success = client.get("/api/alexa/login/success")
            self.assertEqual(res_success.status_code, 200)
            self.assertIn(b"Alexa Connected!", res_success.data)
            self.assertIn(b"alexa_login_success", res_success.data)
        finally:
            daemon.stop()


if __name__ == "__main__":
    unittest.main()
