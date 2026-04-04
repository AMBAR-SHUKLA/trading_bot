"""
models.py — Pure-Python data classes for orders and API responses.

No ORM dependency.  SQLite persistence is handled in database.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


# ── Order request ─────────────────────────────────────────────────────────────

@dataclass
class OrderRequest:
    """Validated user request before it reaches the API."""

    symbol: str
    side: str                    # BUY | SELL
    order_type: str              # MARKET | LIMIT | STOP_LIMIT
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    time_in_force: str = "GTC"

    def summary(self) -> str:
        parts = [
            f"Symbol  : {self.symbol}",
            f"Side    : {self.side}",
            f"Type    : {self.order_type}",
            f"Quantity: {self.quantity}",
        ]
        if self.price is not None:
            parts.append(f"Price   : {self.price}")
        if self.stop_price is not None:
            parts.append(f"StopPrc : {self.stop_price}")
        return "\n".join(parts)


# ── Order response ────────────────────────────────────────────────────────────

@dataclass
class OrderResponse:
    """Normalised response from Binance after order placement."""

    order_id: int
    client_order_id: str
    symbol: str
    side: str
    order_type: str
    status: str
    quantity: float
    executed_qty: float
    avg_price: float
    price: float
    stop_price: float
    time_in_force: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    raw: dict = field(default_factory=dict)

    # ── constructors ──────────────────────────────────────────────────────────

    @classmethod
    def from_binance(cls, data: dict) -> "OrderResponse":
        """Build from a raw Binance REST response dict."""
        return cls(
            order_id=int(data.get("orderId", 0)),
            client_order_id=data.get("clientOrderId", ""),
            symbol=data.get("symbol", ""),
            side=data.get("side", ""),
            order_type=data.get("type", ""),
            status=data.get("status", ""),
            quantity=float(data.get("origQty", 0)),
            executed_qty=float(data.get("executedQty", 0)),
            avg_price=float(data.get("avgPrice", 0)),
            price=float(data.get("price", 0)),
            stop_price=float(data.get("stopPrice", 0)),
            time_in_force=data.get("timeInForce", "GTC"),
            raw=data,
        )

    # ── display ───────────────────────────────────────────────────────────────

    def summary(self) -> str:
        lines = [
            "─" * 50,
            "  ORDER CONFIRMATION",
            "─" * 50,
            f"  Order ID      : {self.order_id}",
            f"  Client Ord ID : {self.client_order_id}",
            f"  Symbol        : {self.symbol}",
            f"  Side          : {self.side}",
            f"  Type          : {self.order_type}",
            f"  Status        : {self.status}",
            f"  Quantity      : {self.quantity}",
            f"  Executed Qty  : {self.executed_qty}",
            f"  Avg Price     : {self.avg_price}",
        ]
        if self.price:
            lines.append(f"  Limit Price   : {self.price}")
        if self.stop_price:
            lines.append(f"  Stop Price    : {self.stop_price}")
        lines.append("─" * 50)
        return "\n".join(lines)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("raw", None)
        d["created_at"] = self.created_at.isoformat()
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ── Order book ────────────────────────────────────────────────────────────────

@dataclass
class OrderBookSnapshot:
    """Top-of-book from Binance depth endpoint."""

    symbol: str
    best_bid: float
    best_bid_qty: float
    best_ask: float
    best_ask_qty: float
    mid_price: float
    spread: float
    fetched_at: datetime = field(default_factory=datetime.utcnow)

    @classmethod
    def from_binance(cls, symbol: str, data: dict) -> "OrderBookSnapshot":
        bids = data.get("bids", [])
        asks = data.get("asks", [])
        best_bid = float(bids[0][0]) if bids else 0.0
        best_bid_qty = float(bids[0][1]) if bids else 0.0
        best_ask = float(asks[0][0]) if asks else 0.0
        best_ask_qty = float(asks[0][1]) if asks else 0.0
        mid = (best_bid + best_ask) / 2 if best_bid and best_ask else 0.0
        spread = best_ask - best_bid if best_bid and best_ask else 0.0
        return cls(
            symbol=symbol,
            best_bid=best_bid,
            best_bid_qty=best_bid_qty,
            best_ask=best_ask,
            best_ask_qty=best_ask_qty,
            mid_price=mid,
            spread=spread,
        )

    def display(self) -> str:
        return (
            f"  {'Bid':>10}  {self.best_bid:>12.4f}  (qty {self.best_bid_qty})\n"
            f"  {'Ask':>10}  {self.best_ask:>12.4f}  (qty {self.best_ask_qty})\n"
            f"  {'Mid':>10}  {self.mid_price:>12.4f}\n"
            f"  {'Spread':>10}  {self.spread:>12.4f}"
        )
