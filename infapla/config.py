import os
from pathlib import Path
from dataclasses import dataclass, field

BASE_DIR = Path(__file__).resolve().parent.parent

@dataclass
class Config:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("INFAPLA_DATA_DIR", BASE_DIR / "data")).resolve())
    host: str = field(default_factory=lambda: os.environ.get("INFAPLA_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.environ.get("INFAPLA_PORT", "8080")))
    git_commit_interval: int = field(default_factory=lambda: int(os.environ.get("INFAPLA_GIT_INTERVAL", "30")))
    telegram_bot_token: str = field(default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN", "").strip())
    telegram_allowed_users: list = field(default_factory=lambda: [u.strip().lstrip("@").lower() for u in os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",") if u.strip()])
    sandbox_script: Path = field(default_factory=lambda: Path(os.environ.get("INFAPLA_SANDBOX_SCRIPT", BASE_DIR / "run-agy-sandboxed.sh")).resolve())
    agy_bin: str = field(default_factory=lambda: os.environ.get("AGY_BIN", "agy"))
    agy_model: str = field(default_factory=lambda: os.environ.get("AGY_MODEL", "gemini-3.8-flash-low"))
    agy_effort: str = field(default_factory=lambda: os.environ.get("AGY_EFFORT", "low"))
    calendar_ics_url: str = field(default_factory=lambda: os.environ.get("INFAPLA_CALENDAR_ICS_URL", "cal/60809c9cfb92adb9fe7693b32e23d9e8892925afada35d4a/calendar.ics"))
    timezone: str = field(default_factory=lambda: os.environ.get("INFAPLA_TIMEZONE", "Europe/Zurich"))
    debug: bool = field(default_factory=lambda: os.environ.get("DEBUG", "0").lower() in ("1", "true", "yes"))
    
    # Alexa / AWS Integration
    alexa_sync_enabled: bool = field(default_factory=lambda: os.environ.get("ALEXA_SYNC_ENABLED", "").lower() in ("1", "true", "yes"))
    alexa_sync_interval: int = field(default_factory=lambda: int(os.environ.get("INFAPLA_ALEXA_INTERVAL", "60")))
    alexa_dynamodb_table: str = field(default_factory=lambda: os.environ.get("ALEXA_DYNAMODB_TABLE", "").strip())
    alexa_sync_url: str = field(default_factory=lambda: os.environ.get("ALEXA_SYNC_URL", "").strip())
    alexa_sync_secret: str = field(default_factory=lambda: os.environ.get("ALEXA_SYNC_SECRET", "").strip())
    alexa_skill_id: str = field(default_factory=lambda: os.environ.get("ALEXA_SKILL_ID", "").strip())
    aws_region: str = field(default_factory=lambda: os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")).strip())
    aws_access_key_id: str = field(default_factory=lambda: os.environ.get("AWS_ACCESS_KEY_ID", "").strip())
    aws_secret_access_key: str = field(default_factory=lambda: os.environ.get("AWS_SECRET_ACCESS_KEY", "").strip())

    # Native Alexa Web API (Standard Alexa Shopping List via cookies)
    alexa_cookie: str = field(default_factory=lambda: os.environ.get("ALEXA_COOKIE", "").strip())
    alexa_csrf: str = field(default_factory=lambda: os.environ.get("ALEXA_CSRF", "").strip())
    alexa_amazon_domain: str = field(default_factory=lambda: os.environ.get("ALEXA_AMAZON_DOMAIN", "amazon.de").strip())

default_config = Config()
