"""
Central config: loads .env and exposes settings.
"""

import os
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()


def _get_int(name: str, default: int | None = None) -> int | None:
    v = os.getenv(name)
    if v is None or str(v).strip() == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _get_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name, "")
    if v == "" or v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")


# ───────────────────────────── Telegram ───────────────────────────── #

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

# Default destination (group/channel). Negative for groups/channels.
BOSS_CHAT_ID = _get_int("BOSS_CHAT_ID", 0) or 0

# Optional forum topic/thread id (for “topics” groups). 0/None = no topic → posts to General.
BOSS_THREAD_ID = _get_int("BOSS_THREAD_ID", 0) or 0

# If True, ignore DB overrides and always use .env BOSS_CHAT_ID / BOSS_THREAD_ID
FORCE_ENV_DESTINATION = _get_bool("FORCE_ENV_DESTINATION", False)


# ───────────────────────────── OpenAI / OCR ───────────────────────────── #

# OpenAI (used when OCR_MODE is "hybrid" or "openai")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

# OCR mode:
#   local  : only Tesseract (fast, no network)
#   hybrid : try local first; fallback to OpenAI if fields missing
#   openai : only OpenAI vision
#   manual : skip OCR; ask you to reply with username/followers
OCR_MODE = os.getenv("OCR_MODE", "hybrid").lower().strip()

# Tesseract path (Windows users set this if tesseract.exe is not in PATH)
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "").strip()

# Throttling / UX knobs
OPENAI_MAX_RPM = float(os.getenv("OPENAI_MAX_RPM", "3") or "3")
OPENAI_MAX_TPM = float(os.getenv("OPENAI_MAX_TPM", "100000") or "100000")
OPENAI_TOKENS_PER_IMAGE = float(os.getenv("OPENAI_TOKENS_PER_IMAGE", "900") or "900")

QUEUE_NOTIFY_THRESHOLD = int(os.getenv("QUEUE_NOTIFY_THRESHOLD", "5"))
MAX_START_WAIT_SEC = int(os.getenv("MAX_START_WAIT_SEC", "300"))


# ───────────────────────────── Timezone ───────────────────────────── #

TIMEZONE = os.getenv("TIMEZONE", "Africa/Lagos")

def tz() -> ZoneInfo:
    try:
        return ZoneInfo(TIMEZONE)
    except Exception:
        return ZoneInfo("Africa/Lagos")
