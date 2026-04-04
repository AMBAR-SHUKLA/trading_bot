"""
tests/test_cli.py — Unit tests for the Typer CLI (all commands via CliRunner).

No real API calls or DB writes are made; all external deps are mocked.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from bot.cli import app
from bot.client import BinanceAPIError
from bot.models import OrderBookSnapshot, OrderResponse

runner = CliRunner()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_response(**overrides) -> OrderResponse:
    defaults = dict(
        order_id=42, client_order_id="cli-test", symbol="BTCUSDT",
        side="BUY", order_type="MARKET", status="FILLED",
        quantity=0.01, executed_qty=0.01, avg_price=43000.0,
        price=0.0, stop_price=0.0, time_in_force="GTC",
        created_at=datetime.utcnow(), raw={},
    )
    defaults.update(overrides)
    return OrderResponse(**defaults)


def _make_snap() -> OrderBookSnapshot:
    return OrderBookSnapshot(
        symbol="BTCUSDT", best_bid=43200.0, best_bid_qty=1.5,
        best_ask=43210.0, best_ask_qty=0.8, mid_price=43205.0, spread=10.0,
    )


def _make_manager() -> MagicMock:
    m = MagicMock()
    m.execute_order.return_value = _make_response()
    m.get_order_book.return_value = _make_snap()
    m.get_current_price.return_value = 43000.0
    m.get_open_orders.return_value = []
    m.get_account_summary.return_value = {
        "totalWalletBalance": "1000",
        "availableBalance": "900",
        "totalUnrealizedProfit": "50",
        "positions": [],
    }
    m._client.ping.return_value = True
    return m


@pytest.fixture(autouse=True)
def _suppress_side_effects(monkeypatch):
    """Prevent logging setup and DB init from running during CLI tests."""
    monkeypatch.setattr("bot.cli.init_db", lambda: None)
    monkeypatch.setattr("bot.logging_config.LOG_DIR", __import__("pathlib").Path("/tmp"))
    monkeypatch.setattr(
        "bot.logging_config.LOG_FILE",
        __import__("pathlib").Path("/tmp/test_bot.log"),
    )


# ══════════════════════════════════════════════════════════════════════════════
# place-order
# ══════════════════════════════════════════════════════════════════════════════

class TestPlaceOrder:
    def test_market_order_success(self):
        with patch("bot.cli.validate_credentials", return_value=True), \
             patch("bot.cli.build_manager", return_value=_make_manager()):
            result = runner.invoke(app, [
                "place-order", "--symbol", "BTCUSDT",
                "--side", "BUY", "--type", "MARKET", "--qty", "0.01",
            ])
        assert result.exit_code == 0

    def test_limit_order_success(self):
        mgr = _make_manager()
        mgr.execute_order.return_value = _make_response(
            order_type="LIMIT", price=43000.0, status="NEW"
        )
        with patch("bot.cli.validate_credentials", return_value=True), \
             patch("bot.cli.build_manager", return_value=mgr):
            result = runner.invoke(app, [
                "place-order", "--symbol", "ETHUSDT", "--side", "SELL",
                "--type", "LIMIT", "--qty", "0.1", "--price", "2000",
            ])
        assert result.exit_code == 0

    def test_stop_limit_order_success(self):
        mgr = _make_manager()
        mgr.execute_order.return_value = _make_response(
            order_type="STOP_LIMIT", price=29000.0, stop_price=29500.0,
        )
        with patch("bot.cli.validate_credentials", return_value=True), \
             patch("bot.cli.build_manager", return_value=mgr):
            result = runner.invoke(app, [
                "place-order", "--symbol", "BTCUSDT", "--side", "SELL",
                "--type", "STOP_LIMIT", "--qty", "0.01",
                "--price", "29000", "--stop-price", "29500",
            ])
        assert result.exit_code == 0

    def test_missing_credentials_exits_1(self):
        with patch("bot.cli.validate_credentials", return_value=False):
            result = runner.invoke(app, [
                "place-order", "--symbol", "BTCUSDT",
                "--side", "BUY", "--type", "MARKET", "--qty", "0.01",
            ])
        assert result.exit_code == 1

    def test_invalid_symbol_exits_1(self):
        with patch("bot.cli.validate_credentials", return_value=True):
            result = runner.invoke(app, [
                "place-order", "--symbol", "123",
                "--side", "BUY", "--type", "MARKET", "--qty", "0.01",
            ])
        assert result.exit_code == 1

    def test_api_error_exits_1(self):
        mgr = _make_manager()
        mgr.execute_order.side_effect = BinanceAPIError(-2019, "Margin insufficient", 400)
        with patch("bot.cli.validate_credentials", return_value=True), \
             patch("bot.cli.build_manager", return_value=mgr):
            result = runner.invoke(app, [
                "place-order", "--symbol", "BTCUSDT",
                "--side", "BUY", "--type", "MARKET", "--qty", "0.01",
            ])
        assert result.exit_code == 1

    def test_timeout_exits_1(self):
        mgr = _make_manager()
        mgr.execute_order.side_effect = TimeoutError("timed out")
        with patch("bot.cli.validate_credentials", return_value=True), \
             patch("bot.cli.build_manager", return_value=mgr):
            result = runner.invoke(app, [
                "place-order", "--symbol", "BTCUSDT",
                "--side", "BUY", "--type", "MARKET", "--qty", "0.01",
            ])
        assert result.exit_code == 1

    def test_connection_error_exits_1(self):
        mgr = _make_manager()
        mgr.execute_order.side_effect = ConnectionError("no network")
        with patch("bot.cli.validate_credentials", return_value=True), \
             patch("bot.cli.build_manager", return_value=mgr):
            result = runner.invoke(app, [
                "place-order", "--symbol", "BTCUSDT",
                "--side", "BUY", "--type", "MARKET", "--qty", "0.01",
            ])
        assert result.exit_code == 1

    def test_credentials_error_exits_1(self):
        from bot.client import CredentialsError
        mgr = _make_manager()
        mgr.execute_order.side_effect = CredentialsError("bad creds")
        with patch("bot.cli.validate_credentials", return_value=True), \
             patch("bot.cli.build_manager", return_value=mgr):
            result = runner.invoke(app, [
                "place-order", "--symbol", "BTCUSDT",
                "--side", "BUY", "--type", "MARKET", "--qty", "0.01",
            ])
        assert result.exit_code == 1


# ══════════════════════════════════════════════════════════════════════════════
# order-book
# ══════════════════════════════════════════════════════════════════════════════

class TestOrderBook:
    def test_success(self):
        with patch("bot.cli.validate_credentials", return_value=True), \
             patch("bot.cli.build_manager", return_value=_make_manager()):
            result = runner.invoke(app, ["order-book", "--symbol", "BTCUSDT"])
        assert result.exit_code == 0

    def test_invalid_symbol_exits_1(self):
        with patch("bot.cli.validate_credentials", return_value=True):
            result = runner.invoke(app, ["order-book", "--symbol", "1"])
        assert result.exit_code == 1

    def test_missing_credentials_exits_1(self):
        with patch("bot.cli.validate_credentials", return_value=False):
            result = runner.invoke(app, ["order-book"])
        assert result.exit_code == 1


# ══════════════════════════════════════════════════════════════════════════════
# open-orders
# ══════════════════════════════════════════════════════════════════════════════

class TestOpenOrders:
    def test_no_orders(self):
        with patch("bot.cli.validate_credentials", return_value=True), \
             patch("bot.cli.build_manager", return_value=_make_manager()):
            result = runner.invoke(app, ["open-orders"])
        assert result.exit_code == 0

    def test_with_orders_renders_table(self):
        mgr = _make_manager()
        mgr.get_open_orders.return_value = [{
            "orderId": 1, "symbol": "BTCUSDT", "side": "BUY",
            "type": "LIMIT", "origQty": "0.01", "price": "43000", "status": "NEW",
        }]
        with patch("bot.cli.validate_credentials", return_value=True), \
             patch("bot.cli.build_manager", return_value=mgr):
            result = runner.invoke(app, ["open-orders", "--symbol", "BTCUSDT"])
        assert result.exit_code == 0

    def test_missing_credentials_exits_1(self):
        with patch("bot.cli.validate_credentials", return_value=False):
            result = runner.invoke(app, ["open-orders"])
        assert result.exit_code == 1


# ══════════════════════════════════════════════════════════════════════════════
# history
# ══════════════════════════════════════════════════════════════════════════════

_EMPTY_STATS = {
    "total": 0, "filled": 0, "buys": 0, "sells": 0, "total_notional": None,
}

_SAMPLE_ROW = {
    "order_id": 1, "symbol": "BTCUSDT", "side": "BUY",
    "order_type": "MARKET", "status": "FILLED",
    "quantity": 0.01, "executed_qty": 0.01,
    "avg_price": 43000.0, "created_at": "2026-04-05T10:15:01",
}

_SAMPLE_STATS = {
    "total": 1, "filled": 1, "buys": 1, "sells": 0, "total_notional": 430.0,
}


class TestHistory:
    def test_empty_history_message(self):
        with patch("bot.cli.get_order_history", return_value=[]), \
             patch("bot.cli.get_order_stats", return_value=_EMPTY_STATS):
            result = runner.invoke(app, ["history"])
        assert result.exit_code == 0
        assert "No orders" in result.stdout

    def test_with_rows_renders_table(self):
        with patch("bot.cli.get_order_history", return_value=[_SAMPLE_ROW]), \
             patch("bot.cli.get_order_stats", return_value=_SAMPLE_STATS):
            result = runner.invoke(app, ["history", "--limit", "5"])
        assert result.exit_code == 0

    def test_with_symbol_filter(self):
        with patch("bot.cli.get_order_history", return_value=[_SAMPLE_ROW]), \
             patch("bot.cli.get_order_stats", return_value=_SAMPLE_STATS):
            result = runner.invoke(app, ["history", "--symbol", "BTCUSDT"])
        assert result.exit_code == 0

    def test_sell_row_renders(self):
        sell_row = {**_SAMPLE_ROW, "side": "SELL"}
        with patch("bot.cli.get_order_history", return_value=[sell_row]), \
             patch("bot.cli.get_order_stats", return_value=_SAMPLE_STATS):
            result = runner.invoke(app, ["history"])
        assert result.exit_code == 0


# ══════════════════════════════════════════════════════════════════════════════
# account
# ══════════════════════════════════════════════════════════════════════════════

class TestAccount:
    def test_no_positions(self):
        with patch("bot.cli.validate_credentials", return_value=True), \
             patch("bot.cli.build_manager", return_value=_make_manager()):
            result = runner.invoke(app, ["account"])
        assert result.exit_code == 0

    def test_with_open_positions(self):
        mgr = _make_manager()
        mgr.get_account_summary.return_value = {
            "totalWalletBalance": "1000",
            "availableBalance": "900",
            "totalUnrealizedProfit": "50",
            "positions": [{
                "symbol": "BTCUSDT", "positionAmt": "0.01",
                "entryPrice": "43000", "markPrice": "44000",
                "unrealizedProfit": "10",
            }],
        }
        with patch("bot.cli.validate_credentials", return_value=True), \
             patch("bot.cli.build_manager", return_value=mgr):
            result = runner.invoke(app, ["account"])
        assert result.exit_code == 0

    def test_with_negative_pnl_position(self):
        mgr = _make_manager()
        mgr.get_account_summary.return_value = {
            "totalWalletBalance": "900",
            "availableBalance": "850",
            "totalUnrealizedProfit": "-50",
            "positions": [{
                "symbol": "ETHUSDT", "positionAmt": "1.0",
                "entryPrice": "2100", "markPrice": "2000",
                "unrealizedProfit": "-100",
            }],
        }
        with patch("bot.cli.validate_credentials", return_value=True), \
             patch("bot.cli.build_manager", return_value=mgr):
            result = runner.invoke(app, ["account"])
        assert result.exit_code == 0

    def test_missing_credentials_exits_1(self):
        with patch("bot.cli.validate_credentials", return_value=False):
            result = runner.invoke(app, ["account"])
        assert result.exit_code == 1

    def test_api_error_exits_1(self):
        mgr = _make_manager()
        mgr.get_account_summary.side_effect = BinanceAPIError(-1001, "server error", 500)
        with patch("bot.cli.validate_credentials", return_value=True), \
             patch("bot.cli.build_manager", return_value=mgr):
            result = runner.invoke(app, ["account"])
        assert result.exit_code == 1


# ══════════════════════════════════════════════════════════════════════════════
# ping
# ══════════════════════════════════════════════════════════════════════════════

class TestPing:
    def test_reachable(self):
        with patch("bot.cli.validate_credentials", return_value=True), \
             patch("bot.cli.build_manager", return_value=_make_manager()):
            result = runner.invoke(app, ["ping"])
        assert result.exit_code == 0
        assert "reachable" in result.stdout.lower()

    def test_unreachable_exits_1(self):
        mgr = _make_manager()
        mgr._client.ping.return_value = False
        with patch("bot.cli.validate_credentials", return_value=True), \
             patch("bot.cli.build_manager", return_value=mgr):
            result = runner.invoke(app, ["ping"])
        assert result.exit_code == 1

    def test_missing_credentials_exits_1(self):
        with patch("bot.cli.validate_credentials", return_value=False):
            result = runner.invoke(app, ["ping"])
        assert result.exit_code == 1

    def test_credentials_error_exits_1(self):
        from bot.client import CredentialsError
        with patch("bot.cli.validate_credentials", return_value=True), \
             patch("bot.cli.build_manager", side_effect=CredentialsError("no creds")):
            result = runner.invoke(app, ["ping"])
        assert result.exit_code == 1


# ══════════════════════════════════════════════════════════════════════════════
# Large-order confirmation (_confirm_large_order path)
# ══════════════════════════════════════════════════════════════════════════════

class TestLargeOrderConfirmation:
    def test_large_order_confirmed_proceeds(self):
        with patch("bot.cli.validate_credentials", return_value=True), \
             patch("bot.cli.build_manager", return_value=_make_manager()), \
             patch("bot.cli.CONFIRM_LARGE_ORDERS", True), \
             patch("bot.cli.is_large_order", return_value=True):
            result = runner.invoke(app, [
                "place-order", "--symbol", "BTCUSDT",
                "--side", "BUY", "--type", "MARKET", "--qty", "50.0",
            ], input="y\n")
        assert result.exit_code == 0

    def test_large_order_declined_exits(self):
        with patch("bot.cli.validate_credentials", return_value=True), \
             patch("bot.cli.build_manager", return_value=_make_manager()), \
             patch("bot.cli.CONFIRM_LARGE_ORDERS", True), \
             patch("bot.cli.is_large_order", return_value=True):
            result = runner.invoke(app, [
                "place-order", "--symbol", "BTCUSDT",
                "--side", "BUY", "--type", "MARKET", "--qty", "50.0",
            ], input="n\n")
        assert result.exit_code == 0  # user cancellation is a clean exit
