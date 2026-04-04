"""
tests/test_database.py — Unit tests for database.py (SQLite persistence).

Uses a temporary database for each test via monkeypatching.
"""

from __future__ import annotations

from datetime import datetime
# from pathlib import Path

import pytest

from bot.models import OrderResponse


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_response(**overrides) -> OrderResponse:
    defaults = dict(
        order_id=1001,
        client_order_id="test-cli-id",
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        status="FILLED",
        quantity=0.01,
        executed_qty=0.01,
        avg_price=43000.0,
        price=0.0,
        stop_price=0.0,
        time_in_force="GTC",
        created_at=datetime.utcnow(),
        raw={},
    )
    defaults.update(overrides)
    return OrderResponse(**defaults)


@pytest.fixture(autouse=True)
def tmp_db(tmp_path, monkeypatch):
    """Redirect all DB operations to a temporary file."""
    db_path = tmp_path / "test_orders.db"
    monkeypatch.setattr("bot.database.DB_PATH", db_path)
    import bot.database as db_mod
    db_mod.init_db()
    yield db_path


# ── init_db ───────────────────────────────────────────────────────────────────

def test_init_db_creates_tables(tmp_path, monkeypatch):
    import sqlite3
    import bot.database as db_mod
    rows = sqlite3.connect(str(db_mod.DB_PATH)).execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = {r[0] for r in rows}
    assert "orders" in table_names
    assert "app_events" in table_names


def test_init_db_idempotent():
    """Calling init_db twice must not raise."""
    import bot.database as db_mod
    db_mod.init_db()
    db_mod.init_db()


# ── save_order / get_order_history ────────────────────────────────────────────

def test_save_order_returns_row_id():
    from bot.database import save_order
    row_id = save_order(_make_response())
    assert row_id == 1


def test_get_order_history_all():
    from bot.database import save_order, get_order_history
    save_order(_make_response(order_id=1))
    save_order(_make_response(order_id=2, symbol="ETHUSDT"))
    rows = get_order_history()
    assert len(rows) == 2


def test_get_order_history_by_symbol():
    from bot.database import save_order, get_order_history
    save_order(_make_response(order_id=1, symbol="BTCUSDT"))
    save_order(_make_response(order_id=2, symbol="ETHUSDT"))
    btc_rows = get_order_history("BTCUSDT")
    eth_rows = get_order_history("ETHUSDT")
    assert len(btc_rows) == 1
    assert btc_rows[0]["symbol"] == "BTCUSDT"
    assert len(eth_rows) == 1


def test_get_order_history_respects_limit():
    from bot.database import save_order, get_order_history
    for i in range(5):
        save_order(_make_response(order_id=i + 1))
    rows = get_order_history(limit=3)
    assert len(rows) == 3


def test_get_order_history_newest_first():
    from bot.database import save_order, get_order_history
    save_order(_make_response(order_id=10))
    save_order(_make_response(order_id=20))
    rows = get_order_history()
    assert rows[0]["order_id"] == 20


def test_get_order_history_empty():
    from bot.database import get_order_history
    assert get_order_history() == []


# ── get_order_stats ───────────────────────────────────────────────────────────

def test_get_order_stats_empty():
    from bot.database import get_order_stats
    stats = get_order_stats()
    assert stats["total"] == 0
    # SQLite SUM() returns NULL (None) for an empty set
    assert stats["filled"] in (0, None)
    assert stats["buys"] in (0, None)
    assert stats["sells"] in (0, None)


def test_get_order_stats_counts():
    from bot.database import save_order, get_order_stats
    save_order(_make_response(order_id=1, side="BUY", status="FILLED"))
    save_order(_make_response(order_id=2, side="SELL", status="NEW"))
    save_order(_make_response(order_id=3, side="BUY", status="FILLED"))
    stats = get_order_stats()
    assert stats["total"] == 3
    assert stats["filled"] == 2
    assert stats["buys"] == 2
    assert stats["sells"] == 1


def test_get_order_stats_notional():
    from bot.database import save_order, get_order_stats
    save_order(_make_response(order_id=1, executed_qty=0.01, avg_price=43000.0))
    stats = get_order_stats()
    assert stats["total_notional"] == pytest.approx(430.0)


# ── log_event ─────────────────────────────────────────────────────────────────

def test_log_event_does_not_raise():
    from bot.database import log_event
    log_event("ORDER_FAILED", "some error message")
    log_event("NETWORK_ERROR", "connection refused")
