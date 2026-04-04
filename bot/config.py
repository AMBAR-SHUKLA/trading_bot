"""
config.py — Centralised configuration for the Binance Futures trading bot.

Loads API credentials from environment variables / .env file and exposes
project-wide constants.  No secret ever touches source control.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load .env file (if present) ────────────────────────────────────────────────
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path, override=False)


# ── Binance Futures Testnet ────────────────────────────────────────────────────
BASE_URL: str = os.getenv("BINANCE_BASE_URL", "https://testnet.binancefuture.com")
API_KEY: str = os.getenv("BINANCE_API_KEY", "")
API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")

# ── Order configuration ────────────────────────────────────────────────────────
SUPPORTED_ORDER_TYPES: tuple[str, ...] = ("MARKET", "LIMIT", "STOP_LIMIT")
SUPPORTED_SIDES: tuple[str, ...] = ("BUY", "SELL")

# ── Networking ─────────────────────────────────────────────────────────────────
REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "10"))   # seconds
MAX_RETRIES: int = int(os.getenv("MAX_RETRIES", "3"))
RETRY_BACKOFF_FACTOR: float = float(os.getenv("RETRY_BACKOFF_FACTOR", "1.5"))

# ── Risk controls ─────────────────────────────────────────────────────────────
MAX_ORDER_QUANTITY: float = float(os.getenv("MAX_ORDER_QUANTITY", "100.0"))
CONFIRM_LARGE_ORDERS: bool = os.getenv("CONFIRM_LARGE_ORDERS", "true").lower() == "true"
LARGE_ORDER_THRESHOLD: float = float(os.getenv("LARGE_ORDER_THRESHOLD", "10.0"))

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_DIR: Path = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE: Path = LOG_DIR / "trading_bot.log"
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

# ── Database ───────────────────────────────────────────────────────────────────
DB_PATH: Path = Path(__file__).resolve().parent.parent / "orders.db"


def validate_credentials() -> bool:
    """Return True if API credentials are configured."""
    return bool(API_KEY and API_SECRET)


def get_masked_key() -> str:
    """Return a masked version of the API key for safe display."""
    if not API_KEY:
        return "<not set>"
    return API_KEY[:6] + "..." + API_KEY[-4:]
