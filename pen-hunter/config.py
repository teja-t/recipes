"""Centralized config: loads .env and exposes settings to the rest of the app."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

EBAY_API_KEY = os.getenv("EBAY_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

DB_PATH = ROOT / "pen-hunter.db"
KEYWORDS_PATH = ROOT / "keywords.yaml"

POLL_INTERVAL_EBAY = 60
POLL_INTERVAL_MERCARI = 300
POLL_INTERVAL_BUNJANG = 600

CLAUDE_MODEL = "claude-sonnet-4-20250514"
