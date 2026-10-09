import logging
from pathlib import Path
from typing import Optional

from .config import Config, default_config
from .storage import Storage
from .git_manager import GitManager, PeriodicCommitter
from .sandbox import SandboxRunner
from .telegram_bot import TelegramBot

logger = logging.getLogger("infapla.daemon")

class InFaPlaDaemon:
    def __init__(self, config: Optional[Config] = None):
        self.config = config or default_config
        self.storage = Storage(self.config.data_dir)
        self.git_manager = GitManager(self.config.data_dir)
        self.sandbox = SandboxRunner(self.config.data_dir, self.config.sandbox_script)
        self.committer = PeriodicCommitter(self.git_manager, self.config.git_commit_interval)
        self.telegram = TelegramBot(self.config.telegram_bot_token, self.storage, self.sandbox)
        self._is_running = False

    def start(self) -> None:
        if self._is_running:
            return
        self._is_running = True
        logger.info("Starting InFaPla background daemon...")
        
        # Start periodic git committer
        self.committer.start()

        # Start telegram bot if token provided
        if self.telegram.is_configured():
            self.telegram.start()
        else:
            logger.info("Telegram bot not configured (set TELEGRAM_BOT_TOKEN to enable).")

    def stop(self) -> None:
        if not self._is_running:
            return
        logger.info("Stopping InFaPla background daemon...")
        self.committer.stop()
        self.telegram.stop()
        self._is_running = False

    def is_running(self) -> bool:
        return self._is_running
