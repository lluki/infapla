import re
import os
import json
import time
import shutil
import logging
import threading
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, Any, List

from .storage import Storage
from .sandbox import SandboxRunner

logger = logging.getLogger("infapla.telegram")

URL_REGEX = re.compile(r"https?://[^\s]+")

class TelegramBot:
    def __init__(self, token: str, storage: Storage, sandbox: SandboxRunner, allowed_users: Optional[List[str]] = None):
        self.token = token.strip()
        self.storage = storage
        self.sandbox = sandbox
        self.allowed_users = set(u.strip().lstrip("@").lower() for u in (allowed_users or []) if u.strip())
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.sessions: Dict[int, Dict[str, Any]] = {}

    def is_user_authorized(self, msg: Dict[str, Any]) -> bool:
        if not self.allowed_users:
            return True
        from_user = msg.get("from") or {}
        user_id = str(from_user.get("id") or "").strip()
        username = (from_user.get("username") or "").strip().lstrip("@").lower()
        chat_id = str(msg.get("chat", {}).get("id") or "").strip()

        return (
            (bool(user_id) and user_id in self.allowed_users)
            or (bool(username) and username in self.allowed_users)
            or (bool(chat_id) and chat_id in self.allowed_users)
        )

    def is_configured(self) -> bool:
        return bool(self.token)

    def start(self) -> None:
        if not self.is_configured():
            logger.info("Telegram bot token not configured. Telegram listener skipped.")
            return

        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self._poll_loop, daemon=True, name="infapla-telegram-bot")
        self.thread.start()
        logger.info("Telegram bot listener started.")

    def stop(self) -> None:
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

    def _api_call(self, method: str, data: Optional[Dict[str, Any]] = None, timeout: int = 40) -> Optional[Dict[str, Any]]:
        url = f"{self.base_url}/{method}"
        try:
            if data is not None:
                encoded_data = json.dumps(data).encode("utf-8")
                req = urllib.request.Request(
                    url,
                    data=encoded_data,
                    headers={"Content-Type": "application/json"}
                )
            else:
                req = urllib.request.Request(url)

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                if res_json.get("ok"):
                    return res_json.get("result")
                else:
                    logger.warning(f"Telegram API error {method}: {res_json.get('description')}")
                    return None
        except Exception as e:
            if self.running:
                logger.debug(f"Telegram request failed {method}: {e}")
            return None

    def send_message(self, chat_id: int, text: str, parse_mode: Optional[str] = "Markdown") -> None:
        data = {
            "chat_id": chat_id,
            "text": text
        }
        if parse_mode:
            data["parse_mode"] = parse_mode
        res = self._api_call("sendMessage", data, timeout=10)
        # If Markdown parsing fails due to unescaped characters, fallback to plain text
        if res is None and parse_mode:
            data.pop("parse_mode", None)
            self._api_call("sendMessage", data, timeout=10)

    def download_file(self, file_id: str, dest_path: Path) -> bool:
        file_info = self._api_call("getFile", {"file_id": file_id}, timeout=15)
        if not file_info or "file_path" not in file_info:
            return False

        file_url = f"https://api.telegram.org/file/bot{self.token}/{file_info['file_path']}"
        try:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(file_url, dest_path)
            return True
        except Exception as e:
            logger.error(f"Failed to download telegram file {file_id}: {e}")
            return False

    def _poll_loop(self) -> None:
        offset = 0
        while self.running:
            try:
                updates = self._api_call("getUpdates", {"offset": offset, "timeout": 20}, timeout=30)
                if updates:
                    for upd in updates:
                        upd_id = upd.get("update_id", 0)
                        if upd_id >= offset:
                            offset = upd_id + 1
                        self._handle_update(upd)
                else:
                    time.sleep(1)
            except Exception as e:
                logger.error(f"Error in telegram poll loop: {e}")
                time.sleep(3)

    def _handle_update(self, update: Dict[str, Any]) -> None:
        msg = update.get("message")
        if not msg:
            return

        chat_id = msg.get("chat", {}).get("id")
        if not chat_id:
            return

        if not self.is_user_authorized(msg):
            sender_id = msg.get("from", {}).get("username") or msg.get("from", {}).get("id") or "Unknown"
            logger.warning(f"Unauthorized message attempt from {sender_id} (chat_id: {chat_id})")
            self.send_message(
                chat_id,
                "⛔ *Access Denied:* You are not authorized to access this InFaPla instance.",
                parse_mode="Markdown"
            )
            return

        text = msg.get("text", "").strip()
        caption = msg.get("caption", "").strip()
        photos = msg.get("photo")
        voice = msg.get("voice") or msg.get("audio")

        # 1. Reset command
        if text.startswith("/reset"):
            self.sessions[chat_id] = {"started_at": time.time(), "history": []}
            self.send_message(
                chat_id,
                "🔄 *Session reset!*\nA fresh conversation session has begun. How can I help your family today?",
                parse_mode="Markdown"
            )
            return

        # 2. Help / Start commands
        if text.startswith("/start") or text.startswith("/help"):
            help_text = (
                "👋 *Welcome to InFaPla Bot!*\n\n"
                "I am your family planning companion. Here are some things you can do:\n\n"
                "🎙️ *Voice message*: Send a voice note (e.g. 'Add milk and eggs to shopping list') and I will process it!\n"
                "📸 *Invite screenshot*: Send a photo/screenshot of an invitation, and I will extract the event and add it to your calendar!\n"
                "🍲 *Recipe link*: Send a web link to a recipe, and I will format and save it under recipes.\n"
                "💬 *Ask questions*: Ask anything about your shopping list, meal plans, or todos.\n\n"
                "*Commands:*\n"
                "• `/shopping` - View pending shopping items\n"
                "• `/todo` - View family todos\n"
                "• `/calendar` - View upcoming events\n"
                "• `/reset` - Start a new session"
            )
            self.send_message(chat_id, help_text)
            return

        # 3. Quick view commands
        if text.startswith("/shopping"):
            shop_data = self.storage.get_shopping_data()
            active = [i for i in shop_data["items"] if not i["done"]]
            if not active:
                self.send_message(chat_id, "🛒 *Shopping List:* All items are checked off! Nothing to buy.")
            else:
                items_str = "\n".join(f"• {i['text']} ({i['category']})" for i in active[:20])
                self.send_message(chat_id, f"🛒 *Pending Shopping Items ({len(active)}):*\n\n{items_str}")
            return

        if text.startswith("/todo"):
            todo_data = self.storage.get_todos() if hasattr(self.storage, "get_todos") else self.storage.get_todo_data()
            active = [i for i in todo_data["items"] if not i["done"]]
            if not active:
                self.send_message(chat_id, "✅ *TODO List:* All tasks are done! Great job!")
            else:
                items_str = "\n".join(f"• {i['text']}" for i in active[:20])
                self.send_message(chat_id, f"📋 *TODO / Open Tasks ({len(active)}):*\n\n{items_str}")
            return

        if text.startswith("/calendar"):
            events = self.storage.get_calendar_events()
            if not events:
                self.send_message(chat_id, "📅 *Calendar:* No upcoming events recorded.")
            else:
                ev_str = "\n".join(
                    f"• *{e['summary']}*\n  🕒 {e.get('start_str', 'TBD')}" + (f" @ {e['location']}" if e.get('location') else "")
                    for e in events[:10]
                )
                self.send_message(chat_id, f"📅 *Calendar / Upcoming Events:*\n\n{ev_str}")
            return

        # 4. Handle voice / audio messages
        if voice:
            self.send_message(chat_id, "🎙️ Listening to your voice message...")
            file_id = voice["file_id"]
            ext = ".ogg"
            if msg.get("audio"):
                file_name = msg["audio"].get("file_name", "")
                if file_name and "." in file_name:
                    ext = Path(file_name).suffix
            audio_filename = f"voice_{chat_id}_{int(time.time())}{ext}"
            audio_path = self.storage.data_dir / audio_filename

            if self.download_file(file_id, audio_path):
                prompt = (
                    f"A family member sent a voice/audio message saved at '{audio_filename}'. "
                    f"{'User note: ' + caption if caption else ''}\n"
                    "Please listen to and transcribe this audio message using your file inspection tools. "
                    "Then, fulfill their request (such as updating the shopping list, updating or adding todos, "
                    "adding events to the calendar, saving a recipe, or answering their question). "
                    f"After processing, delete the temporary audio file '{audio_filename}'. "
                    "Respond with a clear, helpful confirmation of what you understood and did."
                )
                try:
                    result = self.sandbox.execute_prompt(prompt)
                    reply = result.get("response", "Voice message processed!")
                    self.send_message(chat_id, f"🎙️ {reply}")
                finally:
                    if audio_path.exists():
                        try:
                            audio_path.unlink()
                        except Exception:
                            pass
            else:
                self.send_message(chat_id, "❌ Sorry, I had trouble downloading the voice message.")
            return

        # 5. Handle photos (Screenshot of an invite -> calendar entry)
        if photos:
            self.send_message(chat_id, "🔍 Analyzing invite screenshot and creating calendar event...")
            # Pick highest resolution photo
            best_photo = photos[-1]
            file_id = best_photo["file_id"]
            img_filename = f"invite_{chat_id}_{int(time.time())}.jpg"
            img_path = self.storage.data_dir / "calendar" / img_filename

            if self.download_file(file_id, img_path):
                prompt = (
                    f"A family member sent an invitation image saved at 'calendar/{img_filename}'. "
                    f"{'User note: ' + caption if caption else ''}\n"
                    "Please inspect this image, extract the event details (Title/Summary, Date, Start Time, End Time, Location, Description), "
                    "and create a standard iCalendar (.ics) file in the 'calendar/' directory. "
                    f"After creating the .ics file, delete the temporary image 'calendar/{img_filename}'. "
                    "Respond with a clear, cheerful confirmation of the event that was scheduled."
                )
                try:
                    result = self.sandbox.execute_prompt(prompt)
                    reply = result.get("response", "Event created in calendar!")
                    self.send_message(chat_id, f"📅 {reply}")
                finally:
                    if img_path.exists():
                        try:
                            img_path.unlink()
                        except Exception:
                            pass
            else:
                self.send_message(chat_id, "❌ Sorry, I had trouble downloading the screenshot.")
            return

        # 6. Handle Recipe URLs
        urls = URL_REGEX.findall(text)
        if urls:
            url = urls[0]
            self.send_message(chat_id, f"🍳 Fetching recipe from {url} and adding to your recipes...")
            prompt = (
                f"The user sent a recipe link: {url}\n"
                "Please read/fetch the contents of this recipe and create a new recipe file in 'shopping/recipes/<dish-name>.md'. "
                "Format the recipe with: \n"
                "# Dish Title\n\n"
                "## Info\n- Servings: ...\n- Prep time: ...\n\n"
                "## Ingredients\n- list of ingredients...\n\n"
                "## Instructions\n1. step 1...\n\n"
                "Respond with a summary of the saved recipe and the list of key ingredients."
            )
            result = self.sandbox.execute_prompt(prompt)
            reply = result.get("response", "Recipe saved!")
            self.send_message(chat_id, f"🍲 {reply}")
            return

        # 7. Generic queries / questions
        if text:
            # Let user know processing has started
            prompt = f"Family member on Telegram asks:\n{text}"
            result = self.sandbox.execute_prompt(prompt)
            reply = result.get("response", "I could not generate a response.")
            self.send_message(chat_id, reply)
