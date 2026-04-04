"""
tests/test_models.py — Unit tests for the data-class models.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from bot.models import OrderBookSnapshot, OrderRequest, OrderResponse


# ── OrderRequest ──────────────────────────────────────────────────────────────

class TestOrderRequest:
    def test_summary_market(self):
        req = OrderRequest("BTCUSDT", "BUY", "MARKET", 0.01)
        s = req.summary()
        assert "BTCUSDT" in s
        assert "MARKET" in s
        assert "0.01" in s

    def test_summary_limit_includes_price(self):
        req = OrderRequest("ETHUSDT", "SELL", "LIMIT", 0.1, price=2000.0)
        s = req.summary()
        assert "2000.0" in s

    def test_summary_stop_limit_includes_stop_price(self):
        req = OrderRequest(
            "BTCUSDT", "SELL", "STOP_LIMIT", 0.01,
            price=29000.0, stop_price=29500.0,
        )
        s = req.summary()
        assert "29000.0" in s
        assert "29500.0" in s


# ── OrderResponse ─────────────────────────────────────────────────────────────

def _market_resp(**kw) -> OrderResponse:
    defaults = dict(
        order_id=1, client_order_id="abc", symbol="BTCUSDT",
        side="BUY", order_type="MARKET", status="FILLED",
        quantity=0.01, executed_qty=0.01, avg_price=43000.0,
        price=0.0, stop_price=0.0, time_in_force="GTC",
        created_at=datetime.utcnow(), raw={},
    )
    defaults.update(kw)
    return OrderResponse(**defaults)


class TestOrderResponse:
    def test_from_binance_full(self):
        data = {
            "orderId": 99, "clientOrderId": "client-x",
            "symbol": "ETHUSDT", "side": "SELL", "type": "LIMIT",
            "status": "NEW", "origQty": "0.5", "executedQty": "0",
            "avgPrice": "0", "price": "2100.0", "stopPrice": "0",
            "timeInForce": "GTC",
        }
        resp = OrderResponse.from_binance(data)
        assert resp.order_id == 99
        assert resp.symbol == "ETHUSDT"
        assert resp.price == pytest.approx(2100.0)
        assert resp.executed_qty == pytest.approx(0.0)

    def test_from_binance_missing_fields_use_defaults(self):
        resp = OrderResponse.from_binance({})
        assert resp.order_id == 0
        assert resp.symbol == ""
        assert resp.time_in_force == "GTC"

    def test_summary_contains_key_fields(self):
        resp = _market_resp()
        s = resp.summary()
        assert "BTCUSDT" in s
        assert "FILLED" in s
        assert "43000" in s

    def test_summary_shows_limit_price_when_set(self):
        resp = _market_resp(order_type="LIMIT", price=43000.0)
        s = resp.summary()
        assert "Limit Price" in s

    def test_summary_shows_stop_price_when_set(self):
        resp = _market_resp(order_type="STOP_LIMIT", stop_price=29500.0)
        s = resp.summary()
        assert "Stop Price" in s

    def test_to_dict_excludes_raw(self):
        resp = _market_resp(raw={"extra": "data"})
        d = resp.to_dict()
        assert "raw" not in d
        assert d["order_id"] == 1
        assert isinstance(d["created_at"], str)

    def test_to_json_is_valid(self):
        import json
        resp = _market_resp()
        j = resp.to_json()
        parsed = json.loads(j)
        assert parsed["order_id"] == 1
        assert parsed["symbol"] == "BTCUSDT"


# ── OrderBookSnapshot ─────────────────────────────────────────────────────────

class TestOrderBookSnapshot:
    def test_from_binance_full(self):
        data = {
            "bids": [["43200.00", "1.5"], ["43190.00", "2.0"]],
            "asks": [["43210.00", "0.8"], ["43220.00", "1.2"]],
        }
        snap = OrderBookSnapshot.from_binance("BTCUSDT", data)
        assert snap.best_bid == pytest.approx(43200.0)
        assert snap.best_ask == pytest.approx(43210.0)
        assert snap.mid_price == pytest.approx(43205.0)
        assert snap.spread == pytest.approx(10.0)

    def test_from_binance_empty_book(self):
        snap = OrderBookSnapshot.from_binance("BTCUSDT", {"bids": [], "asks": []})
        assert snap.best_bid == 0.0
        assert snap.best_ask == 0.0
        assert snap.mid_price == 0.0
        assert snap.spread == 0.0

    def test_display_contains_prices(self):
        snap = OrderBookSnapshot(
            symbol="BTCUSDT",
            best_bid=43200.0, best_bid_qty=1.5,
            best_ask=43210.0, best_ask_qty=0.8,
            mid_price=43205.0, spread=10.0,
        )
        d = snap.display()
        assert "43200" in d
        assert "43210" in d
        assert "43205" in d
        assert "10.0" in d
