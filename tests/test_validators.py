"""
tests/test_validators.py — Unit tests for the validators module.

Run with:  pytest tests/ -v
"""

import pytest

from bot.validators import (
    validate_symbol,
    validate_side,
    validate_order_type,
    validate_quantity,
    validate_price,
    validate_order_request,
    is_large_order,
)
from bot.models import OrderRequest


# ══════════════════════════════════════════════════════════════════════════════
# Symbol validation
# ══════════════════════════════════════════════════════════════════════════════

class TestValidateSymbol:
    def test_valid_symbols(self):
        assert validate_symbol("BTCUSDT") == "BTCUSDT"
        assert validate_symbol("ETHUSDT") == "ETHUSDT"
        assert validate_symbol("btcusdt") == "BTCUSDT"   # normalised to upper

    def test_strips_whitespace(self):
        assert validate_symbol("  BTCUSDT  ") == "BTCUSDT"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            validate_symbol("")

    def test_digits_raises(self):
        with pytest.raises(ValueError):
            validate_symbol("BTC1USDT")

    def test_too_short_raises(self):
        with pytest.raises(ValueError):
            validate_symbol("BT")

    def test_too_long_raises(self):
        with pytest.raises(ValueError):
            validate_symbol("A" * 21)


# ══════════════════════════════════════════════════════════════════════════════
# Side validation
# ══════════════════════════════════════════════════════════════════════════════

class TestValidateSide:
    def test_buy(self):
        assert validate_side("BUY") == "BUY"

    def test_sell_lowercase(self):
        assert validate_side("sell") == "SELL"

    def test_invalid(self):
        with pytest.raises(ValueError, match="side"):
            validate_side("LONG")


# ══════════════════════════════════════════════════════════════════════════════
# Order type validation
# ══════════════════════════════════════════════════════════════════════════════

class TestValidateOrderType:
    def test_market(self):
        assert validate_order_type("MARKET") == "MARKET"

    def test_limit(self):
        assert validate_order_type("limit") == "LIMIT"

    def test_stop_limit_with_dash(self):
        assert validate_order_type("STOP-LIMIT") == "STOP_LIMIT"

    def test_invalid(self):
        with pytest.raises(ValueError, match="order type"):
            validate_order_type("TWAP")


# ══════════════════════════════════════════════════════════════════════════════
# Quantity validation
# ══════════════════════════════════════════════════════════════════════════════

class TestValidateQuantity:
    def test_valid(self):
        assert validate_quantity(0.01) == pytest.approx(0.01)
        assert validate_quantity("0.5") == pytest.approx(0.5)

    def test_zero_raises(self):
        with pytest.raises(ValueError, match="greater than 0"):
            validate_quantity(0)

    def test_negative_raises(self):
        with pytest.raises(ValueError):
            validate_quantity(-1)

    def test_non_numeric_raises(self):
        with pytest.raises(ValueError, match="not a valid number"):
            validate_quantity("abc")

    def test_exceeds_max_raises(self):
        with pytest.raises(ValueError, match="maximum"):
            validate_quantity(99999.0)


# ══════════════════════════════════════════════════════════════════════════════
# Price validation
# ══════════════════════════════════════════════════════════════════════════════

class TestValidatePrice:
    def test_valid(self):
        assert validate_price(30000.0) == pytest.approx(30000.0)

    def test_none_not_required(self):
        assert validate_price(None, required=False) is None

    def test_none_required_raises(self):
        with pytest.raises(ValueError, match="required"):
            validate_price(None, required=True)

    def test_zero_raises(self):
        with pytest.raises(ValueError, match="greater than 0"):
            validate_price(0)

    def test_string_number(self):
        assert validate_price("28500.50") == pytest.approx(28500.50)


# ══════════════════════════════════════════════════════════════════════════════
# Full order request validation
# ══════════════════════════════════════════════════════════════════════════════

class TestValidateOrderRequest:
    def test_market_order(self):
        req = validate_order_request("BTCUSDT", "BUY", "MARKET", 0.01)
        assert isinstance(req, OrderRequest)
        assert req.symbol == "BTCUSDT"
        assert req.side == "BUY"
        assert req.order_type == "MARKET"
        assert req.quantity == pytest.approx(0.01)
        assert req.price is None

    def test_limit_order(self):
        req = validate_order_request("ETHUSDT", "SELL", "LIMIT", 0.1, price=2500.0)
        assert req.order_type == "LIMIT"
        assert req.price == pytest.approx(2500.0)

    def test_limit_missing_price_raises(self):
        with pytest.raises(ValueError, match="required"):
            validate_order_request("BTCUSDT", "BUY", "LIMIT", 0.01)

    def test_stop_limit_order(self):
        req = validate_order_request(
            "BTCUSDT", "SELL", "STOP_LIMIT", 0.01,
            price=29000.0, stop_price=29500.0
        )
        assert req.order_type == "STOP_LIMIT"
        assert req.stop_price == pytest.approx(29500.0)

    def test_stop_limit_bad_cross_raises(self):
        # BUY stop_price must be <= price
        with pytest.raises(ValueError, match="stop price"):
            validate_order_request(
                "BTCUSDT", "BUY", "STOP_LIMIT", 0.01,
                price=29000.0, stop_price=30000.0    # stop > price — invalid for BUY
            )

    def test_invalid_symbol_raises(self):
        with pytest.raises(ValueError):
            validate_order_request("123", "BUY", "MARKET", 0.01)


# ══════════════════════════════════════════════════════════════════════════════
# Large order detection
# ══════════════════════════════════════════════════════════════════════════════

class TestIsLargeOrder:
    def test_not_large(self):
        assert is_large_order(0.01) is False

    def test_large(self):
        assert is_large_order(50.0) is True


# ══════════════════════════════════════════════════════════════════════════════
# validate_stop_price (directly — covers the function's own branches)
# ══════════════════════════════════════════════════════════════════════════════

class TestValidateStopPrice:
    def test_valid(self):
        from bot.validators import validate_stop_price
        assert validate_stop_price(29500.0) == pytest.approx(29500.0)

    def test_none_not_required(self):
        from bot.validators import validate_stop_price
        assert validate_stop_price(None, required=False) is None

    def test_none_required_raises(self):
        from bot.validators import validate_stop_price
        with pytest.raises(ValueError, match="required"):
            validate_stop_price(None, required=True)

    def test_zero_raises(self):
        from bot.validators import validate_stop_price
        with pytest.raises(ValueError, match="greater than 0"):
            validate_stop_price(0)

    def test_non_numeric_raises(self):
        from bot.validators import validate_stop_price
        with pytest.raises(ValueError, match="not a valid number"):
            validate_stop_price("bad")
