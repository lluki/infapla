import unittest
import tempfile
import shutil
import json
from pathlib import Path

from infapla.config import Config
from infapla.daemon import InFaPlaDaemon
from infapla.server import create_app

class TestServerAPI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.config = Config(data_dir=self.temp_dir)
        self.daemon = InFaPlaDaemon(self.config)
        self.app = create_app(self.daemon)
        self.client = self.app.test_client()

    def tearDown(self):
        self.daemon.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_index_page(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"InFaPla", res.data)

    def test_list_files(self):
        res = self.client.get("/api/files")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("files", data)
        paths = [f["path"] for f in data["files"]]
        self.assertIn("shopping/list.md", paths)

    def test_file_get_and_post(self):
        # GET file
        res = self.client.get("/api/file?path=shopping/list.md")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["type"], "shopping")
        self.assertIn("content", data)

        # POST file
        new_content = "# Updated Shopping List\n- [ ] Milk\n"
        res2 = self.client.post("/api/file", json={"path": "shopping/list.md", "content": new_content})
        self.assertEqual(res2.status_code, 200)

        # Verify updated
        res3 = self.client.get("/api/file?path=shopping/list.md")
        self.assertIn("Updated Shopping List", res3.get_json()["content"])

    def test_file_delete(self):
        # Create a file to delete
        self.client.post("/api/file/create", json={"path": "notes/temp.md", "content": "# Temp"})
        res_get = self.client.get("/api/file?path=notes/temp.md")
        self.assertEqual(res_get.status_code, 200)

        # Delete it
        res_del = self.client.post("/api/file/delete", json={"path": "notes/temp.md"})
        self.assertEqual(res_del.status_code, 200)
        self.assertTrue(res_del.get_json()["success"])

        # Verify it's gone
        res_after = self.client.get("/api/file?path=notes/temp.md")
        self.assertEqual(res_after.status_code, 404)

    def test_shopping_api(self):
        # GET shopping
        res = self.client.get("/api/shopping")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("items", data)

        # ADD shopping
        res_add = self.client.post("/api/shopping/add", json={"text": "Organic Apples", "category": "Produce"})
        self.assertEqual(res_add.status_code, 200)
        data_add = res_add.get_json()
        self.assertTrue(any(i["text"] == "Organic Apples" for i in data_add["items"]))

        # TOGGLE shopping to done and verify category postfix remembered
        res_toggle = self.client.post("/api/shopping/toggle", json={"text": "Organic Apples"})
        self.assertEqual(res_toggle.status_code, 200)
        data_toggle = res_toggle.get_json()
        item = next(i for i in data_toggle["items"] if i["text"] == "Organic Apples")
        self.assertTrue(item["done"])

        # TOGGLE shopping back to active -> must remember Produce category
        res_toggle_back = self.client.post("/api/shopping/toggle", json={"text": "Organic Apples"})
        self.assertEqual(res_toggle_back.status_code, 200)
        data_toggle_back = res_toggle_back.get_json()
        item_back = next(i for i in data_toggle_back["items"] if i["text"] == "Organic Apples")
        self.assertFalse(item_back["done"])
        self.assertEqual(item_back["category"], "Produce")

        # REMOVE shopping
        res_del = self.client.post("/api/shopping/remove", json={"text": "Organic Apples"})
        self.assertEqual(res_del.status_code, 200)

        # CLEAR COMPLETED shopping
        self.client.post("/api/shopping/add", json={"text": "Bananas"})
        self.client.post("/api/shopping/toggle", json={"text": "Bananas"})
        res_clear = self.client.post("/api/shopping/clear-completed")
        self.assertEqual(res_clear.status_code, 200)
        done_items = [i for i in res_clear.get_json()["items"] if i["done"]]
        self.assertEqual(len(done_items), 0)

        # ARCHIVE shopping
        self.client.post("/api/shopping/add", json={"text": "Bread"})
        res_arch = self.client.post("/api/shopping/archive")
        self.assertEqual(res_arch.status_code, 200)
        arch_data = res_arch.get_json()
        self.assertIn("archived_to", arch_data)
        self.assertTrue(arch_data["archived_to"].startswith("shopping/list-archive/"))
        # Shopping list should now be reset and empty
        self.assertEqual(len(arch_data["shopping"]["items"]), 0)

    def test_todo_api(self):
        # ADD todo
        res_add = self.client.post("/api/todo/add", json={"text": "Mow the lawn"})
        self.assertEqual(res_add.status_code, 200)
        data = res_add.get_json()
        self.assertTrue(any(i["text"] == "Mow the lawn" for i in data["items"]))

        # TOGGLE todo
        res_toggle = self.client.post("/api/todo/toggle", json={"text": "Mow the lawn"})
        self.assertEqual(res_toggle.status_code, 200)
        data_toggle = res_toggle.get_json()
        item = next(i for i in data_toggle["items"] if i["text"] == "Mow the lawn")
        self.assertTrue(item["done"])

    def test_calendar_api(self):
        # GET calendar
        res = self.client.get("/api/calendar")
        self.assertEqual(res.status_code, 200)

        # ADD calendar
        res_add = self.client.post("/api/calendar/add", json={
            "summary": "Parent Teacher Conference",
            "start": "2026-10-20T16:00:00",
            "location": "Elementary School Room 104"
        })
        self.assertEqual(res_add.status_code, 200)
        self.assertTrue(res_add.get_json()["success"])

        # GET calendar again
        res2 = self.client.get("/api/calendar")
        events = res2.get_json()["events"]
        self.assertTrue(any("Parent Teacher Conference" in e["summary"] for e in events))

    def test_git_endpoints(self):
        res_status = self.client.get("/api/git/status")
        self.assertEqual(res_status.status_code, 200)

        res_history = self.client.get("/api/git/history")
        self.assertEqual(res_history.status_code, 200)

        res_commit = self.client.post("/api/git/commit", json={"message": "Test commit"})
        self.assertEqual(res_commit.status_code, 200)
        c_hash = res_commit.get_json()["commit"]

        res_diff = self.client.get(f"/api/git/diff?commit={c_hash}")
        self.assertEqual(res_diff.status_code, 200)
        self.assertIn("diff", res_diff.get_json())

        res_sync = self.client.post("/api/git/sync", json={"message": "Sync from API test"})
        self.assertEqual(res_sync.status_code, 200)
        self.assertTrue(res_sync.get_json()["success"])

if __name__ == "__main__":
    unittest.main()
