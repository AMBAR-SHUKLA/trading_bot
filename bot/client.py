"""
client.py — Binance Futures Testnet REST API client.

Features:
  • HMAC-SHA256 request signing
  • Automatic retry with exponential back-off
  • Rate-limit awareness (HTTP 429 / 418)
  • Structured logging of every request and response
  • No secrets ever appear in log output
"""

from __future__ import annotations

import hashlib
import hmac
import time
import urllib.parse
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from bot import logging_config
from bot.config import (
    API_KEY,
    API_SECRET,
    BASE_URL,
    MAX_RETRIES,
    REQUEST_TIMEOUT,
    RETRY_BACKOFF_FACTOR,
)
from bot.models import OrderBookSnapshot, OrderResponse

log = logging_config.get_logger(__name__)


# ── Exceptions ────────────────────────────────────────────────────────────────

class BinanceAPIError(Exception):
    """Raised when the Binance API returns a non-200 response."""

    def __init__(self, code: int, message: str, http_status: int = 400) -> None:
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(f"[{code}] {message} (HTTP {http_status})")


class CredentialsError(Exception):
    """Raised when API credentials are missing or invalid."""


# ── Session factory ──────────────────────────────────────────────────────────

def _build_session() -> requests.Session:
    """Create a requests.Session with retry logic pre-configured."""
    session = requests.Session()
    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF_FACTOR,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET", "POST", "DELETE"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# ── BinanceClient ─────────────────────────────────────────────────────────────

class BinanceClient:
    """
    Thin wrapper around the Binance Futures USDT-M REST API.

    Instantiate once and reuse across a trading session.
    """

    def __init__(
        self,
        api_key: str = API_KEY,
        api_secret: str = API_SECRET,
        base_url: str = BASE_URL,
    ) -> None:
        if not api_key or not api_secret:
            raise CredentialsError(
                "BINANCE_API_KEY and BINANCE_API_SECRET must be set "
                "(see .env.example)."
            )
        self._key = api_key
        self._secret = api_secret
        self._base = base_url.rstrip("/")
        self._session = _build_session()
        self._session.headers.update({"X-MBX-APIKEY": self._key})
        log.info("BinanceClient initialised  base_url=%s", self._base)

    # ── Signing ───────────────────────────────────────────────────────────────

    def _sign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Add timestamp + HMAC-SHA256 signature to a parameter dict."""
        params["timestamp"] = int(time.time() * 1000)
        query = urllib.parse.urlencode(params)
        sig = hmac.new(
            self._secret.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        params["signature"] = sig
        return params

    # ── Low-level HTTP ────────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = True,
    ) -> dict:
        """
        Execute an HTTP request and return the parsed JSON body.

        Handles rate-limit back-off and raises BinanceAPIError on failures.
        """
        params = params or {}
        if signed:
            params = self._sign(params)

        url = f"{self._base}{path}"

        # ── safe log (never log secret / signature) ────────────────────────
        safe_params = {k: v for k, v in params.items() if k not in ("signature",)}
        log.debug("→ %s %s  params=%s", method, path, safe_params)

        try:
            response = self._session.request(
                method,
                url,
                params=params if method == "GET" else None,
                data=params if method == "POST" else None,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.exceptions.Timeout:
            log.error("Request timed out after %ss  url=%s", REQUEST_TIMEOUT, url)
            raise TimeoutError(f"Request to {path} timed out.")
        except requests.exceptions.ConnectionError as exc:
            log.error("Connection error  url=%s  error=%s", url, exc)
            raise ConnectionError(f"Cannot reach {self._base}. Check network.") from exc

        # ── rate-limit handling ────────────────────────────────────────────
        if response.status_code in (429, 418):
            retry_after = int(response.headers.get("Retry-After", 5))
            log.warning("Rate-limited. Waiting %ss before retry.", retry_after)
            time.sleep(retry_after)
            return self._request(method, path, params=params, signed=False)

        # ── response parsing ───────────────────────────────────────────────
        try:
            data: dict = response.json()
        except ValueError:
            log.error(
                "Non-JSON response  status=%s  body=%s",
                response.status_code, response.text[:200],
            )
            raise BinanceAPIError(-1, "Non-JSON response from server.", response.status_code)

        if not response.ok:
            code = data.get("code", response.status_code)
            msg = data.get("msg", response.text)
            log.error("API error  code=%s  msg=%s  http=%s", code, msg, response.status_code)
            raise BinanceAPIError(code, msg, response.status_code)

        log.debug("← %s %s  status=%s", method, path, response.status_code)
        return data

    # ── Public API methods ─────────────────────────────────────────────────────

    def place_market_order(
        self, symbol: str, side: str, quantity: float
    ) -> OrderResponse:
        """Place a MARKET order."""
        params = {
            "symbol":   symbol,
            "side":     side,
            "type":     "MARKET",
            "quantity": quantity,
        }
        log.info(
            "Placing MARKET order  symbol=%s  side=%s  qty=%s",
            symbol, side, quantity,
        )
        data = self._request("POST", "/fapi/v1/order", params)
        resp = OrderResponse.from_binance(data)
        log.info(
            "MARKET order placed  order_id=%s  status=%s  executed_qty=%s  avg_price=%s",
            resp.order_id, resp.status, resp.executed_qty, resp.avg_price,
        )
        return resp

    def place_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        time_in_force: str = "GTC",
    ) -> OrderResponse:
        """Place a LIMIT order."""
        params = {
            "symbol":      symbol,
            "side":        side,
            "type":        "LIMIT",
            "timeInForce": time_in_force,
            "quantity":    quantity,
            "price":       price,
        }
        log.info(
            "Placing LIMIT order  symbol=%s  side=%s  qty=%s  price=%s",
            symbol, side, quantity, price,
        )
        data = self._request("POST", "/fapi/v1/order", params)
        resp = OrderResponse.from_binance(data)
        log.info(
            "LIMIT order placed  order_id=%s  status=%s",
            resp.order_id, resp.status,
        )
        return resp

    def place_stop_limit_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        stop_price: float,
        time_in_force: str = "GTC",
    ) -> OrderResponse:
        """Place a STOP_LIMIT (stop-loss with a limit price) order."""
        params = {
            "symbol":      symbol,
            "side":        side,
            "type":        "STOP",          # Binance uses STOP for stop-limit on futures
            "timeInForce": time_in_force,
            "quantity":    quantity,
            "price":       price,
            "stopPrice":   stop_price,
        }
        log.info(
            "Placing STOP_LIMIT order  symbol=%s  side=%s  qty=%s  price=%s  stop=%s",
            symbol, side, quantity, price, stop_price,
        )
        data = self._request("POST", "/fapi/v1/order", params)
        resp = OrderResponse.from_binance(data)
        log.info(
            "STOP_LIMIT order placed  order_id=%s  status=%s",
            resp.order_id, resp.status,
        )
        return resp

    def get_order(self, symbol: str, order_id: int) -> dict:
        """Query the status of a specific order."""
        log.info("Querying order  symbol=%s  order_id=%s", symbol, order_id)
        return self._request("GET", "/fapi/v1/order", {"symbol": symbol, "orderId": order_id})

    def cancel_order(self, symbol: str, order_id: int) -> dict:
        """Cancel an open order."""
        log.info("Cancelling order  symbol=%s  order_id=%s", symbol, order_id)
        return self._request("DELETE", "/fapi/v1/order", {"symbol": symbol, "orderId": order_id})

    def get_open_orders(self, symbol: Optional[str] = None) -> list:
        """Return all open orders, optionally filtered by symbol."""
        params: dict = {}
        if symbol:
            params["symbol"] = symbol
        log.info("Fetching open orders  symbol=%s", symbol or "all")
        data = self._request("GET", "/fapi/v1/openOrders", params)
        return data if isinstance(data, list) else []

    def get_account(self) -> dict:
        """Return account information (balance, positions)."""
        log.info("Fetching account info")
        return self._request("GET", "/fapi/v2/account", {})

    def get_order_book(self, symbol: str, limit: int = 5) -> OrderBookSnapshot:
        """Fetch top-of-book depth for a symbol (no signature required)."""
        log.debug("Fetching order book  symbol=%s  limit=%s", symbol, limit)
        data = self._request(
            "GET",
            "/fapi/v1/depth",
            {"symbol": symbol, "limit": limit},
            signed=False,
        )
        return OrderBookSnapshot.from_binance(symbol, data)

    def get_price(self, symbol: str) -> float:
        """Return the latest mark price for a symbol."""
        data = self._request(
            "GET", "/fapi/v1/ticker/price", {"symbol": symbol}, signed=False
        )
        return float(data.get("price", 0))

    def ping(self) -> bool:
        """Return True if the Binance API is reachable."""
        try:
            self._request("GET", "/fapi/v1/ping", {}, signed=False)
            return True
        except Exception:
            return False
