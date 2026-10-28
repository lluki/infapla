import re
import json
import time
import random
import logging
import threading
import urllib.request
import urllib.parse
from typing import List, Dict, Any, Optional, Tuple

from .config import Config
from .storage import Storage
from .sandbox import SandboxRunner

logger = logging.getLogger("infapla.alexa")

ALEXA_PARSE_PROMPT = (
    "Add only items to shopping list. Each item of input shopping list may contain items "
    "that are in fact multiple items. parse them and add them as separat items."
)


def parse_model_items(model_output: str) -> List[str]:
    """
    Parses the output of the model into individual clean shopping list items.
    Handles markdown bullets, numbered lists, and conversational responses.
    """
    if not model_output or not model_output.strip():
        return []

    items = []
    lines = model_output.strip().splitlines()

    skip_prefixes = (
        "here are",
        "here is",
        "i have",
        "sure",
        "output:",
        "shopping list:",
        "items to add:",
        "add only",
        "note:",
    )

    has_bullets = any(
        re.match(r"^(?:[-*+]|\d+[\.\)])\s+", l.strip())
        for l in lines
    )

    for line in lines:
        line = line.strip()
        if not line:
            continue

        lower_line = line.lower()
        if any(lower_line.startswith(prefix) for prefix in skip_prefixes):
            continue

        # Strip markdown bullets: -, *, +, or numbers like 1., 1)
        cleaned = re.sub(r"^(?:[-*+]|\d+[\.\)])\s*(?:\[[ xX]\]\s*)?", "", line).strip()
        # Remove surrounding markdown bold/italics or backticks
        cleaned = re.sub(r"^[`*_]+|[`*_]+$", "", cleaned).strip()
        # Remove trailing periods if plain item
        if cleaned.endswith(".") and not cleaned.endswith("etc."):
            cleaned = cleaned[:-1].strip()

        if cleaned and not any(cleaned.lower().startswith(p) for p in skip_prefixes):
            items.append(cleaned)

    # Fallback: If no bullet points were used and items contain commas or 'and', split them
    if not has_bullets and items:
        split_items = []
        for it in items:
            parts = re.split(r"[,;]+|\s+(?:and|und)\s+", it)
            for part in parts:
                p = part.strip()
                p = re.sub(r"^(?:and|und)\s+", "", p, flags=re.IGNORECASE).strip()
                if p:
                    split_items.append(p)
        if split_items:
            items = split_items

    # Fallback if model returned empty items list
    if not items and model_output.strip():
        raw = model_output.strip()
        parts = re.split(r"[,;\n]+", raw)
        for part in parts:
            p = part.strip()
            p = re.sub(r"^(?:and|und)\s+", "", p, flags=re.IGNORECASE).strip()
            if p:
                items.append(p)

    return items


class BaseAlexaBackend:
    """Interface for retrieving and clearing Alexa shopping list items."""

    def fetch_items(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def clear_items(self, item_ids: List[str]) -> bool:
        raise NotImplementedError


class HttpAlexaBackend(BaseAlexaBackend):
    """
    Connects to an AWS Lambda Function URL or AWS API Gateway endpoint over HTTPS.
    Requires no external dependencies (uses standard library urllib).
    """

    def __init__(self, endpoint_url: str, secret_token: Optional[str] = None):
        self.endpoint_url = endpoint_url.strip()
        self.secret_token = (secret_token or "").strip()

    def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "InFaPla-AlexaSync/1.0"
        }
        if self.secret_token:
            headers["x-api-key"] = self.secret_token
            headers["Authorization"] = f"Bearer {self.secret_token}"
        return headers

    def fetch_items(self) -> List[Dict[str, Any]]:
        req = urllib.request.Request(self.endpoint_url, headers=self._get_headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return data.get("items", [])
                return []
        except Exception as e:
            logger.error(f"Failed to fetch Alexa items from HTTP endpoint: {e}")
            raise

    def clear_items(self, item_ids: List[str]) -> bool:
        if not item_ids:
            return True
        payload = json.dumps({"action": "clear", "ids": item_ids}).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint_url,
            data=payload,
            headers=self._get_headers(),
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return bool(res.get("success", True))
        except Exception as e:
            logger.error(f"Failed to clear Alexa items via HTTP endpoint: {e}")
            return False


class DynamoDBAlexaBackend(BaseAlexaBackend):
    """
    Connects directly to an AWS DynamoDB table using boto3.
    """

    def __init__(
        self,
        table_name: str,
        region_name: str = "us-east-1",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None
    ):
        self.table_name = table_name.strip()
        self.region_name = region_name.strip()
        self.aws_access_key_id = aws_access_key_id.strip() if aws_access_key_id else None
        self.aws_secret_access_key = aws_secret_access_key.strip() if aws_secret_access_key else None
        self._table = None

    def _get_table(self):
        if self._table is None:
            try:
                import boto3
            except ImportError:
                raise ImportError(
                    "boto3 package is required for direct DynamoDB sync. "
                    "Install boto3 or use HTTP sync via ALEXA_SYNC_URL."
                )

            session_kwargs = {"region_name": self.region_name}
            if self.aws_access_key_id and self.aws_secret_access_key:
                session_kwargs["aws_access_key_id"] = self.aws_access_key_id
                session_kwargs["aws_secret_access_key"] = self.aws_secret_access_key

            session = boto3.Session(**session_kwargs)
            dynamodb = session.resource("dynamodb")
            self._table = dynamodb.Table(self.table_name)
        return self._table

    def fetch_items(self) -> List[Dict[str, Any]]:
        table = self._get_table()
        try:
            response = table.scan()
            items = response.get("Items", [])
            # Only return items where status is pending or not marked completed
            pending = [
                i for i in items
                if i.get("status") in (None, "", "pending")
            ]
            return pending
        except Exception as e:
            logger.error(f"Failed to scan DynamoDB table {self.table_name}: {e}")
            raise

    def clear_items(self, item_ids: List[str]) -> bool:
        if not item_ids:
            return True
        table = self._get_table()
        success = True
        for i_id in item_ids:
            try:
                table.delete_item(Key={"id": i_id})
            except Exception as e:
                logger.error(f"Failed to delete item {i_id} from DynamoDB: {e}")
                success = False
        return success


class NativeAlexaBackend(BaseAlexaBackend):
    """
    Connects to Amazon's internal web API to read and clear the standard native Alexa shopping list.
    Endpoint: https://alexa.{domain}/api/todos?type=SHOPPING_ITEM&size=100&completed=false
    Works with standard "Alexa, add [item] to my shopping list" without needing custom skills.
    Requires an authenticated Amazon web session cookie bundle and csrf token.
    """

    def __init__(self, cookie: str, csrf: str, domain: str = "amazon.de"):
        self.cookie = cookie.strip()
        self.csrf = csrf.strip()
        clean_domain = domain.strip().lower()
        if clean_domain.startswith("alexa."):
            clean_domain = clean_domain[6:]
        self.domain = clean_domain
        self.base_url = f"https://alexa.{self.domain}"

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Cookie": self.cookie,
            "csrf": self.csrf,
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": f"{self.base_url}/spa/index.html",
            "Accept": "application/json, text/javascript, */*; q=0.01"
        }

    def fetch_items(self) -> List[Dict[str, Any]]:
        url = f"{self.base_url}/api/todos?type=SHOPPING_ITEM&size=100&completed=false"
        req = urllib.request.Request(url, headers=self._get_headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                values = data.get("values", [])
                return [
                    {"id": v["id"], "text": v.get("text", "")}
                    for v in values
                    if not v.get("complete", False) and v.get("text")
                ]
        except Exception as e:
            logger.error(f"Failed to fetch native Alexa shopping list from {url}: {e}")
            raise

    def clear_items(self, item_ids: List[str]) -> bool:
        if not item_ids:
            return True
        success = True
        for item_id in item_ids:
            url = f"{self.base_url}/api/todos/{urllib.parse.quote(str(item_id))}"
            req = urllib.request.Request(url, headers=self._get_headers(), method="DELETE")
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    pass
            except Exception as e:
                logger.error(f"Failed to delete native Alexa item {item_id}: {e}")
                success = False
        return success


class AlexaSyncService:
    """
    Background periodic service that syncs the Alexa shopping list with InFaPla.
    """

    def __init__(
        self,
        config: Config,
        storage: Storage,
        sandbox: SandboxRunner,
        backend: Optional[BaseAlexaBackend] = None
    ):
        self.config = config
        self.storage = storage
        self.sandbox = sandbox
        self.interval = config.alexa_sync_interval
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()

        # Status tracking
        self.last_sync_time: Optional[float] = None
        self.last_sync_status: str = "never_run"
        self.last_error: Optional[str] = None
        self.total_synced_items: int = 0

        # Resolve backend
        if backend is not None:
            self.backend = backend
        elif self.config.alexa_cookie and self.config.alexa_csrf:
            self.backend = NativeAlexaBackend(
                cookie=self.config.alexa_cookie,
                csrf=self.config.alexa_csrf,
                domain=self.config.alexa_amazon_domain
            )
        elif self.config.alexa_sync_url:
            self.backend = HttpAlexaBackend(
                endpoint_url=self.config.alexa_sync_url,
                secret_token=self.config.alexa_sync_secret
            )
        elif self.config.alexa_dynamodb_table:
            self.backend = DynamoDBAlexaBackend(
                table_name=self.config.alexa_dynamodb_table,
                region_name=self.config.aws_region,
                aws_access_key_id=self.config.aws_access_key_id,
                aws_secret_access_key=self.config.aws_secret_access_key
            )
        else:
            self.backend = None

    def is_configured(self) -> bool:
        return self.backend is not None or bool(
            (self.config.alexa_cookie and self.config.alexa_csrf)
            or self.config.alexa_sync_url
            or self.config.alexa_dynamodb_table
        )

    def start(self) -> None:
        if not self.is_configured():
            logger.info("Alexa shopping sync not configured. Skipping background worker.")
            return

        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name="infapla-alexa-sync"
        )
        self.thread.start()
        logger.info(f"Alexa shopping sync service started (interval={self.interval}s)")

    def stop(self) -> None:
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)
        logger.info("Alexa shopping sync service stopped.")

    def _run_loop(self) -> None:
        while self.running:
            try:
                self.sync_once()
            except Exception as e:
                logger.error(f"Unexpected error in Alexa sync loop: {e}", exc_info=True)
            # Sleep in small slices for quick shutdown responsiveness
            for _ in range(max(1, self.interval)):
                if not self.running:
                    break
                time.sleep(1)

    def sync_once(self) -> Dict[str, Any]:
        """
        Executes a single synchronization cycle:
        1. Fetches pending raw items from Alexa/AWS backend.
        2. Filters/splits items through the model prompt.
        3. Inserts parsed items into InFaPla shopping list.
        4. If successful, clears items from Alexa.
        """
        with self.lock:
            if not self.backend:
                return {"success": False, "error": "Alexa backend not configured"}

            logger.info("Checking Alexa shopping list for new items...")
            try:
                raw_items = self.backend.fetch_items()
            except Exception as e:
                self.last_sync_time = time.time()
                self.last_sync_status = "fetch_failed"
                self.last_error = str(e)
                logger.error(f"Error fetching Alexa shopping list: {e}")
                return {"success": False, "error": f"Fetch failed: {e}"}

            if not raw_items:
                self.last_sync_time = time.time()
                self.last_sync_status = "idle_no_items"
                self.last_error = None
                return {"success": True, "count": 0, "message": "No new items on Alexa"}

            logger.info(f"Retrieved {len(raw_items)} items from Alexa. Passing through AI model...")

            # Extract item text and IDs
            item_texts = []
            item_ids = []
            for item in raw_items:
                text = item.get("text") or item.get("raw_text") or item.get("item") or ""
                if text.strip():
                    item_texts.append(text.strip())
                item_id = item.get("id") or item.get("itemId")
                if item_id:
                    item_ids.append(str(item_id))

            if not item_texts:
                self.last_sync_time = time.time()
                self.last_sync_status = "idle_empty_texts"
                return {"success": True, "count": 0, "message": "Alexa items had no text"}

            # Build prompt for the model
            formatted_input = "\n".join(f"- {t}" for t in item_texts)
            full_prompt = (
                f"{ALEXA_PARSE_PROMPT}\n\n"
                f"Input shopping list:\n"
                f"{formatted_input}\n\n"
                f"Please output each separated item on its own line starting with '- '."
            )

            try:
                model_result = self.sandbox.execute_prompt(full_prompt)
                response_text = model_result.get("response", "")
                if model_result.get("error"):
                    err_msg = model_result["error"]
                    logger.error(f"Model execution returned an error: {err_msg}")
                    self.last_sync_status = "model_error"
                    self.last_error = err_msg
                    return {"success": False, "error": f"Model failed: {err_msg}"}
            except Exception as e:
                logger.error(f"Model prompt execution raised an exception: {e}")
                self.last_sync_status = "model_exception"
                self.last_error = str(e)
                return {"success": False, "error": f"Model error: {e}"}

            parsed_items = parse_model_items(response_text)
            if not parsed_items:
                # Fallback: if model returned empty or could not parse, use raw texts
                logger.warning("Model returned no parsable items; falling back to raw items.")
                parsed_items = item_texts

            logger.info(f"Model parsed {len(parsed_items)} separate shopping items: {parsed_items}")

            # Insert parsed items into InFaPla shopping list
            try:
                for item_name in parsed_items:
                    self.storage.add_shopping(item_name)
            except Exception as e:
                logger.error(f"Failed to add items to InFaPla shopping list: {e}")
                self.last_sync_status = "storage_error"
                self.last_error = str(e)
                # DO NOT clear Alexa shopping list if storage insertion failed!
                return {"success": False, "error": f"Storage insertion failed: {e}"}

            # If successful, clear Alexa shopping list
            logger.info(f"Successfully inserted items into InFaPla. Clearing Alexa list (IDs: {item_ids})...")
            cleared = self.backend.clear_items(item_ids)
            if not cleared:
                logger.warning("Items were inserted into InFaPla, but clearing Alexa list returned False.")

            self.last_sync_time = time.time()
            self.last_sync_status = "success"
            self.last_error = None
            self.total_synced_items += len(parsed_items)

            return {
                "success": True,
                "raw_count": len(raw_items),
                "items_added": parsed_items,
                "cleared": cleared
            }

    def get_status(self) -> Dict[str, Any]:
        return {
            "configured": self.is_configured(),
            "running": self.running,
            "interval_seconds": self.interval,
            "backend_type": type(self.backend).__name__ if self.backend else None,
            "last_sync_time": self.last_sync_time,
            "last_sync_status": self.last_sync_status,
            "last_error": self.last_error,
            "total_synced_items": self.total_synced_items
        }


def handle_alexa_skill_webhook(
    event: Dict[str, Any],
    storage: Storage,
    sandbox: SandboxRunner,
    expected_skill_id: Optional[str] = None
) -> Tuple[Dict[str, Any], int]:
    """
    Handles direct HTTPS requests from the Alexa Skills Kit (no AWS Lambda/DynamoDB required).
    Directly processes items with the AI model and inserts them into InFaPla.
    """
    # Verify skill ID if configured
    if expected_skill_id:
        app_id = (
            event.get("session", {}).get("application", {}).get("applicationId")
            or event.get("context", {}).get("System", {}).get("application", {}).get("applicationId")
        )
        if app_id and app_id != expected_skill_id:
            logger.warning(f"Unauthorized Alexa request with skill ID: {app_id}")
            return {"error": "Unauthorized: Skill ID mismatch"}, 401

    request = event.get("request", {})
    req_type = request.get("type")

    def build_ask_response(speech: str, should_end: bool = True, reprompt: Optional[str] = None) -> Dict[str, Any]:
        resp = {
            "version": "1.0",
            "response": {
                "outputSpeech": {
                    "type": "PlainText",
                    "text": speech
                },
                "shouldEndSession": should_end
            }
        }
        if reprompt and not should_end:
            resp["response"]["reprompt"] = {
                "outputSpeech": {
                    "type": "PlainText",
                    "text": reprompt
                }
            }
        return resp

    times = random.randint(1, 10)
    maya_speech = f"Hello Maya, you should snip {times} times"

    if req_type == "LaunchRequest":
        return build_ask_response(
            speech=maya_speech,
            should_end=True
        ), 200

    elif req_type == "IntentRequest":
        intent = request.get("intent", {})
        intent_name = intent.get("name")

        if intent_name == "AddShoppingItemIntent":
            slots = intent.get("slots", {})
            item_slot = slots.get("items", {})
            raw_items = item_slot.get("value", "").strip()

            if not raw_items:
                return build_ask_response(
                    speech="I didn't catch any items. What would you like to add?",
                    should_end=False,
                    reprompt="What items should I add?"
                ), 200

            # Filter through AI model
            full_prompt = (
                f"{ALEXA_PARSE_PROMPT}\n\n"
                f"Input shopping list:\n"
                f"- {raw_items}\n\n"
                f"Please output each separated item on its own line starting with '- '."
            )

            parsed_items = []
            try:
                res = sandbox.execute_prompt(full_prompt)
                parsed_items = parse_model_items(res.get("response", ""))
            except Exception as e:
                logger.error(f"Error filtering items through model: {e}")

            if not parsed_items:
                parsed_items = [raw_items]

            # Insert into InFaPla shopping list
            try:
                for item_name in parsed_items:
                    storage.add_shopping(item_name)
            except Exception as e:
                logger.error(f"Failed to save items to shopping list: {e}")
                return build_ask_response(
                    speech="Sorry, I ran into an error saving the items to your shopping list."
                ), 200

            speech_text = f"Added {', '.join(parsed_items)} to your shopping list."
            return build_ask_response(speech=speech_text, should_end=True), 200

        elif intent_name in ("AMAZON.HelpIntent", "AMAZON.CancelIntent", "AMAZON.StopIntent"):
            return build_ask_response(
                speech=maya_speech,
                should_end=True
            ), 200

    elif req_type == "SessionEndedRequest":
        return build_ask_response(speech="", should_end=True), 200

    return build_ask_response(speech=maya_speech, should_end=True), 200
