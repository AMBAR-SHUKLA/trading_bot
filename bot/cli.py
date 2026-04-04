"""
cli.py — Typer-based CLI for the Binance Futures Trading Bot.

Commands:
  place-order   Place a MARKET, LIMIT, or STOP_LIMIT order.
  interactive   Interactive wizard — asks for each field one by one.
  order-book    Show current order book snapshot for a symbol.
  open-orders   List open orders.
  history       Show local order history from the database.
  account       Display account balance summary.
  ping          Check connectivity to Binance testnet.

Usage examples:
  python -m bot.cli place-order --symbol BTCUSDT --side BUY --type MARKET --qty 0.01
  python -m bot.cli place-order --symbol BTCUSDT --side BUY --type LIMIT --qty 0.01 --price 30000
  python -m bot.cli interactive
  python -m bot.cli order-book --symbol ETHUSDT
  python -m bot.cli history --limit 10
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from bot import logging_config
from bot.client import BinanceAPIError, CredentialsError
from bot.config import (
    CONFIRM_LARGE_ORDERS,
    SUPPORTED_ORDER_TYPES,
    SUPPORTED_SIDES,
    validate_credentials,
)
from bot.database import get_order_history, get_order_stats, init_db
from bot.orders import build_manager
from bot.validators import (
    is_large_order,
    validate_order_request,
    validate_symbol,
    validate_side,
    validate_order_type,
    validate_quantity,
    validate_price,
    validate_stop_price,
)

console = Console()
app = typer.Typer(
    name="trading-bot",
    help=(
        "[bold cyan]Binance Futures Testnet Trading Bot[/bold cyan]\n\n"
        "Place orders, check the market, and manage positions."
    ),
    no_args_is_help=True,
    rich_markup_mode="rich",
)

log = logging_config.get_logger(__name__)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _setup(verbose: bool = False) -> None:
    """Initialise logging and DB."""
    logging_config.setup_logging(verbose=verbose)
    init_db()


def _banner() -> None:
    console.print(
        Panel(
            "[bold cyan]  Binance Futures Testnet Trading Bot  [/bold cyan]\n"
            "[dim]  USDT-M Futures  |  Paper Trading Only  [/dim]",
            border_style="cyan",
        )
    )


def _check_credentials() -> None:
    if not validate_credentials():
        console.print(
            "[bold red]✗ API credentials not configured.[/bold red]\n"
            "Copy [dim].env.example[/dim] → [dim].env[/dim] and fill in your "
            "Binance Futures Testnet API key + secret.",
            highlight=False,
        )
        raise typer.Exit(code=1)


def _confirm_large_order(qty: float) -> None:
    if CONFIRM_LARGE_ORDERS and is_large_order(qty):
        console.print(
            f"\n[yellow]⚠ Large order detected: quantity = {qty}[/yellow]"
        )
        confirmed = typer.confirm("Are you sure you want to proceed?", default=False)
        if not confirmed:
            console.print("[dim]Order cancelled by user.[/dim]")
            raise typer.Exit()


def _print_success(resp_summary: str) -> None:
    console.print(
        Panel(
            f"[bold green]✔ Order Placed Successfully[/bold green]\n\n{resp_summary}",
            border_style="green",
        )
    )


def _print_error(msg: str) -> None:
    console.print(
        Panel(f"[bold red]✗ Error[/bold red]\n\n{msg}", border_style="red")
    )


# ── place-order command ───────────────────────────────────────────────────────

@app.command("place-order")
def place_order(
    symbol: str = typer.Option(..., "--symbol", "-s", help="Trading pair, e.g. BTCUSDT"),
    side: str = typer.Option(..., "--side", help="BUY or SELL"),
    order_type: str = typer.Option(..., "--type", "-t", help="MARKET | LIMIT | STOP_LIMIT"),
    qty: float = typer.Option(..., "--qty", "-q", help="Order quantity"),
    price: Optional[float] = typer.Option(
        None, "--price", "-p",
        help="Limit price (required for LIMIT / STOP_LIMIT)",
    ),
    stop_price: Optional[float] = typer.Option(
        None, "--stop-price",
        help="Stop trigger price (required for STOP_LIMIT)",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging"),
) -> None:
    """Place a single order on Binance Futures Testnet."""
    _setup(verbose)
    _banner()
    _check_credentials()

    # ── Validate ──────────────────────────────────────────────────────────────
    try:
        req = validate_order_request(symbol, side, order_type, qty, price, stop_price)
    except ValueError as exc:
        _print_error(str(exc))
        log.warning("Validation failed  %s", exc)
        raise typer.Exit(code=1)

    # ── Show request summary ──────────────────────────────────────────────────
    console.print("\n[bold]Order Request:[/bold]")
    console.print(req.summary())

    # ── Risk check ────────────────────────────────────────────────────────────
    _confirm_large_order(req.quantity)

    # ── Execute ───────────────────────────────────────────────────────────────
    try:
        manager = build_manager()
        resp = manager.execute_order(req)
    except CredentialsError as exc:
        _print_error(str(exc))
        raise typer.Exit(code=1)
    except BinanceAPIError as exc:
        _print_error(
            f"Binance API error [{exc.code}]: {exc.message}\n"
            f"HTTP status: {exc.http_status}"
        )
        raise typer.Exit(code=1)
    except (TimeoutError, ConnectionError) as exc:
        _print_error(str(exc))
        raise typer.Exit(code=1)

    _print_success(resp.summary())
    log.info("CLI place-order completed  order_id=%s", resp.order_id)


# ── interactive command ───────────────────────────────────────────────────────

@app.command("interactive")
def interactive_mode(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """
    [bold]Interactive wizard[/bold] — guided order entry with live validation.

    Prompts for each field and validates immediately. Perfect for first-time users.
    """
    _setup(verbose)
    _banner()
    _check_credentials()

    console.print("\n[bold cyan]Interactive Order Wizard[/bold cyan]")
    console.print("[dim]Press Ctrl-C at any time to cancel.[/dim]\n")

    # ── Symbol ────────────────────────────────────────────────────────────────
    while True:
        raw_symbol = typer.prompt("Symbol (e.g. BTCUSDT)")
        try:
            symbol = validate_symbol(raw_symbol)
            break
        except ValueError as exc:
            console.print(f"[red]  ✗ {exc}[/red]")

    # ── Optional: show live price ─────────────────────────────────────────────
    try:
        manager = build_manager()
        price_now = manager.get_current_price(symbol)
        console.print(f"[dim]  Current price of {symbol}: {price_now}[/dim]")
    except Exception:
        pass

    # ── Side ──────────────────────────────────────────────────────────────────
    while True:
        raw_side = typer.prompt(f"Side [{'/'.join(SUPPORTED_SIDES)}]")
        try:
            side = validate_side(raw_side)
            break
        except ValueError as exc:
            console.print(f"[red]  ✗ {exc}[/red]")

    # ── Order type ────────────────────────────────────────────────────────────
    while True:
        raw_type = typer.prompt(f"Order type [{'/'.join(SUPPORTED_ORDER_TYPES)}]")
        try:
            order_type = validate_order_type(raw_type)
            break
        except ValueError as exc:
            console.print(f"[red]  ✗ {exc}[/red]")

    # ── Quantity ──────────────────────────────────────────────────────────────
    while True:
        raw_qty = typer.prompt("Quantity")
        try:
            qty = validate_quantity(raw_qty)
            break
        except ValueError as exc:
            console.print(f"[red]  ✗ {exc}[/red]")

    # ── Price (LIMIT / STOP_LIMIT) ────────────────────────────────────────────
    price: Optional[float] = None
    if order_type in ("LIMIT", "STOP_LIMIT"):
        while True:
            raw_price = typer.prompt("Limit price")
            try:
                price = validate_price(raw_price, required=True)
                break
            except ValueError as exc:
                console.print(f"[red]  ✗ {exc}[/red]")

    # ── Stop price (STOP_LIMIT) ───────────────────────────────────────────────
    stop_price: Optional[float] = None
    if order_type == "STOP_LIMIT":
        while True:
            raw_stop = typer.prompt("Stop trigger price")
            try:
                stop_price = validate_stop_price(raw_stop, required=True)
                break
            except ValueError as exc:
                console.print(f"[red]  ✗ {exc}[/red]")

    # ── Validate full request ─────────────────────────────────────────────────
    try:
        req = validate_order_request(symbol, side, order_type, qty, price, stop_price)
    except ValueError as exc:
        _print_error(str(exc))
        raise typer.Exit(code=1)

    # ── Review & confirm ──────────────────────────────────────────────────────
    console.print("\n[bold]Order Summary (review before submitting):[/bold]")
    console.print(req.summary())
    _confirm_large_order(req.quantity)

    confirmed = typer.confirm("\nSubmit this order?", default=True)
    if not confirmed:
        console.print("[dim]Order cancelled.[/dim]")
        raise typer.Exit()

    # ── Execute ───────────────────────────────────────────────────────────────
    try:
        resp = manager.execute_order(req)
    except BinanceAPIError as exc:
        _print_error(f"[{exc.code}] {exc.message}")
        raise typer.Exit(code=1)
    except (TimeoutError, ConnectionError) as exc:
        _print_error(str(exc))
        raise typer.Exit(code=1)

    _print_success(resp.summary())


# ── order-book command ────────────────────────────────────────────────────────

@app.command("order-book")
def order_book(
    symbol: str = typer.Option("BTCUSDT", "--symbol", "-s", help="Trading pair"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Show the current top-of-book order book snapshot for a symbol."""
    _setup(verbose)
    _check_credentials()

    try:
        symbol = validate_symbol(symbol)
        manager = build_manager()
        snap = manager.get_order_book(symbol)
    except (ValueError, CredentialsError) as exc:
        _print_error(str(exc))
        raise typer.Exit(code=1)

    console.print(
        Panel(
            f"[bold]Order Book — {snap.symbol}[/bold]\n\n{snap.display()}\n"
            f"\n  [dim]Fetched at {snap.fetched_at.strftime('%H:%M:%S UTC')}[/dim]",
            border_style="cyan",
        )
    )


# ── open-orders command ───────────────────────────────────────────────────────

@app.command("open-orders")
def open_orders(
    symbol: Optional[str] = typer.Option(None, "--symbol", "-s"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """List currently open orders on Binance."""
    _setup(verbose)
    _check_credentials()

    try:
        manager = build_manager()
        orders = manager.get_open_orders(symbol)
    except (CredentialsError, BinanceAPIError) as exc:
        _print_error(str(exc))
        raise typer.Exit(code=1)

    if not orders:
        console.print("[dim]No open orders.[/dim]")
        return

    table = Table(title="Open Orders", border_style="cyan")
    for col in ["Order ID", "Symbol", "Side", "Type", "Qty", "Price", "Status"]:
        table.add_column(col)

    for o in orders:
        table.add_row(
            str(o.get("orderId", "")),
            o.get("symbol", ""),
            o.get("side", ""),
            o.get("type", ""),
            str(o.get("origQty", "")),
            str(o.get("price", "")),
            o.get("status", ""),
        )
    console.print(table)


# ── history command ───────────────────────────────────────────────────────────

@app.command("history")
def history(
    symbol: Optional[str] = typer.Option(None, "--symbol", "-s", help="Filter by symbol"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of records to show"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Display local order history from the database."""
    _setup(verbose)
    init_db()

    rows = get_order_history(symbol, limit)
    stats = get_order_stats()

    if not rows:
        console.print("[dim]No orders in local history.[/dim]")
        return

    table = Table(title="Order History (local DB)", border_style="blue")
    cols = [
        "Order ID", "Symbol", "Side", "Type",
        "Status", "Qty", "Exec Qty", "Avg Price", "Placed At",
    ]
    for col in cols:
        table.add_column(col, no_wrap=True)

    for r in rows:
        side_style = "green" if r["side"] == "BUY" else "red"
        table.add_row(
            str(r["order_id"]),
            r["symbol"],
            Text(r["side"], style=side_style),
            r["order_type"],
            r["status"],
            str(r["quantity"]),
            str(r["executed_qty"]),
            str(r["avg_price"]),
            (r["created_at"] or "")[:19],
        )

    console.print(table)

    # ── Stats footer ──────────────────────────────────────────────────────────
    console.print(
        f"\n[dim]Total orders: {stats.get('total', 0)}  |  "
        f"Filled: {stats.get('filled', 0)}  |  "
        f"Buys: {stats.get('buys', 0)}  |  "
        f"Sells: {stats.get('sells', 0)}  |  "
        f"Total notional: {round(stats.get('total_notional') or 0, 2)} USDT[/dim]"
    )


# ── account command ───────────────────────────────────────────────────────────

@app.command("account")
def account(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Display Binance Futures account balance and positions."""
    _setup(verbose)
    _check_credentials()

    try:
        manager = build_manager()
        data = manager.get_account_summary()
    except (CredentialsError, BinanceAPIError) as exc:
        _print_error(str(exc))
        raise typer.Exit(code=1)

    total_balance = data.get("totalWalletBalance", "N/A")
    unrealised_pnl = data.get("totalUnrealizedProfit", "N/A")
    avail_balance = data.get("availableBalance", "N/A")

    console.print(
        Panel(
            f"[bold]Account Summary[/bold]\n\n"
            f"  Wallet Balance  : {total_balance} USDT\n"
            f"  Available       : {avail_balance} USDT\n"
            f"  Unrealised PnL  : {unrealised_pnl} USDT",
            border_style="blue",
        )
    )

    positions = [p for p in data.get("positions", []) if float(p.get("positionAmt", 0)) != 0]
    if positions:
        table = Table(title="Open Positions", border_style="yellow")
        for col in ["Symbol", "Amount", "Entry Price", "Mark Price", "Unrealised PnL"]:
            table.add_column(col)
        for pos in positions:
            pnl_val = float(pos.get("unrealizedProfit", 0))
            pnl_style = "green" if pnl_val >= 0 else "red"
            table.add_row(
                pos.get("symbol", ""),
                str(pos.get("positionAmt", "")),
                str(pos.get("entryPrice", "")),
                str(pos.get("markPrice", "")),
                Text(str(pnl_val), style=pnl_style),
            )
        console.print(table)
    else:
        console.print("[dim]No open positions.[/dim]")


# ── ping command ──────────────────────────────────────────────────────────────

@app.command("ping")
def ping(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Check connectivity to the Binance Futures Testnet."""
    _setup(verbose)
    _check_credentials()

    try:
        manager = build_manager()
        ok = manager._client.ping()
    except CredentialsError as exc:
        _print_error(str(exc))
        raise typer.Exit(code=1)

    if ok:
        console.print("[bold green]✔ Binance Testnet is reachable.[/bold green]")
    else:
        console.print("[bold red]✗ Cannot reach Binance Testnet.[/bold red]")
        raise typer.Exit(code=1)


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()
