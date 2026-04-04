"""
tests/test_logging_config.py — Unit tests for logging_config.py.
"""

from __future__ import annotations

import logging

import pytest

from bot.logging_config import _ConsoleFormatter, get_logger, setup_logging


# ── setup_logging ─────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def reset_root_handlers():
    """Remove any handlers added during a test so tests don't interfere."""
    root = logging.getLogger()
    original = root.handlers[:]
    yield
    root.handlers = original


def test_setup_logging_returns_root_logger(tmp_path, monkeypatch):
    monkeypatch.setattr("bot.logging_config.LOG_DIR", tmp_path)
    monkeypatch.setattr("bot.logging_config.LOG_FILE", tmp_path / "test.log")
    logging.getLogger().handlers = []
    result = setup_logging()
    assert isinstance(result, logging.Logger)
    assert result.name == "root"


def test_setup_logging_adds_handlers(tmp_path, monkeypatch):
    monkeypatch.setattr("bot.logging_config.LOG_DIR", tmp_path)
    monkeypatch.setattr("bot.logging_config.LOG_FILE", tmp_path / "test.log")
    logging.getLogger().handlers = []
    setup_logging()
    assert len(logging.getLogger().handlers) == 2


def test_setup_logging_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr("bot.logging_config.LOG_DIR", tmp_path)
    monkeypatch.setattr("bot.logging_config.LOG_FILE", tmp_path / "test.log")
    logging.getLogger().handlers = []
    setup_logging()
    handler_count = len(logging.getLogger().handlers)
    setup_logging()
    assert len(logging.getLogger().handlers) == handler_count


def test_setup_logging_verbose(tmp_path, monkeypatch):
    monkeypatch.setattr("bot.logging_config.LOG_DIR", tmp_path)
    monkeypatch.setattr("bot.logging_config.LOG_FILE", tmp_path / "test.log")
    logging.getLogger().handlers = []
    result = setup_logging(verbose=True)
    assert result is not None


def test_get_logger_returns_named_logger():
    log = get_logger("bot.test_module")
    assert isinstance(log, logging.Logger)
    assert log.name == "bot.test_module"


# ── _ConsoleFormatter ─────────────────────────────────────────────────────────

def _make_record(level: int, msg: str = "test message") -> logging.LogRecord:
    return logging.LogRecord(
        name="test", level=level, pathname="", lineno=0,
        msg=msg, args=(), exc_info=None,
    )


class TestConsoleFormatter:
    def test_formats_info(self):
        result = _ConsoleFormatter().format(_make_record(logging.INFO))
        assert "test message" in result

    def test_formats_debug(self):
        result = _ConsoleFormatter().format(_make_record(logging.DEBUG))
        assert "test message" in result

    def test_formats_warning(self):
        result = _ConsoleFormatter().format(_make_record(logging.WARNING))
        assert "test message" in result

    def test_formats_error(self):
        result = _ConsoleFormatter().format(_make_record(logging.ERROR))
        assert "test message" in result

    def test_formats_critical(self):
        result = _ConsoleFormatter().format(_make_record(logging.CRITICAL))
        assert "test message" in result

    def test_output_contains_ansi_colour(self):
        result = _ConsoleFormatter().format(_make_record(logging.INFO))
        assert "\x1b[" in result

    def test_unknown_level_uses_reset(self):
        result = _ConsoleFormatter().format(_make_record(99))
        assert "test message" in result
