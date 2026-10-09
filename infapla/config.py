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
    sandbox_script: Path = field(default_factory=lambda: (BASE_DIR / "run-agy-sandboxed.sh").resolve())
    agy_bin: str = field(default_factory=lambda: os.environ.get("AGY_BIN", "agy"))
    debug: bool = field(default_factory=lambda: os.environ.get("DEBUG", "0").lower() in ("1", "true", "yes"))

default_config = Config()
