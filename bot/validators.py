"""
validators.py — Input validation for all order parameters.

Raises descriptive ValueError exceptions that the CLI/UI can surface to users.
All validation follows OWASP "validate all input" guidelines.
"""

from __future__ import annotations

import re
from typing import Optional

from bot.config import (
    SUPPORTED_ORDER_TYPES,
    SUPPORTED_SIDES,
    MAX_ORDER_QUANTITY,
)
from bot.models import OrderRequest


# ── Individual field validators ───────────────────────────────────────────────

def validate_symbol(symbol: str) -> str:
    """
    Validate trading symbol.

    Rules:
      • Non-empty
      • Uppercase letters only (e.g. BTCUSDT, ETHUSDT)
      • 3–20 characters
    """
    if not symbol:
        raise ValueError("Symbol cannot be empty.")
    symbol = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z]{3,20}", symbol):
        raise ValueError(
            f"Invalid symbol '{symbol}'. "
            "Must be 3–20 uppercase letters (e.g. BTCUSDT)."
        )
    return symbol


def validate_side(side: str) -> str:
    """Validate order side — must be BUY or SELL."""
    side = side.strip().upper()
    if side not in SUPPORTED_SIDES:
        raise ValueError(
            f"Invalid side '{side}'. Must be one of: {', '.join(SUPPORTED_SIDES)}."
        )
    return side


def validate_order_type(order_type: str) -> str:
    """Validate order type — MARKET, LIMIT, or STOP_LIMIT."""
    order_type = order_type.strip().upper().replace("-", "_").replace(" ", "_")
    if order_type not in SUPPORTED_ORDER_TYPES:
        raise ValueError(
            f"Invalid order type '{order_type}'. "
            f"Supported: {', '.join(SUPPORTED_ORDER_TYPES)}."
        )
    return order_type


def validate_quantity(quantity: float | str) -> float:
    """Validate order quantity — must be a finite positive number within limits."""
    try:
        qty = float(quantity)
    except (TypeError, ValueError):
        raise ValueError(f"Quantity '{quantity}' is not a valid number.")

    if qty <= 0:
        raise ValueError(f"Quantity must be greater than 0. Got {qty}.")
    if qty > MAX_ORDER_QUANTITY:
        raise ValueError(
            f"Quantity {qty} exceeds the configured maximum ({MAX_ORDER_QUANTITY}). "
            "Update MAX_ORDER_QUANTITY in your .env to override."
        )
    return qty


def validate_price(price: float | str | None, *, required: bool = False) -> Optional[float]:
    """Validate order price — required for LIMIT and STOP_LIMIT orders."""
    if price is None or price == "":
        if required:
            raise ValueError("Price is required for LIMIT and STOP_LIMIT orders.")
        return None

    try:
        p = float(price)
    except (TypeError, ValueError):
        raise ValueError(f"Price '{price}' is not a valid number.")

    if p <= 0:
        raise ValueError(f"Price must be greater than 0. Got {p}.")
    return p


def validate_stop_price(
    stop_price: float | str | None, *, required: bool = False
) -> Optional[float]:
    """Validate stop price — required for STOP_LIMIT orders."""
    if stop_price is None or stop_price == "":
        if required:
            raise ValueError("Stop price is required for STOP_LIMIT orders.")
        return None

    try:
        sp = float(stop_price)
    except (TypeError, ValueError):
        raise ValueError(f"Stop price '{stop_price}' is not a valid number.")

    if sp <= 0:
        raise ValueError(f"Stop price must be greater than 0. Got {sp}.")
    return sp


# ── Full order validator ──────────────────────────────────────────────────────

def validate_order_request(
    symbol: str,
    side: str,
    order_type: str,
    quantity: float | str,
    price: float | str | None = None,
    stop_price: float | str | None = None,
) -> OrderRequest:
    """
    Validate all order fields and return a well-formed OrderRequest.

    Raises ValueError with a descriptive message on the first failure.
    """
    v_symbol = validate_symbol(symbol)
    v_side = validate_side(side)
    v_type = validate_order_type(order_type)
    v_qty = validate_quantity(quantity)

    needs_price = v_type in ("LIMIT", "STOP_LIMIT")
    needs_stop = v_type == "STOP_LIMIT"

    v_price = validate_price(price, required=needs_price)
    v_stop = validate_stop_price(stop_price, required=needs_stop)

    # Cross-field: stop must be below/above limit price for risk sanity
    if v_type == "STOP_LIMIT" and v_price and v_stop:
        # For BUY stop-limit: stop_price <= price (trigger before execution)
        # For SELL stop-limit: stop_price >= price
        if v_side == "BUY" and v_stop > v_price:
            raise ValueError(
                f"For a BUY STOP_LIMIT order, stop price ({v_stop}) must be "
                f"≤ limit price ({v_price})."
            )
        if v_side == "SELL" and v_stop < v_price:
            raise ValueError(
                f"For a SELL STOP_LIMIT order, stop price ({v_stop}) must be "
                f"≥ limit price ({v_price})."
            )

    return OrderRequest(
        symbol=v_symbol,
        side=v_side,
        order_type=v_type,
        quantity=v_qty,
        price=v_price,
        stop_price=v_stop,
    )


def is_large_order(quantity: float) -> bool:
    """Return True if the quantity exceeds the large-order warning threshold."""
    from bot.config import LARGE_ORDER_THRESHOLD
    return quantity >= LARGE_ORDER_THRESHOLD
