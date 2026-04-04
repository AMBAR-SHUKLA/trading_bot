# Binance Futures Testnet Trading Bot

A Python command-line and web UI trading bot for the **Binance Futures USDT-M Testnet**.  
Supports MARKET, LIMIT, and STOP_LIMIT orders with full input validation, structured logging, and SQLite order history.

---

## Project Structure

```
trading_bot/
├── bot/
│   ├── __init__.py         # Package metadata
│   ├── __main__.py         # python -m bot entry point
│   ├── config.py           # All config from environment variables
│   ├── logging_config.py   # Dual (file + console) structured logging
│   ├── models.py           # Pure-Python data classes (OrderRequest, OrderResponse, …)
│   ├── validators.py       # Input validation (all fields, cross-field checks)
│   ├── client.py           # Binance REST client (signing, retry, rate-limit)
│   ├── orders.py           # Order execution business logic layer
│   ├── database.py         # SQLite persistence (order history, stats)
│   ├── cli.py              # Typer CLI (place-order, interactive, history, …)
│   └── ui.py               # Streamlit web UI (bonus)
├── tests/
│   ├── __init__.py
│   ├── test_validators.py  # Validator unit tests
│   └── test_client.py      # Client unit tests (mocked HTTP)
├── sample_logs/
│   ├── market_order.log
│   ├── limit_order.log
│   └── stop_limit_order.log
├── .env.example            # Credential template
├── .github/workflows/ci.yml
├── requirements.txt
└── README.md
```

---

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/AMBAR-SHUKLA/trading_bot.git
cd trading_bot
pip install -r requirements.txt
```

### 2. Configure credentials

```bash
cp .env.example .env
# Edit .env and fill in your Binance Futures Testnet API key + secret
```

Get free testnet credentials at: https://testnet.binancefuture.com

### 3. Run the CLI

```bash
# Place a market order
python -m bot place-order --symbol BTCUSDT --side BUY --type MARKET --qty 0.01

# Place a limit order
python -m bot place-order --symbol BTCUSDT --side BUY --type LIMIT --qty 0.01 --price 30000

# Place a stop-limit order
python -m bot place-order --symbol BTCUSDT --side SELL --type STOP_LIMIT --qty 0.01 --price 29000 --stop-price 29500

# Interactive wizard
python -m bot interactive

# View order book
python -m bot order-book --symbol BTCUSDT

# View local order history
python -m bot history --limit 20

# Account summary
python -m bot account

# Ping testnet
python -m bot ping
```

### 4. Run the web UI

```bash
streamlit run bot/ui.py
```

---

## Environment Variables

Copy `.env.example` to `.env` and configure:

| Variable                | Default                              | Description                        |
|-------------------------|--------------------------------------|------------------------------------|
| `BINANCE_API_KEY`       | *(required)*                         | Testnet API key                    |
| `BINANCE_API_SECRET`    | *(required)*                         | Testnet API secret                 |
| `BINANCE_BASE_URL`      | `https://testnet.binancefuture.com`  | API base URL                       |
| `REQUEST_TIMEOUT`       | `10`                                 | HTTP timeout in seconds            |
| `MAX_RETRIES`           | `3`                                  | Retry attempts on 5xx errors       |
| `RETRY_BACKOFF_FACTOR`  | `1.5`                                | Exponential back-off multiplier    |
| `MAX_ORDER_QUANTITY`    | `100.0`                              | Maximum allowed order quantity     |
| `LARGE_ORDER_THRESHOLD` | `10.0`                               | Quantity that triggers confirmation|
| `CONFIRM_LARGE_ORDERS`  | `true`                               | Prompt before large orders         |
| `LOG_LEVEL`             | `INFO`                               | Logging level (DEBUG/INFO/WARNING) |

---

## Running Tests

```bash
pytest tests/ -v --cov=bot --cov-report=term-missing
```

---

## CI

GitHub Actions runs on every push to `main`/`develop` and on pull requests:
- Lints with **flake8** (max line length 100)
- Runs **pytest** with coverage (minimum 70%)
- Tests against Python **3.10, 3.11, 3.12**

---

## License

MIT
