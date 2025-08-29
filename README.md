# Crypto Trader (PyQt6) — Signals, Backtests & One‑Click Orders

A fast, desktop‑first app for exploring trading ideas and executing them without leaving your charts. Built with **PyQt6**, **Matplotlib**, **ccxt**, and **PostgreSQL**.

> **Screenshots** live in `docs/images/` and are shown at the relevant sections below:
> - `docs/images/dashboard.png` (Main Dashboard)
> - `docs/images/backtester.png` (Backtester)

---

## Table of Contents
- [Highlights](#highlights)
- [Screenshot — Main Dashboard](#screenshot--main-dashboard)
- [Install](#install)
- [Configure](#configure)
- [Run](#run)
- [How to Use](#how-to-use)
  - [Dashboard](#dashboard)
  - [Backtesting](#backtesting)
  - [Orders & Portfolio](#orders--portfolio)
- [Under the Hood](#under-the-hood)
  - [Data Model](#data-model)
  - [Project Layout](#project-layout)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [License](#license)

---

## Highlights

- **Chart + Signals:** Price, **Keltner Channels**, **RVI**, and combined buy/sell markers.
- **Live tweakability:** Change periods/thresholds/multipliers in the UI and regenerate.
- **Backtests in seconds:** Single‑asset runs with summary metrics and visuals.
- **Real orders:** Market/limit via **Bitget** (through **ccxt**) + background fill tracking.
- **Solid storage:** PostgreSQL via SQLAlchemy (candles, indicators, signals, params).
- **Clean UI:** PyQt6 with a responsive layout and separate panels for each task.
- **Local time UX:** Data stored in UTC; UI renders timestamps in your local zone (Europe/Brussels by default).

---

## Screenshot — Main Dashboard

<p align="center">
  <img src="docs/images/dashboard.PNG" alt="Main Dashboard" loading="lazy">
</p>

The dashboard shows your active symbol/timeframe, indicators, and final signals. Edit parameters on the left, place orders on the right, and watch portfolio tables update as fills arrive.

---

## Install

> Works on **Windows 11 (Git Bash / PowerShell)**, macOS, and Linux. Python **3.11+** recommended.

```bash
# 1) Create a virtual environment
python -m venv .venv

# 2) Activate it
# Windows (PowerShell)
. .venv/Scripts/Activate.ps1
# Windows (Git Bash)
source .venv/Scripts/activate
# macOS/Linux
# source .venv/bin/activate

# 3) Install dependencies
pip install -U pip wheel
pip install PyQt6 matplotlib pandas numpy SQLAlchemy psycopg2-binary ccxt yfinance tenacity schedule python-dateutil
```

> **Note (Windows):** If `psycopg2` compilation fails, keep using `psycopg2-binary` for development.

---

## Configure

### Database (PostgreSQL)
Set environment variables (examples for a local instance):

```bash
# PowerShell: use  setx KEY "value"  (then restart shell)
export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=5432
export POSTGRES_DB=crypto_trader
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=postgres
```

### Exchange API (Bitget via ccxt)
Store your creds in a local file read by the app:

- **Path:** `~/.crypto_trading_api_credentials`  
- **Format (3 lines):**
  ```text
  <API_KEY>
  <API_SECRET>
  <API_PASSPHRASE>
  ```
- Restrict permissions on Unix: `chmod 600 ~/.crypto_trading_api_credentials`

---

## Run

From the repo root:

```bash
# Option A — run via module
python -m app.ui.main_window

# Option B — if you have a top-level script
python main.py
```

> If your package layout differs, adjust the command accordingly.

---

## How to Use

### Dashboard
1. **Pick a ticker & timeframe** in the left panel.
2. **Regenerate Signals** after tweaking parameters:
   - **Keltner:** period + separate upper/lower multipliers.
   - **RVI:** periods & thresholds; optional **15m RVI filter** for stricter entries.
3. **Read signals**: buy ▲ / sell ▼ markers on the chart, plus indicator overlays.
4. **Place orders** in the right panel (Market/Limit). A background checker tracks fills.
5. **Portfolio** panel shows open positions and closed trades updated in near‑real time.

### Backtesting

<p align="center">
  <img src="docs/images/backtester.PNG" alt="Backtester" loading="lazy">
</p>

1. Pick **symbol** and **date range** (and timeframe if applicable).
2. Set indicator/risk parameters to test.
3. Click **Run**. Review summary stats, trades, and the equity/markers plot.
4. Iterate quickly to compare different parameter sets.

### Orders & Portfolio
- Orders are sent to **Bitget** via **ccxt**.
- A dedicated worker polls order status until filled/canceled.
- **Portfolio** aggregates open/closed positions and recent fills.

---

## Under the Hood

### Data Model
Tables are created automatically (via SQLAlchemy). Key tables:

```sql
-- Candles
historical_data(
  timestamp TIMESTAMP, open DOUBLE PRECISION, high DOUBLE PRECISION,
  low DOUBLE PRECISION, close DOUBLE PRECISION, volume DOUBLE PRECISION,
  symbol TEXT, timeframe TEXT,
  PRIMARY KEY (timestamp, symbol, timeframe)
);

-- Indicators
indicator_historical_data(
  timestamp TIMESTAMP, symbol TEXT, timeframe TEXT,
  keltner_upper DOUBLE PRECISION, keltner_lower DOUBLE PRECISION, rvi DOUBLE PRECISION,
  PRIMARY KEY (timestamp, symbol, timeframe)
);

-- Signals
signals_data(
  timestamp TIMESTAMP, symbol TEXT, timeframe TEXT,
  keltner_signal INT, rvi_signal INT, rvi_signal_15m INT DEFAULT 0, final_signal INT,
  PRIMARY KEY (timestamp, symbol, timeframe)
);

-- Per-symbol/timeframe indicator params
indicator_params(
  symbol TEXT, timeframe TEXT,
  keltner_upper_multiplier DOUBLE PRECISION DEFAULT 3.0,
  keltner_lower_multiplier DOUBLE PRECISION DEFAULT 3.0,
  keltner_period INT DEFAULT 24,
  rvi_15m_period INT DEFAULT 10,
  rvi_1h_period INT DEFAULT 10,
  rvi_15m_upper_threshold DOUBLE PRECISION DEFAULT  0.2,
  rvi_15m_lower_threshold DOUBLE PRECISION DEFAULT -0.2,
  rvi_1h_upper_threshold  DOUBLE PRECISION DEFAULT  0.2,
  rvi_1h_lower_threshold  DOUBLE PRECISION DEFAULT -0.2,
  include_15m_rvi INT DEFAULT 1,
  PRIMARY KEY (symbol, timeframe)
);

-- Risk knobs per symbol
portfolio_risk_parameters(
  symbol TEXT PRIMARY KEY,
  stoploss DOUBLE PRECISION DEFAULT 0.10,
  position_size DOUBLE PRECISION DEFAULT 0.05,
  max_allocation DOUBLE PRECISION DEFAULT 0.20,
  partial_sell_fraction DOUBLE PRECISION DEFAULT 0.20
);

-- Tickers list
tickers(
  id SERIAL PRIMARY KEY,
  symbol TEXT UNIQUE NOT NULL
);
```

### Project Layout

```
app/
  controllers/
    indicator_generator.py     # Keltner & RVI calculations
    signal_generator.py        # Combine indicators → final signals
    signal_controller.py       # Run generation in a worker thread
    order_checker.py           # Poll order status until filled
  ui/
    main_window.py             # Top‑level UI & wiring
    plot_canvas.py             # Matplotlib chart (price + bands + markers)
    tickers_panel.py           # Ticker management
    signal_parameters.py       # Edit/save indicator params
    risk_parameters.py         # Stop, size, allocation, partial exits
    orders_panel.py            # Market/limit orders
    portfolio_panel.py         # Open/closed positions
  data_handler.py              # ccxt ingestion & backfills (closed candles only)
  executor.py                  # ccxt Bitget integration
  trade_bot.py                 # Glue for signals ↔ actions
  database.py                  # Postgres engine & queries
  api_credentials.py           # Read/write local API creds
docs/
  images/
    dashboard.png
    backtester.png
```

---

## Troubleshooting

- **No candles on chart?** Check DB env vars, Postgres is running, and the symbol/timeframe is ingested.
- **Orders rejected?** Verify API credentials, instrument availability, and account permissions on Bitget.
- **Timestamps look off?** Storage is **UTC**; UI renders **local time (Europe/Brussels)**.
- **Windows line endings warning?** Add a `.gitattributes` with `*.py text eol=lf` and run `git add --renormalize .`

---

## Roadmap

- Batch backtests & parameter sweeps
- Strategy plug‑ins (more indicators/filters)
- Risk overlays on chart (stops/targets)
- CSV/Parquet exports
- Dockerized dev setup

---

## License

Choose and include a license (MIT, Apache‑2.0, etc.).
