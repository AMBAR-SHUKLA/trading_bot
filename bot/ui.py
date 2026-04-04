"""
ui.py — Streamlit web UI for the Binance Futures Trading Bot.

Run with:
    streamlit run bot/ui.py

Features:
  • Order placement form (MARKET, LIMIT, STOP_LIMIT)
  • Real-time order book display
  • Account balance & open positions
  • Local order history with stats
  • Live connection status
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as `streamlit run bot/ui.py` from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from bot import logging_config  # noqa: E402
from bot.client import BinanceAPIError, CredentialsError  # noqa: E402
from bot.config import SUPPORTED_ORDER_TYPES, SUPPORTED_SIDES, validate_credentials  # noqa: E402
from bot.database import get_order_history, get_order_stats, init_db  # noqa: E402
from bot.orders import build_manager  # noqa: E402
from bot.validators import validate_order_request  # noqa: E402

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Binance Futures Bot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

logging_config.setup_logging()
init_db()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📈 Trading Bot")
    st.caption("Binance Futures Testnet • USDT-M")
    st.divider()

    creds_ok = validate_credentials()
    if creds_ok:
        st.success("✔ API credentials loaded", icon="🔑")
    else:
        st.error("✗ API credentials missing", icon="⚠️")
        st.info(
            "Create a `.env` file in the project root.\n"
            "See `.env.example` for the template.",
            icon="ℹ️",
        )

    st.divider()
    page = st.radio(
        "Navigate",
        ["🛒 Place Order", "📊 Order Book", "📜 History", "💼 Account"],
        label_visibility="collapsed",
    )

# ── Helper: build manager with error handling ─────────────────────────────────


@st.cache_resource(ttl=30)
def _get_manager():
    return build_manager()


def _safe_manager():
    try:
        return _get_manager()
    except CredentialsError as exc:
        st.error(str(exc))
        st.stop()


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: Place Order
# ═══════════════════════════════════════════════════════════════════════════════

if page == "🛒 Place Order":
    st.header("Place a New Order")

    col1, col2 = st.columns([1, 1], gap="large")

    with col1:
        st.subheader("Order Parameters")

        symbol = st.text_input("Symbol", value="BTCUSDT", placeholder="e.g. BTCUSDT").upper()
        side = st.selectbox("Side", SUPPORTED_SIDES)
        order_type = st.selectbox("Order Type", SUPPORTED_ORDER_TYPES)
        quantity = st.number_input("Quantity", min_value=0.0001, step=0.001, format="%.4f")

        price: float | None = None
        stop_price: float | None = None

        if order_type in ("LIMIT", "STOP_LIMIT"):
            price = st.number_input("Limit Price", min_value=0.01, step=0.01, format="%.2f")
        if order_type == "STOP_LIMIT":
            stop_price = st.number_input(
                "Stop Trigger Price", min_value=0.01, step=0.01, format="%.2f"
            )

        # ── Live price hint ───────────────────────────────────────────────────
        if creds_ok and symbol:
            try:
                mgr = _safe_manager()
                live_px = mgr.get_current_price(symbol)
                st.info(f"Current {symbol} price: **{live_px:,.2f} USDT**", icon="💡")
            except Exception:
                pass

    with col2:
        st.subheader("Order Preview")

        if symbol and side and order_type and quantity:
            preview_lines = [
                f"**Symbol** : {symbol}",
                f"**Side**   : {side}",
                f"**Type**   : {order_type}",
                f"**Qty**    : {quantity}",
            ]
            if price:
                preview_lines.append(f"**Price**  : {price}")
            if stop_price:
                preview_lines.append(f"**Stop**   : {stop_price}")
            st.markdown("\n\n".join(preview_lines))
        else:
            st.caption("Fill in the form to preview your order.")

    st.divider()

    if st.button("🚀 Submit Order", type="primary", disabled=not creds_ok):
        try:
            req = validate_order_request(symbol, side, order_type, quantity, price, stop_price)
        except ValueError as exc:
            st.error(f"Validation error: {exc}")
            st.stop()

        with st.spinner("Submitting order to Binance Testnet…"):
            try:
                mgr = _safe_manager()
                resp = mgr.execute_order(req)
            except BinanceAPIError as exc:
                st.error(f"Binance API error [{exc.code}]: {exc.message}")
                st.stop()
            except (TimeoutError, ConnectionError) as exc:
                st.error(str(exc))
                st.stop()

        st.success(f"✔ Order placed! Order ID: **{resp.order_id}**")
        st.json(resp.to_dict())


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: Order Book
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "📊 Order Book":
    st.header("Order Book Snapshot")

    sym = st.text_input("Symbol", value="BTCUSDT").upper()

    if st.button("Refresh", type="secondary") or sym:
        if not creds_ok:
            st.warning("Configure API credentials first.")
        else:
            try:
                mgr = _safe_manager()
                snap = mgr.get_order_book(sym)

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Best Bid", f"{snap.best_bid:,.4f}", f"qty {snap.best_bid_qty}")
                m2.metric("Best Ask", f"{snap.best_ask:,.4f}", f"qty {snap.best_ask_qty}")
                m3.metric("Mid Price", f"{snap.mid_price:,.4f}")
                m4.metric("Spread", f"{snap.spread:,.4f}")

                st.caption(f"Fetched at {snap.fetched_at.strftime('%H:%M:%S UTC')}")
            except Exception as exc:
                st.error(str(exc))


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: History
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "📜 History":
    st.header("Order History")

    c1, c2 = st.columns([2, 1])
    filter_sym = c1.text_input("Filter by symbol (blank = all)").upper() or None
    limit_n = c2.number_input("Max records", min_value=5, max_value=200, value=20, step=5)

    rows = get_order_history(filter_sym, int(limit_n))
    stats = get_order_stats()

    # ── Stats row ─────────────────────────────────────────────────────────────
    s1, s2, s3, s4, s5 = st.columns(5)
    s1.metric("Total Orders", stats.get("total", 0))
    s2.metric("Filled", stats.get("filled", 0))
    s3.metric("Buys", stats.get("buys", 0))
    s4.metric("Sells", stats.get("sells", 0))
    s5.metric("Total Notional", f"{round(stats.get('total_notional') or 0, 2)} USDT")

    st.divider()

    if rows:
        import pandas as pd

        df = pd.DataFrame(rows)
        df = df[["order_id", "symbol", "side", "order_type", "status",
                 "quantity", "executed_qty", "avg_price", "created_at"]]
        df.columns = ["Order ID", "Symbol", "Side", "Type", "Status",
                      "Qty", "Exec Qty", "Avg Price", "Placed At"]

        def _colour_side(val: str) -> str:
            if val == "BUY":
                return "color: #16c784"
            elif val == "SELL":
                return "color: #ea3943"
            return ""

        st.dataframe(
            df.style.applymap(_colour_side, subset=["Side"]),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No order history yet. Place some orders first.")


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: Account
# ═══════════════════════════════════════════════════════════════════════════════

elif page == "💼 Account":
    st.header("Account Overview")

    if not creds_ok:
        st.warning("Configure API credentials first.")
    else:
        if st.button("Refresh Account"):
            st.cache_resource.clear()

        try:
            mgr = _safe_manager()
            data = mgr.get_account_summary()
        except (CredentialsError, BinanceAPIError) as exc:
            st.error(str(exc))
            st.stop()

        b1, b2, b3 = st.columns(3)
        b1.metric("Wallet Balance", f"{data.get('totalWalletBalance', 'N/A')} USDT")
        b2.metric("Available Balance", f"{data.get('availableBalance', 'N/A')} USDT")
        b3.metric("Unrealised PnL", f"{data.get('totalUnrealizedProfit', 'N/A')} USDT")

        positions = [
            p for p in data.get("positions", [])
            if float(p.get("positionAmt", 0)) != 0
        ]

        if positions:
            st.subheader("Open Positions")
            import pandas as pd
            pos_df = pd.DataFrame(positions)[
                ["symbol", "positionAmt", "entryPrice", "markPrice", "unrealizedProfit"]
            ]
            pos_df.columns = ["Symbol", "Amount", "Entry Price", "Mark Price", "Unrealised PnL"]
            st.dataframe(pos_df, use_container_width=True, hide_index=True)
        else:
            st.info("No open positions.")
