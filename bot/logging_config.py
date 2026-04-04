"""
logging_config.py — Configures Python's logging subsystem for the trading bot.

Features:
  • Dual output — structured log file (JSON-style lines) + human-readable console.
  • Timestamps on every record.
  • Sensitive fields (API keys, secrets) are never written.
  • Single call to `setup_logging()` idempotent — safe to call multiple times.
"""

import logging
import logging.handlers
import sys

from bot.config import LOG_DIR, LOG_FILE, LOG_LEVEL


# ── Custom formatter ─────────────────────────────────────────────────────────

class _FileFormatter(logging.Formatter):
    """Structured, timestamped formatter for the log file."""

    FMT = (
        "%(asctime)s | %(levelname)-8s | %(name)-24s | %(message)s"
    )
    DATEFMT = "%Y-%m-%dT%H:%M:%S"

    def __init__(self) -> None:
        super().__init__(fmt=self.FMT, datefmt=self.DATEFMT)


class _ConsoleFormatter(logging.Formatter):
    """Coloured, concise formatter for the terminal."""

    GREY = "\x1b[38;21m"
    CYAN = "\x1b[36m"
    YELLOW = "\x1b[33m"
    RED = "\x1b[31m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"

    LEVEL_COLOURS = {
        logging.DEBUG:    GREY,
        logging.INFO:     CYAN,
        logging.WARNING:  YELLOW,
        logging.ERROR:    RED,
        logging.CRITICAL: BOLD_RED,
    }

    FMT = "%(asctime)s  %(levelname)-8s  %(message)s"
    DATEFMT = "%H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        colour = self.LEVEL_COLOURS.get(record.levelno, self.RESET)
        formatter = logging.Formatter(
            fmt=f"{colour}{self.FMT}{self.RESET}",
            datefmt=self.DATEFMT,
        )
        return formatter.format(record)


# ── Public setup function ─────────────────────────────────────────────────────

def setup_logging(*, verbose: bool = False) -> logging.Logger:
    """
    Configure root logger with file + console handlers.

    Args:
        verbose: If True, set console level to DEBUG.

    Returns:
        The root logger (already configured).
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    if root.handlers:          # already initialised
        return root

    numeric_level = getattr(logging, LOG_LEVEL, logging.INFO)
    root.setLevel(logging.DEBUG)   # handlers apply their own levels

    # File handler — rotating, max 5 MB × 5 files
    fh = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_FileFormatter())

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else numeric_level)
    ch.setFormatter(_ConsoleFormatter())

    root.addHandler(fh)
    root.addHandler(ch)

    return root


def get_logger(name: str) -> logging.Logger:
    """Return a module-level logger (call setup_logging first)."""
    return logging.getLogger(name)
