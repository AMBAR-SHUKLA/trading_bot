"""
tests/test_orders.py — Unit tests for the OrderManager (mocked BinanceClient).
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from bot.client import BinanceAPIError
from bot.models import OrderBookSnapshot, OrderRequest, OrderResponse
from bot.orders import OrderManager


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_response(**overrides) -> OrderResponse:
    defaults = dict(
        order_id=1, client_order_id="x", symbol="BTCUSDT",
        side="BUY", order_type="MARKET", status="FILLED",
        quantity=0.01, executed_qty=0.01, avg_price=43000.0,
        price=0.0, stop_price=0.0, time_in_force="GTC",
        created_at=datetime.utcnow(), raw={},
    )
    defaults.update(overrides)
    return OrderResponse(**defaults)


@pytest.fixture()
def mock_client():
    return MagicMock()


@pytest.fixture()
def manager(mock_client):
    with patch("bot.orders.init_db"):
        return OrderManager(mock_client)


# ── execute_order — MARKET ────────────────────────────────────────────────────

class TestExecuteMarketOrder:
    def test_success(self, manager, mock_client):
        mock_client.place_market_order.return_value = _make_response()
        req = OrderRequest("BTCUSDT", "BUY", "MARKET", 0.01)
        with patch("bot.orders.save_order", return_value=1):
            resp = manager.execute_order(req)
        assert resp.order_id == 1
        mock_client.place_market_order.assert_called_once_with(
            symbol="BTCUSDT", side="BUY", quantity=0.01
        )

    def test_api_error_raises(self, manager, mock_client):
        mock_client.place_market_order.side_effect = BinanceAPIError(-2019, "Margin error")
        req = OrderRequest("BTCUSDT", "BUY", "MARKET", 0.01)
        with patch("bot.orders.log_event"):
            with pytest.raises(BinanceAPIError):
                manager.execute_order(req)

    def test_timeout_raises(self, manager, mock_client):
        mock_client.place_market_order.side_effect = TimeoutError("timed out")
        req = OrderRequest("BTCUSDT", "BUY", "MARKET", 0.01)
        with patch("bot.orders.log_event"):
            with pytest.raises(TimeoutError):
                manager.execute_order(req)

    def test_connection_error_raises(self, manager, mock_client):
        mock_client.place_market_order.side_effect = ConnectionError("no network")
        req = OrderRequest("BTCUSDT", "BUY", "MARKET", 0.01)
        with patch("bot.orders.log_event"):
            with pytest.raises(ConnectionError):
                manager.execute_order(req)

    def test_db_failure_is_non_fatal(self, manager, mock_client):
        mock_client.place_market_order.return_value = _make_response()
        req = OrderRequest("BTCUSDT", "BUY", "MARKET", 0.01)
        with patch("bot.orders.save_order", side_effect=Exception("DB error")):
            resp = manager.execute_order(req)
        assert resp.order_id == 1


# ── execute_order — LIMIT ────────────────────────────────────────────────────

class TestExecuteLimitOrder:
    def test_success(self, manager, mock_client):
        mock_client.place_limit_order.return_value = _make_response(
            order_type="LIMIT", price=43000.0, status="NEW"
        )
        req = OrderRequest("BTCUSDT", "BUY", "LIMIT", 0.01, price=43000.0)
        with patch("bot.orders.save_order", return_value=1):
            resp = manager.execute_order(req)
        assert resp.order_type == "LIMIT"
        mock_client.place_limit_order.assert_called_once_with(
            symbol="BTCUSDT", side="BUY", quantity=0.01,
            price=43000.0, time_in_force="GTC",
        )


# ── execute_order — STOP_LIMIT ────────────────────────────────────────────────

class TestExecuteStopLimitOrder:
    def test_success(self, manager, mock_client):
        mock_client.place_stop_limit_order.return_value = _make_response(
            order_type="STOP_LIMIT", price=29000.0, stop_price=29500.0, status="NEW"
        )
        req = OrderRequest(
            "BTCUSDT", "SELL", "STOP_LIMIT", 0.01,
            price=29000.0, stop_price=29500.0,
        )
        with patch("bot.orders.save_order", return_value=1):
            resp = manager.execute_order(req)
        assert resp.stop_price == pytest.approx(29500.0)
        mock_client.place_stop_limit_order.assert_called_once_with(
            symbol="BTCUSDT", side="SELL", quantity=0.01,
            price=29000.0, stop_price=29500.0, time_in_force="GTC",
        )


# ── execute_order — unsupported type ─────────────────────────────────────────

def test_unsupported_order_type_raises(manager):
    req = OrderRequest("BTCUSDT", "BUY", "TWAP", 0.01)
    with pytest.raises(ValueError, match="Unsupported order type"):
        manager.execute_order(req)


# ── Market data helpers ───────────────────────────────────────────────────────

def test_get_order_book(manager, mock_client):
    snap = MagicMock(spec=OrderBookSnapshot)
    mock_client.get_order_book.return_value = snap
    result = manager.get_order_book("BTCUSDT")
    assert result is snap
    mock_client.get_order_book.assert_called_once_with("BTCUSDT")


def test_get_current_price(manager, mock_client):
    mock_client.get_price.return_value = 43000.0
    assert manager.get_current_price("BTCUSDT") == pytest.approx(43000.0)


def test_get_open_orders_no_symbol(manager, mock_client):
    mock_client.get_open_orders.return_value = []
    assert manager.get_open_orders() == []
    mock_client.get_open_orders.assert_called_once_with(None)


def test_get_open_orders_with_symbol(manager, mock_client):
    mock_client.get_open_orders.return_value = []
    manager.get_open_orders("BTCUSDT")
    mock_client.get_open_orders.assert_called_once_with("BTCUSDT")


def test_cancel_order(manager, mock_client):
    mock_client.cancel_order.return_value = {"status": "CANCELED"}
    with patch("bot.orders.log_event"):
        result = manager.cancel_order("BTCUSDT", 99)
    assert result["status"] == "CANCELED"


def test_get_account_summary(manager, mock_client):
    mock_client.get_account.return_value = {"totalWalletBalance": "500"}
    result = manager.get_account_summary()
    assert result["totalWalletBalance"] == "500"


# ── build_manager ─────────────────────────────────────────────────────────────

def test_build_manager_raises_without_credentials():
    """build_manager should propagate CredentialsError when keys are missing."""
    from bot.client import CredentialsError
    with patch("bot.orders.BinanceClient", side_effect=CredentialsError("no creds")):
        with pytest.raises(CredentialsError):
            from bot.orders import build_manager
            build_manager()
