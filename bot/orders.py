"""
orders.py — High-level order execution logic.

This module sits between the CLI/UI and the raw BinanceClient.
It is responsible for:
  1. Dispatching to the correct client method based on order type.
  2. Persisting the result to the database.
  3. Logging every step in a structured way.
  4. Returning user-friendly results.
"""

from __future__ import annotations

from typing import Optional

from bot import logging_config
from bot.client import BinanceClient, BinanceAPIError
from bot.database import init_db, save_order, log_event
from bot.models import OrderRequest, OrderResponse, OrderBookSnapshot

log = logging_config.get_logger(__name__)


# ── OrderManager ──────────────────────────────────────────────────────────────

class OrderManager:
    """
    Orchestrates order lifecycle: validate → execute → persist → report.

    Args:
        client: An already-initialised BinanceClient instance.
    """

    def __init__(self, client: BinanceClient) -> None:
        self._client = client
        init_db()
        log.debug("OrderManager ready")

    # ── Core dispatch ─────────────────────────────────────────────────────────

    def execute_order(self, req: OrderRequest) -> OrderResponse:
        """
        Execute any supported order type and persist the result.

        Raises:
            BinanceAPIError: on exchange-level failures.
            ValueError:      on validation failures (caller should have caught
                             these in the CLI layer, but defensive check here).
        """
        log.info(
            "Executing %s %s order  symbol=%s  qty=%s",
            req.side, req.order_type, req.symbol, req.quantity,
        )

        try:
            if req.order_type == "MARKET":
                resp = self._client.place_market_order(
                    symbol=req.symbol,
                    side=req.side,
                    quantity=req.quantity,
                )

            elif req.order_type == "LIMIT":
                resp = self._client.place_limit_order(
                    symbol=req.symbol,
                    side=req.side,
                    quantity=req.quantity,
                    price=req.price,  # type: ignore[arg-type]
                    time_in_force=req.time_in_force,
                )

            elif req.order_type == "STOP_LIMIT":
                resp = self._client.place_stop_limit_order(
                    symbol=req.symbol,
                    side=req.side,
                    quantity=req.quantity,
                    price=req.price,        # type: ignore[arg-type]
                    stop_price=req.stop_price,  # type: ignore[arg-type]
                    time_in_force=req.time_in_force,
                )

            else:
                raise ValueError(f"Unsupported order type: {req.order_type}")

        except BinanceAPIError as exc:
            log_event("ORDER_FAILED", str(exc))
            log.error("Order failed  %s", exc)
            raise

        except (TimeoutError, ConnectionError) as exc:
            log_event("NETWORK_ERROR", str(exc))
            log.error("Network error during order  %s", exc)
            raise

        # ── Persist ────────────────────────────────────────────────────────
        try:
            row_id = save_order(resp)
            log.info("Order persisted  db_row=%s  order_id=%s", row_id, resp.order_id)
        except Exception as db_exc:
            log.warning("DB write failed (non-fatal)  %s", db_exc)

        return resp

    # ── Market data helpers ───────────────────────────────────────────────────

    def get_order_book(self, symbol: str) -> OrderBookSnapshot:
        """Fetch and return the current order book snapshot for a symbol."""
        log.info("Fetching order book  symbol=%s", symbol)
        return self._client.get_order_book(symbol)

    def get_current_price(self, symbol: str) -> float:
        """Return the latest price for a symbol."""
        price = self._client.get_price(symbol)
        log.info("Current price  symbol=%s  price=%s", symbol, price)
        return price

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """Return all open orders from Binance."""
        return self._client.get_open_orders(symbol)

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        """Cancel an open order and log the result."""
        log.info("Cancelling order  symbol=%s  order_id=%s", symbol, order_id)
        result = self._client.cancel_order(symbol, order_id)
        log_event("ORDER_CANCELLED", f"symbol={symbol} order_id={order_id}")
        return result

    def get_account_summary(self) -> dict:
        """Return account balance and position information."""
        return self._client.get_account()


# ── Module-level convenience ──────────────────────────────────────────────────

def build_manager() -> OrderManager:
    """Build and return an OrderManager with credentials from environment."""
    client = BinanceClient()
    return OrderManager(client)
