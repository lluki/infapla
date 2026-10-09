import sys
import argparse
import logging
from pathlib import Path

from infapla.config import Config
from infapla.server import run_server

def main():
    parser = argparse.ArgumentParser(description="InFaPla - Intelligent Family Planner")
    parser.add_argument("--dir", default=None, help="Path to dedicated MD data directory (default: ./data)")
    parser.add_argument("--host", default=None, help="HTTP host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="HTTP port (default: 8080)")
    parser.add_argument("--telegram-token", default=None, help="Telegram bot token")
    parser.add_argument("--git-interval", type=int, default=None, help="Git auto-commit interval in seconds (default: 30)")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )

    cfg = Config()
    if args.dir:
        cfg.data_dir = Path(args.dir).resolve()
    if args.host:
        cfg.host = args.host
    if args.port:
        cfg.port = args.port
    if args.telegram_token:
        cfg.telegram_bot_token = args.telegram_token
    if args.git_interval:
        cfg.git_commit_interval = args.git_interval
    if args.debug:
        cfg.debug = True

    run_server(cfg)

if __name__ == "__main__":
    main()
