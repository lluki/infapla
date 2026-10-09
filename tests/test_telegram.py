import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import MagicMock

from infapla.storage import Storage
from infapla.sandbox import SandboxRunner
from infapla.telegram_bot import TelegramBot

class TestTelegramBot(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.storage = Storage(self.temp_dir)
        self.mock_sandbox = MagicMock(spec=SandboxRunner)
        self.bot = TelegramBot("dummy_token", self.storage, self.mock_sandbox)
        # Mock api call & send message
        self.bot.send_message = MagicMock()
        self.bot.download_file = MagicMock(return_value=True)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_reset_command(self):
        update = {
            "update_id": 1,
            "message": {
                "chat": {"id": 12345},
                "text": "/reset"
            }
        }
        self.bot._handle_update(update)
        self.assertIn(12345, self.bot.sessions)
        self.bot.send_message.assert_called()
        call_text = self.bot.send_message.call_args[0][1]
        self.assertIn("Session reset", call_text)

    def test_help_and_start(self):
        update = {
            "update_id": 2,
            "message": {
                "chat": {"id": 12345},
                "text": "/help"
            }
        }
        self.bot._handle_update(update)
        call_text = self.bot.send_message.call_args[0][1]
        self.assertIn("InFaPla Bot", call_text)

    def test_shopping_command(self):
        update = {
            "update_id": 3,
            "message": {
                "chat": {"id": 12345},
                "text": "/shopping"
            }
        }
        self.bot._handle_update(update)
        call_text = self.bot.send_message.call_args[0][1]
        self.assertIn("Shopping", call_text)

    def test_todo_command(self):
        update = {
            "update_id": 4,
            "message": {
                "chat": {"id": 12345},
                "text": "/todo"
            }
        }
        self.bot._handle_update(update)
        call_text = self.bot.send_message.call_args[0][1]
        self.assertIn("TODO", call_text)

    def test_calendar_command(self):
        update = {
            "update_id": 5,
            "message": {
                "chat": {"id": 12345},
                "text": "/calendar"
            }
        }
        self.bot._handle_update(update)
        call_text = self.bot.send_message.call_args[0][1]
        self.assertIn("Calendar", call_text)

    def test_recipe_url_handling(self):
        update = {
            "update_id": 6,
            "message": {
                "chat": {"id": 12345},
                "text": "Check out this recipe https://example.com/best-lasagna"
            }
        }
        self.mock_sandbox.execute_prompt.return_value = {
            "response": "Created recipe Lasagna in shopping/recipes/lasagna.md",
            "files_modified": ["shopping/recipes/lasagna.md"]
        }
        self.bot._handle_update(update)
        self.mock_sandbox.execute_prompt.assert_called()
        prompt_arg = self.mock_sandbox.execute_prompt.call_args[0][0]
        self.assertIn("https://example.com/best-lasagna", prompt_arg)
        self.assertIn("shopping/recipes", prompt_arg)

    def test_photo_invite_handling(self):
        update = {
            "update_id": 7,
            "message": {
                "chat": {"id": 12345},
                "caption": "Birthday party invitation",
                "photo": [
                    {"file_id": "small_id", "file_size": 100},
                    {"file_id": "large_id", "file_size": 5000}
                ]
            }
        }
        self.mock_sandbox.execute_prompt.return_value = {
            "response": "Extracted Birthday Party on Oct 25 and saved to calendar/20261025-birthday.ics",
            "files_modified": ["calendar/20261025-birthday.ics"]
        }
        self.bot._handle_update(update)
        self.bot.download_file.assert_called_with("large_id", unittest.mock.ANY)
        self.mock_sandbox.execute_prompt.assert_called()
        prompt_arg = self.mock_sandbox.execute_prompt.call_args[0][0]
        self.assertIn("calendar/", prompt_arg)
        self.assertIn("invitation", prompt_arg.lower())

if __name__ == "__main__":
    unittest.main()
