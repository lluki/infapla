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
            alexa_sync_interval=1,
            alexa_sync_url="https://fake-lambda-url.amazonaws.com/sync",
            alexa_sync_secret="test-secret"
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
    def test_native_alexa_backend(self, mock_urlopen):
        backend = NativeAlexaBackend("fake-cookie", "fake-csrf", "amazon.de")

        # Mock fetch from /api/todos
        mock_resp_fetch = MagicMock()
        mock_resp_fetch.read.return_value = json.dumps({
            "values": [
                {"id": "nat-1", "text": "oat milk", "complete": False},
                {"id": "nat-2", "text": "apples", "complete": True}
            ]
        }).encode("utf-8")
        mock_resp_fetch.__enter__.return_value = mock_resp_fetch
        mock_urlopen.return_value = mock_resp_fetch

        items = backend.fetch_items()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], "oat milk")

        # Mock delete
        mock_resp_del = MagicMock()
        mock_resp_del.__enter__.return_value = mock_resp_del
        mock_urlopen.return_value = mock_resp_del

        cleared = backend.clear_items(["nat-1"])
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

    def test_server_api_alexa_status_and_sync(self):
        daemon = InFaPlaDaemon(self.config)
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

    def test_direct_alexa_skill_webhook(self):
        daemon = InFaPlaDaemon(self.config)
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


if __name__ == "__main__":
    unittest.main()
