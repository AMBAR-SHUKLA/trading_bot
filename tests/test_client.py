"""
tests/test_client.py — Unit tests for the BinanceClient (mocked HTTP).

No real network calls are made.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from bot.client import BinanceClient, BinanceAPIError, CredentialsError
from bot.models import OrderResponse, OrderBookSnapshot


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def client():
    """Return a BinanceClient with fake credentials."""
    return BinanceClient(
        api_key="test_api_key_0123456789abcdef",
        api_secret="test_secret_key_0123456789abcdef",
        base_url="https://testnet.binancefuture.com",
    )


def _mock_response(data: dict, status: int = 200) -> MagicMock:
    """Build a mock requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status
    resp.ok = status < 400
    resp.json.return_value = data
    resp.text = json.dumps(data)
    resp.headers = {}
    return resp


_MARKET_ORDER_FIXTURE = {
    "orderId": 123456,
    "clientOrderId": "abc123",
    "symbol": "BTCUSDT",
    "side": "BUY",
    "type": "MARKET",
    "status": "FILLED",
    "origQty": "0.01",
    "executedQty": "0.01",
    "avgPrice": "43210.50",
    "price": "0",
    "stopPrice": "0",
    "timeInForce": "GTC",
}

_LIMIT_ORDER_FIXTURE = {
    **_MARKET_ORDER_FIXTURE,
    "orderId": 789012,
    "type": "LIMIT",
    "status": "NEW",
    "price": "40000.00",
    "executedQty": "0",
    "avgPrice": "0",
}

_STOP_LIMIT_FIXTURE = {
    **_MARKET_ORDER_FIXTURE,
    "orderId": 555555,
    "type": "STOP",
    "status": "NEW",
    "price": "29000.00",
    "stopPrice": "29500.00",
}


# ══════════════════════════════════════════════════════════════════════════════
# Credentials guard
# ══════════════════════════════════════════════════════════════════════════════

def test_missing_credentials_raises():
    with pytest.raises(CredentialsError):
        BinanceClient(api_key="", api_secret="")


# ══════════════════════════════════════════════════════════════════════════════
# Market order
# ══════════════════════════════════════════════════════════════════════════════

class TestMarketOrder:
    def test_returns_order_response(self, client):
        with patch.object(
            client._session, "request",
            return_value=_mock_response(_MARKET_ORDER_FIXTURE),
        ):
            resp = client.place_market_order("BTCUSDT", "BUY", 0.01)

        assert isinstance(resp, OrderResponse)
        assert resp.order_id == 123456
        assert resp.status == "FILLED"
        assert resp.executed_qty == pytest.approx(0.01)
        assert resp.avg_price == pytest.approx(43210.50)

    def test_api_error_raises(self, client):
        error_body = {"code": -2019, "msg": "Margin is insufficient."}
        with patch.object(client._session, "request", return_value=_mock_response(error_body, 400)):
            with pytest.raises(BinanceAPIError) as exc_info:
                client.place_market_order("BTCUSDT", "BUY", 0.01)
        assert exc_info.value.code == -2019


# ══════════════════════════════════════════════════════════════════════════════
# Limit order
# ══════════════════════════════════════════════════════════════════════════════

class TestLimitOrder:
    def test_returns_order_response(self, client):
        with patch.object(
            client._session, "request",
            return_value=_mock_response(_LIMIT_ORDER_FIXTURE),
        ):
            resp = client.place_limit_order("BTCUSDT", "BUY", 0.01, 40000.0)

        assert resp.order_id == 789012
        assert resp.status == "NEW"
        assert resp.price == pytest.approx(40000.0)

    def test_timeout_raises(self, client):
        with patch.object(
            client._session, "request",
            side_effect=requests.exceptions.Timeout,
        ):
            with pytest.raises(TimeoutError):
                client.place_limit_order("BTCUSDT", "BUY", 0.01, 40000.0)

    def test_connection_error_raises(self, client):
        with patch.object(
            client._session, "request",
            side_effect=requests.exceptions.ConnectionError,
        ):
            with pytest.raises(ConnectionError):
                client.place_limit_order("BTCUSDT", "BUY", 0.01, 40000.0)


# ══════════════════════════════════════════════════════════════════════════════
# Stop-Limit order
# ══════════════════════════════════════════════════════════════════════════════

class TestStopLimitOrder:
    def test_returns_order_response(self, client):
        with patch.object(
            client._session, "request",
            return_value=_mock_response(_STOP_LIMIT_FIXTURE),
        ):
            resp = client.place_stop_limit_order(
                "BTCUSDT", "SELL", 0.01, price=29000.0, stop_price=29500.0
            )
        assert resp.order_id == 555555
        assert resp.stop_price == pytest.approx(29500.0)


# ══════════════════════════════════════════════════════════════════════════════
# Order book
# ══════════════════════════════════════════════════════════════════════════════

class TestOrderBook:
    def test_returns_snapshot(self, client):
        depth_data = {
            "bids": [["43200.00", "1.5"], ["43190.00", "2.0"]],
            "asks": [["43210.00", "0.8"], ["43220.00", "1.2"]],
        }
        with patch.object(client._session, "request", return_value=_mock_response(depth_data)):
            snap = client.get_order_book("BTCUSDT", limit=5)

        assert isinstance(snap, OrderBookSnapshot)
        assert snap.best_bid == pytest.approx(43200.0)
        assert snap.best_ask == pytest.approx(43210.0)
        assert snap.spread == pytest.approx(10.0)
        assert snap.mid_price == pytest.approx(43205.0)


# ══════════════════════════════════════════════════════════════════════════════
# Ping
# ══════════════════════════════════════════════════════════════════════════════

def test_ping_true(client):
    with patch.object(client._session, "request", return_value=_mock_response({})):
        assert client.ping() is True


def test_ping_false_on_error(client):
    with patch.object(client._session, "request", side_effect=Exception("fail")):
        assert client.ping() is False


# ══════════════════════════════════════════════════════════════════════════════
# Additional coverage — previously uncovered client paths
# ══════════════════════════════════════════════════════════════════════════════

def test_get_order(client):
    with patch.object(
        client._session, "request",
        return_value=_mock_response({"orderId": 9, "symbol": "BTCUSDT"}),
    ):
        result = client.get_order("BTCUSDT", 9)
    assert result["orderId"] == 9


def test_cancel_order(client):
    with patch.object(
        client._session, "request",
        return_value=_mock_response({"status": "CANCELED"}),
    ):
        result = client.cancel_order("BTCUSDT", 9)
    assert result["status"] == "CANCELED"


def test_get_open_orders_all_symbols(client):
    with patch.object(
        client._session, "request", return_value=_mock_response([]),
    ):
        result = client.get_open_orders()
    assert result == []


def test_get_open_orders_filtered(client):
    with patch.object(
        client._session, "request", return_value=_mock_response([]),
    ):
        result = client.get_open_orders("BTCUSDT")
    assert result == []


def test_get_account(client):
    with patch.object(
        client._session, "request",
        return_value=_mock_response({"totalWalletBalance": "1000"}),
    ):
        result = client.get_account()
    assert result["totalWalletBalance"] == "1000"


def test_get_price(client):
    with patch.object(
        client._session, "request",
        return_value=_mock_response({"price": "43000.0"}),
    ):
        result = client.get_price("BTCUSDT")
    assert result == pytest.approx(43000.0)


def test_rate_limit_triggers_retry(client):
    import time as _time
    limit_resp = MagicMock(spec=requests.Response)
    limit_resp.status_code = 429
    limit_resp.ok = False
    limit_resp.headers = {"Retry-After": "0"}

    ok_resp = _mock_response({"price": "43000.0"})

    with patch.object(
        client._session, "request", side_effect=[limit_resp, ok_resp]
    ), patch.object(_time, "sleep"):
        result = client.get_price("BTCUSDT")
    assert result == pytest.approx(43000.0)


def test_non_json_response_raises(client):
    from bot.client import BinanceAPIError as _BinanceAPIError
    bad_resp = MagicMock(spec=requests.Response)
    bad_resp.status_code = 200
    bad_resp.ok = True
    bad_resp.json.side_effect = ValueError("not json")
    bad_resp.text = "not json at all"
    bad_resp.headers = {}

    with patch.object(client._session, "request", return_value=bad_resp):
        with pytest.raises(_BinanceAPIError) as exc_info:
            client.get_price("BTCUSDT")
    assert exc_info.value.code == -1
