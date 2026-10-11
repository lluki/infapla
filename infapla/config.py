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

default_config = Config()
