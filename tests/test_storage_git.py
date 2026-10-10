import unittest
import tempfile
import shutil
from pathlib import Path
from infapla.storage import Storage
from infapla.git_manager import GitManager

class TestStorageAndGit(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.storage = Storage(self.temp_dir)
        self.git_mgr = GitManager(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization(self):
        # Files should be created
        files = self.storage.list_files()
        paths = [f["path"] for f in files]
        self.assertIn("shopping/list.md", paths)
        self.assertIn("todo/list.md", paths)
        self.assertIn("calendar/family.ics", paths)

    def test_path_traversal_protection(self):
        with self.assertRaises(PermissionError):
            self.storage.resolve_path("../../etc/passwd")

    def test_file_classification(self):
        self.assertEqual(self.storage.classify_file("shopping/list.md"), "shopping")
        self.assertEqual(self.storage.classify_file("shopping/recipes/pasta.md"), "recipe")
        self.assertEqual(self.storage.classify_file("shopping/mealplan/2026-10-12.md"), "mealplan")
        self.assertEqual(self.storage.classify_file("todo/list.md"), "todo")
        self.assertEqual(self.storage.classify_file("calendar/events.ics"), "calendar")
        self.assertEqual(self.storage.classify_file("notes/family.md"), "markdown")
        self.assertEqual(self.storage.classify_file("archive/data.bin"), "generic")

    def test_shopping_operations(self):
        initial = self.storage.get_shopping_data()
        self.assertGreater(initial["active_count"], 0)

        # Add item
        updated = self.storage.add_shopping("Fresh Strawberries", "Produce")
        texts = [i["text"] for i in updated["items"]]
        self.assertIn("Fresh Strawberries", texts)

        # Toggle item
        toggled = self.storage.toggle_shopping("Fresh Strawberries")
        strawberries = next(i for i in toggled["items"] if i["text"] == "Fresh Strawberries")
        self.assertTrue(strawberries["done"])

        # Remove item
        removed = self.storage.remove_shopping("Fresh Strawberries")
        texts_after = [i["text"] for i in removed["items"]]
        self.assertNotIn("Fresh Strawberries", texts_after)

    def test_todo_operations(self):
        self.storage.add_todo("Test family task")
        data = self.storage.get_todo_data()
        texts = [i["text"] for i in data["items"]]
        self.assertIn("Test family task", texts)

        self.storage.toggle_todo("Test family task")
        data2 = self.storage.get_todo_data()
        item = next(i for i in data2["items"] if i["text"] == "Test family task")
        self.assertTrue(item["done"])

    def test_git_commit_and_history(self):
        # Create a new file
        self.storage.write_file("notes/test.md", "# Test Note\n")
        self.assertTrue(self.git_mgr.is_dirty())

        commit_hash = self.git_mgr.commit("Added test note")
        self.assertIsNotNone(commit_hash)
        self.assertFalse(self.git_mgr.is_dirty())

        history = self.git_mgr.get_history(limit=5)
        self.assertGreater(len(history), 0)
        self.assertEqual(history[0]["message"], "Added test note")

        last_edited = self.git_mgr.get_last_edited_files()
        paths = [f["path"] for f in last_edited]
        self.assertIn("notes/test.md", paths)

        diff = self.git_mgr.get_commit_diff(commit_hash)
        self.assertIn("+", diff)
        self.assertIn("# Test Note", diff)

    def test_git_sync(self):
        self.storage.write_file("notes/sync_test.md", "# Sync Note\n")
        res = self.git_mgr.sync("Test sync commit")
        self.assertTrue(res["success"])
        self.assertTrue(res["committed"])
        self.assertFalse(self.git_mgr.is_dirty())

if __name__ == "__main__":
    unittest.main()
