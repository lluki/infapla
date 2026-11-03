import re
import json
import time
import random
import logging
import threading
import uuid
import http.cookiejar
import urllib.request
import urllib.parse
from urllib.error import HTTPError
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from .config import Config
from .storage import Storage
from .sandbox import SandboxRunner

logger = logging.getLogger("infapla.alexa")

SESSION_FILENAME = ".alexa_session.json"

ALEXA_PARSE_SYSTEM_INSTRUCTION = (
    "You are a strict shopping list item text parser. "
    "Your ONLY role is to parse, clean, and split text into individual shopping list item names. "
    "CRITICAL: Do NOT use any tools. Do NOT read, view, create, edit, or modify any files on disk. "
    "Only respond with text containing the parsed items, one per line starting with '- '."
)

ALEXA_PARSE_PROMPT = (
    "Parse the input shopping list. Each item of input shopping list may contain items "
    "that are in fact multiple items. parse them and add them as separat items.\n"
    "Do NOT edit any files or use any tools.\n"
    "Please output each separated item on its own line starting with '- '."
)


def get_session_file_path(data_dir: Path) -> Path:
    return Path(data_dir) / SESSION_FILENAME


def load_saved_session(data_dir: Path) -> Optional[Dict[str, Any]]:
    path = get_session_file_path(data_dir)
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and data.get("cookie"):
                return data
    except Exception as e:
        logger.warning(f"Failed to read saved Alexa session from {path}: {e}")
    return None


def save_session_data(data_dir: Path, cookie: str, csrf: str = "", domain: str = "amazon.de") -> Dict[str, Any]:
    target = get_session_file_path(data_dir)
    data = {
        "cookie": cookie.strip(),
        "csrf": csrf.strip() if csrf else "",
        "domain": domain.strip().lower() if domain else "amazon.de",
        "updated_at": int(time.time())
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # Ensure .alexa_session.json is in data/.gitignore so credentials aren't committed
    gi = Path(data_dir) / ".gitignore"
    try:
        content = gi.read_text(encoding="utf-8") if gi.exists() else ""
        if SESSION_FILENAME not in content:
            with open(gi, "a", encoding="utf-8") as f:
                f.write(f"\n{SESSION_FILENAME}\n")
    except Exception as e:
        logger.debug(f"Failed to update data/.gitignore: {e}")

    logger.info(f"Saved Alexa session to {target} (domain={data['domain']})")
    return data


def delete_saved_session(data_dir: Path) -> bool:
    target = get_session_file_path(data_dir)
    if target.exists():
        try:
            target.unlink()
            logger.info(f"Removed Alexa session file {target}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove session file {target}: {e}")
            return False
    return False


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
        "i've",
        "sure",
        "output:",
        "shopping list:",
        "items to add:",
        "add only",
        "note:",
        "the following",
        "added to",
        "items:",
        "list:",
        "updated",
    )

    has_bullets = any(
        re.match(r"^(?:[-*+]|\d+[\.\)])\s+", l.strip())
        for l in lines
    )

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # If the output contains bullets, ignore any line without a bullet (prose / explanations)
        if has_bullets and not re.match(r"^(?:[-*+]|\d+[\.\)])\s+", line):
            continue

        lower_line = line.lower()
        if any(lower_line.startswith(prefix) for prefix in skip_prefixes):
            continue

        # Ignore lines ending in colon (headers / introductions)
        if line.endswith(":"):
            continue

        # Ignore lines mentioning file paths / markdown links
        if "file://" in line or "list.md" in line:
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
                if p and not any(p.lower().startswith(prefix) for prefix in skip_prefixes):
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
            if (
                p
                and not any(p.lower().startswith(prefix) for prefix in skip_prefixes)
                and "file://" not in p
                and not p.endswith(":")
            ):
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
    Connects to Amazon's Alexa shopping list API to read and clear the standard native Alexa shopping list.
    Uses Amazon's modern alexashoppinglists API:
      - Lists: https://www.{domain}/alexashoppinglists/api/v2/lists/fetch
      - Items: https://www.{domain}/alexashoppinglists/api/v2/lists/{list_id}/items/fetch?limit=100
      - Delete: https://www.{domain}/alexashoppinglists/api/v2/lists/{list_id}/items/{item_id}?version={version}
    With automatic fallback to legacy https://alexa.{domain}/api/todos if supported.
    Works with standard "Alexa, add [item] to my shopping list" without needing custom skills.
    Requires an authenticated Amazon web session cookie bundle and csrf token.
    """

    def __init__(self, cookie: str, csrf: str, domain: str = "amazon.de"):
        self.cookie = cookie.strip()
        self.csrf = csrf.strip()
        clean_domain = domain.strip().lower()
        for prefix in ("alexa.", "www."):
            if clean_domain.startswith(prefix):
                clean_domain = clean_domain[len(prefix):]
        self.domain = clean_domain
        self.retail_url = f"https://www.{self.domain}"
        self.alexa_url = f"https://alexa.{self.domain}"
        self.base_url = self.alexa_url
        self._item_metadata: Dict[str, Dict[str, Any]] = {}

    def _get_headers(self, content_type: Optional[str] = "application/json; charset=utf-8") -> Dict[str, str]:
        headers = {
            "Cookie": self.cookie,
            "csrf": self.csrf,
            "anti-csrftoken-a2z": self.csrf,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def fetch_items(self) -> List[Dict[str, Any]]:
        # 1. Try modern alexashoppinglists API first
        domains_to_try = [self.retail_url]
        if "amazon.com" not in self.retail_url:
            domains_to_try.append("https://www.amazon.com")

        last_error = None
        for base in domains_to_try:
            try:
                fetch_lists_url = f"{base}/alexashoppinglists/api/v2/lists/fetch"
                req = urllib.request.Request(
                    fetch_lists_url,
                    data=b"{}",
                    headers=self._get_headers(),
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                list_info_list = data.get("listInfoList")
                if list_info_list is None:
                    raise ValueError(f"Endpoint {base} did not return listInfoList")
                shop_list = next((l for l in list_info_list if l.get("listType") == "SHOP"), None)
                if not shop_list:
                    shop_list = next((l for l in list_info_list if "SHOPPING" in str(l.get("listId", "")).upper()), None)
                if not shop_list and list_info_list:
                    shop_list = list_info_list[0]

                if not shop_list:
                    return []

                list_id = shop_list["listId"]
                items_url = f"{base}/alexashoppinglists/api/v2/lists/{urllib.parse.quote(str(list_id))}/items/fetch?limit=100"
                req_items = urllib.request.Request(
                    items_url,
                    data=b"{}",
                    headers=self._get_headers(),
                    method="POST"
                )
                with urllib.request.urlopen(req_items, timeout=15) as resp_items:
                    items_data = json.loads(resp_items.read().decode("utf-8"))

                items = []
                for it in items_data.get("itemInfoList", []):
                    status = str(it.get("itemStatus", "")).upper()
                    if status == "ACTIVE" and it.get("itemName"):
                        i_id = str(it["itemId"])
                        ver = it.get("version", 1)
                        self._item_metadata[i_id] = {
                            "base_url": base,
                            "list_id": list_id,
                            "version": ver
                        }
                        items.append({
                            "id": i_id,
                            "text": it["itemName"],
                            "version": ver,
                            "list_id": list_id
                        })
                return items
            except Exception as e:
                last_error = e
                logger.debug(f"Modern alexashoppinglists API attempt failed for {base}: {e}")

        # 2. Fallback to legacy alexa.amazon.{domain}/api/todos
        legacy_url = f"{self.alexa_url}/api/todos?type=SHOPPING_ITEM&size=100&completed=false"
        try:
            legacy_headers = self._get_headers(content_type=None)
            legacy_headers["Referer"] = f"{self.alexa_url}/spa/index.html"
            req = urllib.request.Request(legacy_url, headers=legacy_headers, method="GET")
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                values = data.get("values", [])
                return [
                    {"id": v["id"], "text": v.get("text", "")}
                    for v in values
                    if not v.get("complete", False) and v.get("text")
                ]
        except Exception as legacy_err:
            logger.error(f"Failed to fetch native Alexa shopping list: modern err={last_error}, legacy err={legacy_err}")
            raise last_error or legacy_err

    def clear_items(self, item_ids: List[str]) -> bool:
        if not item_ids:
            return True
        success = True
        for item_id in item_ids:
            item_id_str = str(item_id)
            meta = self._item_metadata.get(item_id_str)
            if meta and "list_id" in meta:
                base = meta.get("base_url", self.retail_url)
                lid = meta["list_id"]
                ver = meta.get("version", 1)
                url = f"{base}/alexashoppinglists/api/v2/lists/{urllib.parse.quote(str(lid))}/items/{urllib.parse.quote(item_id_str)}?version={ver}"
            else:
                url = f"{self.alexa_url}/api/todos/{urllib.parse.quote(item_id_str)}"

            headers = self._get_headers(content_type=None)
            req = urllib.request.Request(url, headers=headers, method="DELETE")
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
        else:
            self.backend = self._resolve_backend()

    def _resolve_backend(self) -> Optional[BaseAlexaBackend]:
        # 1. Check saved session in data directory
        saved = load_saved_session(self.storage.data_dir)
        if saved and saved.get("cookie"):
            return NativeAlexaBackend(
                cookie=saved["cookie"],
                csrf=saved.get("csrf", ""),
                domain=saved.get("domain", "amazon.de")
            )

        # 2. Check environment config for native web cookies
        if self.config.alexa_cookie and self.config.alexa_csrf:
            return NativeAlexaBackend(
                cookie=self.config.alexa_cookie,
                csrf=self.config.alexa_csrf,
                domain=self.config.alexa_amazon_domain
            )

        # 3. Check HTTP / Lambda function URL
        if self.config.alexa_sync_url:
            return HttpAlexaBackend(
                endpoint_url=self.config.alexa_sync_url,
                secret_token=self.config.alexa_sync_secret
            )

        # 4. Check DynamoDB backend
        if self.config.alexa_dynamodb_table:
            return DynamoDBAlexaBackend(
                table_name=self.config.alexa_dynamodb_table,
                region_name=self.config.aws_region,
                aws_access_key_id=self.config.aws_access_key_id,
                aws_secret_access_key=self.config.aws_secret_access_key
            )

        return None

    def reload_backend(self) -> bool:
        """
        Reloads backend configuration (e.g. after user logs in or updates session).
        Automatically starts the background sync worker if configured and enabled.
        """
        with self.lock:
            self.backend = self._resolve_backend()
            is_conf = self.is_configured()
            if self.config.alexa_sync_enabled:
                if is_conf and not self.running:
                    self.start()
                elif not is_conf and self.running:
                    self.stop()
            else:
                if self.running:
                    self.stop()
            logger.info(f"Reloaded Alexa backend: {type(self.backend).__name__ if self.backend else 'None'} (configured={is_conf}, enabled={self.config.alexa_sync_enabled})")
            return is_conf

    def test_connection(self) -> Dict[str, Any]:
        """
        Performs a read-only test against the Alexa backend to verify credentials and connectivity.
        Does not clear or modify items.
        """
        backend = self.backend or self._resolve_backend()
        if not backend:
            return {
                "success": False,
                "error": "Alexa is not configured. Please log in or provide credentials."
            }
        try:
            items = backend.fetch_items()
            sample_titles = [i.get("text", "") for i in items if i.get("text")][:5]
            return {
                "success": True,
                "count": len(items),
                "samples": sample_titles,
                "backend_type": type(backend).__name__
            }
        except Exception as e:
            logger.warning(f"Alexa test connection failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "backend_type": type(backend).__name__
            }

    def is_configured(self) -> bool:
        return self.backend is not None or bool(
            load_saved_session(self.storage.data_dir)
            or (self.config.alexa_cookie and self.config.alexa_csrf)
            or self.config.alexa_sync_url
            or self.config.alexa_dynamodb_table
        )

    def start(self, force: bool = False) -> None:
        if not self.config.alexa_sync_enabled and not force:
            logger.info("Alexa shopping sync poller is disabled (ALEXA_SYNC_ENABLED=0). Skipping background worker.")
            return

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
                model_result = self.sandbox.execute_prompt(
                    full_prompt,
                    system_instruction=ALEXA_PARSE_SYSTEM_INSTRUCTION,
                    read_only=True
                )
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
                existing_data = self.storage.get_shopping_data()
                existing_active = {
                    i["text"].strip().lower()
                    for i in existing_data.get("items", [])
                    if not i.get("done")
                }
                added_items = []
                for item_name in parsed_items:
                    clean_name = item_name.strip()
                    if clean_name.lower() in existing_active:
                        logger.info(f"Item '{clean_name}' is already active in shopping list; skipping duplicate.")
                        continue
                    self.storage.add_shopping(clean_name)
                    existing_active.add(clean_name.lower())
                    added_items.append(clean_name)
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
            self.total_synced_items += len(added_items)

            return {
                "success": True,
                "raw_count": len(raw_items),
                "items_added": added_items if added_items else parsed_items,
                "cleared": cleared
            }

    def get_status(self) -> Dict[str, Any]:
        saved = load_saved_session(self.storage.data_dir)
        active_domain = None
        if isinstance(self.backend, NativeAlexaBackend):
            active_domain = self.backend.domain
        elif saved:
            active_domain = saved.get("domain")
        elif self.config.alexa_amazon_domain:
            active_domain = self.config.alexa_amazon_domain

        return {
            "configured": self.is_configured(),
            "enabled": self.config.alexa_sync_enabled,
            "running": self.running,
            "interval_seconds": self.interval,
            "backend_type": type(self.backend).__name__ if self.backend else None,
            "domain": active_domain,
            "session_saved": bool(saved),
            "session_updated_at": saved.get("updated_at") if saved else None,
            "last_sync_time": self.last_sync_time,
            "last_sync_status": self.last_sync_status,
            "last_error": self.last_error,
            "total_synced_items": self.total_synced_items
        }


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Prevents urllib from automatically following redirects so we can intercept login steps."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class AlexaLoginProxy:
    """
    Manages interactive captive Amazon login sessions.
    Handles login redirection, HTML rewriting, cookie capture, and CSRF token extraction.
    """
    def __init__(self, data_dir: Path, on_success_callback=None):
        self.data_dir = Path(data_dir)
        self.on_success_callback = on_success_callback
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()

    def create_session(self, domain: str = "amazon.de", prefix: str = "") -> Tuple[str, str]:
        with self.lock:
            # Clean up sessions older than 20 minutes
            now = time.time()
            expired = [sid for sid, s in self.sessions.items() if now - s["created_at"] > 1200]
            for sid in expired:
                del self.sessions[sid]

            sid = uuid.uuid4().hex
            clean_domain = domain.strip().lower()
            if clean_domain.startswith("alexa."):
                clean_domain = clean_domain[6:]
            if clean_domain.startswith("www."):
                clean_domain = clean_domain[4:]
            if not clean_domain.startswith("amazon."):
                clean_domain = f"amazon.{clean_domain}"

            cj = http.cookiejar.CookieJar()
            
            # Map clean domain to Amazon's exact assoc_handle
            handle_map = {
                "amazon.com": "amzn_dp_project_dee",
                "amazon.de": "amzn_dp_project_dee_de",
                "amazon.co.uk": "amzn_dp_project_dee_uk",
                "amazon.fr": "amzn_dp_project_dee_fr",
                "amazon.it": "amzn_dp_project_dee_it",
                "amazon.es": "amzn_dp_project_dee_es",
            }
            assoc_handle = handle_map.get(clean_domain, "amzn_dp_project_dee")

            # Official Amazon signin URL for Alexa OAuth / web login
            start_url = (
                f"https://www.{clean_domain}/ap/signin?"
                f"showRmrMe=1&"
                f"openid.return_to=https%3A%2F%2Falexa.{clean_domain}%2Flogin&"
                f"openid.identity=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&"
                f"openid.assoc_handle={assoc_handle}&"
                f"openid.mode=checkid_setup&"
                f"openid.claimed_id=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0%2Fidentifier_select&"
                f"openid.ns=http%3A%2F%2Fspecs.openid.net%2Fauth%2F2.0&"
            )

            self.sessions[sid] = {
                "created_at": now,
                "domain": clean_domain,
                "prefix": prefix,
                "cookie_jar": cj,
                "status": "pending",
                "error": None
            }
            logger.info(f"[Alexa Proxy] Created login session {sid[:8]} for domain {clean_domain} (prefix={prefix}, assoc_handle={assoc_handle})")
            return sid, start_url

    def get_session(self, sid: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.sessions.get(sid)

    def _has_authenticated_cookies(self, cookie_jar: http.cookiejar.CookieJar) -> bool:
        cookie_names = set(c.name for c in cookie_jar)
        # Real authentication tokens set by Amazon after user credentials verified:
        if any(k in cookie_names for k in ("at-main", "sess-at-main", "x-main")):
            return True
        if "ubid-main" in cookie_names and "session-token" in cookie_names:
            return True
        return False

    def _is_completion_url(self, url: str, domain: str) -> bool:
        parsed = urllib.parse.urlparse(url)
        netloc = parsed.netloc.lower()
        path = parsed.path.lower()
        # Completion is reached when the user's browser arrives on alexa.{domain} (not www.amazon.{domain}), or /ap/maplanding
        if netloc == f"alexa.{domain}" and (path.startswith("/spa") or path.startswith("/login") or path == "/"):
            return True
        if path == "/ap/maplanding":
            return True
        return False

    def _extract_cookie_str(self, cookie_jar: http.cookiejar.CookieJar) -> str:
        return "; ".join(f"{c.name}={c.value}" for c in cookie_jar)

    def _extract_csrf(self, cookie_jar: http.cookiejar.CookieJar, domain: str) -> str:
        # 1. Check if csrf cookie is already in the cookie jar
        for c in cookie_jar:
            if c.name.lower() == "csrf":
                return c.value

        # 2. Query alexa.{domain}/api/language or /spa/index.html to extract csrf
        url = f"https://alexa.{domain}/api/language"
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": f"https://alexa.{domain}/spa/index.html"
            }
        )
        try:
            with opener.open(req, timeout=10) as resp:
                for c in cookie_jar:
                    if c.name.lower() == "csrf":
                        return c.value
                csrf_header = resp.headers.get("csrf")
                if csrf_header:
                    return csrf_header
        except Exception as e:
            logger.debug(f"Failed to fetch csrf from {url}: {e}")

        # Check for any cookie containing csrf
        for c in cookie_jar:
            if "csrf" in c.name.lower():
                return c.value

        return ""

    def proxy_request(
        self,
        sid: str,
        target_url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        data: Optional[bytes] = None,
        proxy_path: str = "/api/alexa/login/proxy"
    ) -> Tuple[int, Dict[str, str], bytes]:
        sess = self.get_session(sid)
        if not sess:
            logger.warning(f"[Alexa Proxy] Session {sid} not found or expired")
            return 400, {"Content-Type": "text/html; charset=utf-8"}, b"<h3>Invalid or expired login session. Please close this window and try again.</h3>"

        cj = sess["cookie_jar"]
        domain = sess["domain"]
        prefix = sess.get("prefix", "")
        if prefix and not proxy_path.startswith(prefix):
            proxy_path = f"{prefix.rstrip('/')}/api/alexa/login/proxy"

        # Parse target URL
        parsed_target = urllib.parse.urlparse(target_url)
        if not parsed_target.scheme:
            target_url = f"https://www.{domain}" + (target_url if target_url.startswith("/") else "/" + target_url)
            parsed_target = urllib.parse.urlparse(target_url)

        req_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": f"https://www.{domain}/",
        }
        if headers:
            if "content-type" in headers:
                req_headers["Content-Type"] = headers["content-type"]
            elif "Content-Type" in headers:
                req_headers["Content-Type"] = headers["Content-Type"]

        cookie_names_before = [c.name for c in cj]
        logger.info(f"[Alexa Proxy] {method} {target_url} (SID={sid[:8]}, cookies={cookie_names_before}, body_len={len(data) if data else 0})")

        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj), NoRedirectHandler)
        req = urllib.request.Request(
            target_url,
            data=data if method.upper() == "POST" else None,
            headers=req_headers,
            method=method.upper()
        )

        try:
            resp = opener.open(req, timeout=20)
            status_code = resp.status
            resp_headers = dict(resp.headers)
            body = resp.read()
        except urllib.error.HTTPError as e:
            status_code = e.code
            resp_headers = dict(e.headers)
            body = e.read() if hasattr(e, "read") else b""
        except Exception as e:
            logger.error(f"[Alexa Proxy] Network error requesting {target_url}: {e}", exc_info=True)
            return 502, {"Content-Type": "text/html; charset=utf-8"}, f"<h3>Error communicating with Amazon: {e}</h3>".encode("utf-8")

        cookie_names_after = [c.name for c in cj]
        logger.info(f"[Alexa Proxy] Amazon HTTP {status_code} for {target_url} (cookies_now={cookie_names_after})")

        success_loc = f"{proxy_path.rsplit('/', 1)[0]}/success"

        # Handle redirects (301, 302, 303, 307)
        if status_code in (301, 302, 303, 307):
            location = resp_headers.get("Location") or resp_headers.get("location")
            if location:
                resolved_loc = urllib.parse.urljoin(target_url, location)
                logger.info(f"[Alexa Proxy] Redirect to: {resolved_loc}")

                # Check if this redirect is toward completion (alexa login or maplanding)
                if self._is_completion_url(resolved_loc, domain):
                    logger.info(f"[Alexa Proxy] Completion redirect detected: {resolved_loc}")
                    # Follow completion endpoint to allow Alexa to set CSRF and session cookies
                    try:
                        comp_req = urllib.request.Request(
                            resolved_loc,
                            headers={
                                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                                "Referer": f"https://www.{domain}/"
                            }
                        )
                        comp_resp = opener.open(comp_req, timeout=15)
                        logger.info(f"[Alexa Proxy] Visited completion target: HTTP {comp_resp.status}")
                    except urllib.error.HTTPError as ce:
                        logger.info(f"[Alexa Proxy] Visited completion target: HTTP {ce.code} (Location: {ce.headers.get('Location')})")
                    except Exception as ce:
                        logger.warning(f"[Alexa Proxy] Exception visiting completion target: {ce}")

                    if self._has_authenticated_cookies(cj):
                        cookie_str = self._extract_cookie_str(cj)
                        csrf = self._extract_csrf(cj, domain)
                        save_session_data(self.data_dir, cookie_str, csrf, domain)
                        sess["status"] = "success"
                        if self.on_success_callback:
                            try:
                                self.on_success_callback()
                            except Exception as cb_err:
                                logger.error(f"[Alexa Proxy] Callback error on login success: {cb_err}")
                        logger.info(f"[Alexa Proxy] *** LOGIN SUCCESSFUL! *** Saved session for domain={domain}, csrf={csrf[:10] if csrf else 'none'}...")
                        return 302, {"Location": success_loc}, b""
                    else:
                        logger.warning(f"[Alexa Proxy] Reached completion target but missing authenticated cookies: {[c.name for c in cj]}")

                proxy_loc = f"{proxy_path}?sid={sid}&url={urllib.parse.quote(resolved_loc)}"
                return 302, {"Location": proxy_loc}, b""

        # Check if 200 response on completion target with auth cookies
        if self._is_completion_url(target_url, domain) and self._has_authenticated_cookies(cj):
            cookie_str = self._extract_cookie_str(cj)
            csrf = self._extract_csrf(cj, domain)
            save_session_data(self.data_dir, cookie_str, csrf, domain)
            sess["status"] = "success"
            if self.on_success_callback:
                try:
                    self.on_success_callback()
                except Exception as cb_err:
                    logger.error(f"[Alexa Proxy] Callback error on login success: {cb_err}")
            logger.info(f"[Alexa Proxy] *** LOGIN SUCCESSFUL (200)! *** Saved session for domain={domain}, csrf={csrf[:10] if csrf else 'none'}...")
            return 302, {"Location": success_loc}, b""

        # Handle HTML response
        content_type = resp_headers.get("Content-Type", "").lower()
        if "text/html" in content_type:
            try:
                html_text = body.decode("utf-8", errors="ignore")
                base_host = f"{parsed_target.scheme}://{parsed_target.netloc}"

                # Inject base tag so styles, JS, and images load correctly
                if "<head>" in html_text:
                    html_text = html_text.replace("<head>", f'<head><base href="{base_host}/">', 1)
                elif "<head " in html_text:
                    html_text = re.sub(r"(<head\b[^>]*>)", rf'\1<base href="{base_host}/">', html_text, count=1)

                # Rewrite form actions to preserve the true Amazon target URL
                def rewrite_form_tag(match):
                    tag = match.group(0)
                    action_match = re.search(r'action=[\"\']([^\"\']*)[\"\']', tag)
                    if action_match:
                        old_action = action_match.group(1)
                        resolved = urllib.parse.urljoin(target_url, old_action)
                        new_action = f"{proxy_path}?sid={sid}&url={urllib.parse.quote(resolved)}"
                        tag = tag.replace(action_match.group(0), f'action="{new_action}" data-amazon-action="{resolved}"')
                    return tag

                html_text = re.sub(r'<form\b[^>]*>', rewrite_form_tag, html_text)

                # Inject JavaScript helper
                js_helper = f"""
                <script>
                (function() {{
                    var sid = "{sid}";
                    var currentUrl = "{target_url}";
                    var baseHost = "{base_host}";
                    var proxyPath = "{proxy_path}";
                    if (window.location.pathname.indexOf("login/proxy") !== -1) {{
                        proxyPath = window.location.pathname;
                    }}

                    console.log("[InFaPla Proxy] Login helper initialized for sid:", sid);

                    // Intercept form submissions
                    document.addEventListener("submit", function(e) {{
                        var form = e.target;
                        var amazonAction = form.getAttribute("data-amazon-action");
                        if (!amazonAction) {{
                            var rawAct = form.getAttribute("action") || "";
                            var match = rawAct.match(/[?&]url=([^&]+)/);
                            if (match) {{
                                amazonAction = decodeURIComponent(match[1]);
                            }} else {{
                                amazonAction = new URL(rawAct, baseHost).href;
                            }}
                        }}
                        var targetAction = window.location.origin + proxyPath + "?sid=" + encodeURIComponent(sid) + "&url=" + encodeURIComponent(amazonAction);
                        form.action = targetAction;
                        console.log("[InFaPla Proxy] Submitting form to:", targetAction, "Targeting Amazon:", amazonAction);
                    }}, true);

                    // Intercept link clicks
                    document.addEventListener("click", function(e) {{
                        var a = e.target.closest("a");
                        if (a && a.href && !a.href.startsWith("javascript:") && !a.href.startsWith("#")) {{
                            var targetHref = a.getAttribute("data-amazon-href");
                            if (!targetHref) {{
                                var match = a.href.match(/[?&]url=([^&]+)/);
                                if (match) {{
                                    targetHref = decodeURIComponent(match[1]);
                                }} else if (!a.href.includes(proxyPath)) {{
                                    targetHref = a.href;
                                }}
                            }}
                            if (targetHref) {{
                                e.preventDefault();
                                var nextProxy = window.location.origin + proxyPath + "?sid=" + encodeURIComponent(sid) + "&url=" + encodeURIComponent(targetHref);
                                console.log("[InFaPla Proxy] Navigating link to:", nextProxy, "Targeting Amazon:", targetHref);
                                window.location.href = nextProxy;
                            }}
                        }}
                    }}, true);
                }})();
                </script>
                """
                if "</body>" in html_text:
                    html_text = html_text.replace("</body>", f"{js_helper}</body>", 1)
                else:
                    html_text += js_helper

                body = html_text.encode("utf-8")
            except Exception as parse_err:
                logger.error(f"[Alexa Proxy] Error rewriting proxied Amazon HTML: {parse_err}")

        # Filter response headers
        clean_headers = {}
        for k, v in resp_headers.items():
            k_lower = k.lower()
            if k_lower in ("content-type", "cache-control", "expires", "pragma"):
                clean_headers[k] = v

        return status_code, clean_headers, body


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
                res = sandbox.execute_prompt(
                    full_prompt,
                    system_instruction=ALEXA_PARSE_SYSTEM_INSTRUCTION,
                    read_only=True
                )
                parsed_items = parse_model_items(res.get("response", ""))
            except Exception as e:
                logger.error(f"Error filtering items through model: {e}")

            if not parsed_items:
                parsed_items = [raw_items]

            # Insert into InFaPla shopping list
            try:
                existing_data = storage.get_shopping_data()
                existing_active = {
                    i["text"].strip().lower()
                    for i in existing_data.get("items", [])
                    if not i.get("done")
                }
                for item_name in parsed_items:
                    clean_name = item_name.strip()
                    if clean_name.lower() in existing_active:
                        logger.info(f"Item '{clean_name}' is already active in shopping list; skipping duplicate.")
                        continue
                    storage.add_shopping(clean_name)
                    existing_active.add(clean_name.lower())
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
