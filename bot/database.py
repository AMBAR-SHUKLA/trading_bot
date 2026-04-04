"""
database.py — Lightweight SQLite persistence for order history.

Uses only the stdlib sqlite3 module; no ORM required.
"""

from __future__ import annotations

import json
import sqlite3
from typing import List, Optional

from bot.config import DB_PATH
from bot.models import OrderResponse


# ── Schema ────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        INTEGER NOT NULL,
    client_order_id TEXT,
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL,
    order_type      TEXT NOT NULL,
    status          TEXT,
    quantity        REAL,
    executed_qty    REAL,
    avg_price       REAL,
    price           REAL,
    stop_price      REAL,
    time_in_force   TEXT,
    created_at      TEXT,
    raw_json        TEXT
);

CREATE TABLE IF NOT EXISTS app_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT NOT NULL,
    message     TEXT,
    recorded_at TEXT DEFAULT (datetime('now'))
);
"""


# ── Connection factory ────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they do not exist."""
    with _connect() as conn:
        conn.executescript(_DDL)


# ── Write operations ──────────────────────────────────────────────────────────

def save_order(response: OrderResponse) -> int:
    """Persist an OrderResponse and return the auto-increment row id."""
    sql = """
        INSERT INTO orders (
            order_id, client_order_id, symbol, side, order_type,
            status, quantity, executed_qty, avg_price, price,
            stop_price, time_in_force, created_at, raw_json
        ) VALUES (
            :order_id, :client_order_id, :symbol, :side, :order_type,
            :status, :quantity, :executed_qty, :avg_price, :price,
            :stop_price, :time_in_force, :created_at, :raw_json
        )
    """
    row = {
        "order_id":        response.order_id,
        "client_order_id": response.client_order_id,
        "symbol":          response.symbol,
        "side":            response.side,
        "order_type":      response.order_type,
        "status":          response.status,
        "quantity":        response.quantity,
        "executed_qty":    response.executed_qty,
        "avg_price":       response.avg_price,
        "price":           response.price,
        "stop_price":      response.stop_price,
        "time_in_force":   response.time_in_force,
        "created_at":      response.created_at.isoformat(),
        "raw_json":        json.dumps(response.raw),
    }
    with _connect() as conn:
        cur = conn.execute(sql, row)
        return cur.lastrowid  # type: ignore[return-value]


def log_event(event_type: str, message: str) -> None:
    """Record a generic application event (errors, warnings, etc.)."""
    with _connect() as conn:
        conn.execute(
            "INSERT INTO app_events (event_type, message) VALUES (?, ?)",
            (event_type, message),
        )


# ── Read operations ───────────────────────────────────────────────────────────

def get_order_history(
    symbol: Optional[str] = None,
    limit: int = 20,
) -> List[dict]:
    """Return recent orders as a list of dicts, newest first."""
    if symbol:
        sql = (
            "SELECT * FROM orders WHERE symbol = ? "
            "ORDER BY id DESC LIMIT ?"
        )
        params: tuple = (symbol.upper(), limit)
    else:
        sql = "SELECT * FROM orders ORDER BY id DESC LIMIT ?"
        params = (limit,)

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def get_order_stats() -> dict:
    """Return aggregate statistics across all persisted orders."""
    sql = """
        SELECT
            COUNT(*)                        AS total,
            SUM(CASE WHEN status='FILLED' THEN 1 ELSE 0 END) AS filled,
            SUM(CASE WHEN side='BUY'  THEN 1 ELSE 0 END)     AS buys,
            SUM(CASE WHEN side='SELL' THEN 1 ELSE 0 END)     AS sells,
            SUM(executed_qty * avg_price)   AS total_notional
        FROM orders
    """
    with _connect() as conn:
        row = conn.execute(sql).fetchone()
    return dict(row) if row else {}
