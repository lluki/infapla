import sys
import argparse
import logging
from pathlib import Path

from .config import Config
from .server import run_server

def main():
    parser = argparse.ArgumentParser(description="InFaPla - Intelligent Family Planner")
    parser.add_argument("--dir", default=None, help="Path to dedicated MD data directory (default: ./data)")
    parser.add_argument("--host", default=None, help="HTTP host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="HTTP port (default: 8080)")
    parser.add_argument("--telegram-token", default=None, help="Telegram bot token")
    parser.add_argument("--telegram-allowed-users", default=None, help="Comma-separated list of allowed Telegram usernames or IDs")
    parser.add_argument("--git-interval", type=int, default=None, help="Git auto-commit interval in seconds (default: 30)")
    parser.add_argument("--model", default=None, help="agy model (default: gemini-3.8-flash-low)")
    parser.add_argument("--effort", default=None, help="agy reasoning effort: low|medium|high (default: low)")
    parser.add_argument("--alexa-interval", type=int, default=None, help="Alexa shopping list sync interval in seconds (default: 60)")
    parser.add_argument("--alexa-table", default=None, help="AWS DynamoDB table name for Alexa shopping items")
    parser.add_argument("--alexa-url", default=None, help="AWS Lambda Function URL / API Gateway endpoint for Alexa sync")
    parser.add_argument("--alexa-secret", default=None, help="Secret token / API key for Alexa sync HTTP endpoint")
    parser.add_argument("--aws-region", default=None, help="AWS region for DynamoDB (default: us-east-1)")
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
    if args.telegram_allowed_users:
        cfg.telegram_allowed_users = [u.strip().lstrip("@").lower() for u in args.telegram_allowed_users.split(",") if u.strip()]
    if args.git_interval:
        cfg.git_commit_interval = args.git_interval
    if args.model:
        cfg.agy_model = args.model
    if args.effort:
        cfg.agy_effort = args.effort
    if args.alexa_interval:
        cfg.alexa_sync_interval = args.alexa_interval
    if args.alexa_table:
        cfg.alexa_dynamodb_table = args.alexa_table
    if args.alexa_url:
        cfg.alexa_sync_url = args.alexa_url
    if args.alexa_secret:
        cfg.alexa_sync_secret = args.alexa_secret
    if args.aws_region:
        cfg.aws_region = args.aws_region
    if args.debug:
        cfg.debug = True

    run_server(cfg)

if __name__ == "__main__":
    main()
