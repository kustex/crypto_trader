
CRYPTO TRADER — Desktop GUI (PyQt6) for Signal Generation, Backtesting & Execution
==================================================================================

This repository contains a desktop trading application built with **PyQt6** that:
- pulls OHLCV data from exchanges via **ccxt** (plus spot quotes via yfinance),
- computes **Keltner Channels** and **Relative Vigor Index (RVI)** signals,
- lets you tune **signal** and **risk** parameters in real time,
- visualizes prices, indicators, and trade signals,
- places orders on **Bitget** (via ccxt) and monitors fills,
- runs **single‑asset backtests** with a simple workflow,
- stores all market data, signals, and parameters in **PostgreSQL** via **SQLAlchemy**.

> Screenshots are referenced below. Place your images at:
> - `docs/images/dashboard.png`   (Main dashboard)
> - `docs/images/backtester.png`  (Backtest panel)

In Markdown‑capable viewers, these would be embedded as:
    ![Dashboard](docs/images/dashboard.png)
    ![Backtester](docs/images/backtester.png)

Since this is a README.txt, most code hosts will still show the file nicely, but image embedding may not render in plain text.


-------------------------------------------------------------------------------
1) FEATURES
-------------------------------------------------------------------------------
• Multi‑panel UI (PyQt6):
  - Left: **Tickers** list + **Signal Management** + **Risk Management**
  - Center: **Chart Canvas** (price + Keltner bands + buy/sell markers)
  - Right: **Orders** panel (place market orders) + **Portfolio** (open/closed)

• Signals:
  - **Keltner Channels** (separate upper/lower multipliers, configurable period)
  - **RVI** on the active timeframe, with optional **15m RVI filter**
  - Final signal stored to DB in `signals_data`.

• Backtesting (single‑asset):
  - Choose symbol + date range + parameters, run backtest, see results and plots.
  - Progress bar + results table (performance summary, trades list/equity curve).

• Execution:
  - Place market orders to **Bitget** (via ccxt), monitor status until filled.
  - Order status checker runs in a background **QThread**.

• Storage:
  - PostgreSQL via **SQLAlchemy**. Tables auto‑created on first run.

• Scheduling:
  - Background fetch of new OHLCV candles per timeframe (15m/1h/1d/1w/1M).
  - Only stores **closed** candles. Handles retries and backfills.

• Timezone:
  - Internally uses UTC; UI displays **local (UTC+1)** timestamps.


-------------------------------------------------------------------------------
2) QUICK START
-------------------------------------------------------------------------------
Prerequisites
- Python 3.11+ recommended
- PostgreSQL 14+ (local or remote)
- (Windows) If you hit build issues with `psycopg2`, install `psycopg2-binary`

Suggested environment
    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    # macOS/Linux
    source .venv/bin/activate

Install dependencies
    pip install -U pip wheel
    pip install PyQt6 matplotlib pandas numpy SQLAlchemy psycopg2-binary ccxt yfinance schedule tenacity python-dateutil

Database configuration (environment variables)
Set the following before launching the app (example for a local Postgres):
    export POSTGRES_HOST=127.0.0.1
    export POSTGRES_PORT=5432
    export POSTGRES_DB=crypto_trader
    export POSTGRES_USER=postgres
    export POSTGRES_PASSWORD=postgres

On Windows (PowerShell), use:
    setx POSTGRES_HOST 127.0.0.1
    setx POSTGRES_PORT 5432
    setx POSTGRES_DB crypto_trader
    setx POSTGRES_USER postgres
    setx POSTGRES_PASSWORD postgres

API credentials (Bitget via ccxt)
The app reads/writes a simple credentials file:
    ~/.crypto_trading_api_credentials
Format (each on its own line):
    <API_KEY>
    <API_SECRET>
    <API_PASSPHRASE>
Permissions should be user‑only on Unix (chmod 600).

Launch
Depending on your project’s entry point, one of the following will start the GUI:
    python -m app              # if you have an __init__.py that boots the UI
    python -m app.ui.main_window
    python main.py             # if you keep a top‑level runner
Adjust to your repository’s layout.


-------------------------------------------------------------------------------
3) HOW TO USE THE APP
-------------------------------------------------------------------------------
A. Dashboard (Main Tab)
   1) Add or select a ticker in the **Tickers** panel.
   2) Choose a timeframe (e.g., 15m / 1h / 1d). The chart updates automatically.
   3) Click **Regenerate Signals** to recompute indicators and save to DB.
   4) Tune **Signal Management**:
      - Keltner: upper/lower multipliers, period
      - RVI: periods for 15m and 1h, thresholds, toggle “Include 15m RVI” filter
      - Save: parameters are persisted to `indicator_params` (per symbol/timeframe)
   5) Tune **Risk Management**:
      - Stoploss, position size, max allocation, partial sell fraction
      - Saved in `portfolio_risk_parameters` (per symbol)
   6) **Orders** panel:
      - Enter symbol, side, amount (units or $), and place a market order
      - The **Order Status Checker** monitors fills; portfolio tables refresh
   7) **Portfolio** panel:
      - Shows open positions (using latest quotes) and closed orders/trades

B. Backtester (Backtest Tab)
   1) Pick symbol and date range.
   2) Set the signal/risk parameters to test.
   3) Run. Watch progress, then review results and the plot.
   4) Iterate: tweak parameters and re‑run to compare outcomes.


-------------------------------------------------------------------------------
4) STRATEGY PRIMER
-------------------------------------------------------------------------------
Keltner Channels
- Middle line: moving average of price.
- Upper/Lower bands: middle ± (ATR × multiplier). Here, upper and lower have
  independent multipliers and a configurable period.

RVI (Relative Vigor Index)
- Computes a smoothed ratio of “direction” to “range” over a rolling window.
- Signal is derived by comparing RVI to upper/lower thresholds.
- App supports both **active timeframe RVI** and an optional **15m RVI filter**.

Final Signal
- Combines Keltner and RVI logic into a single **final_signal** stored in DB.
- The chart paints buy (▲) / sell (▼) markers at signal timestamps.


-------------------------------------------------------------------------------
5) DATA MODEL (PostgreSQL)
-------------------------------------------------------------------------------
Tables auto‑created by the app (via SQLAlchemy):

• historical_data
    timestamp   TIMESTAMP  (PK part)
    open        DOUBLE PRECISION
    high        DOUBLE PRECISION
    low         DOUBLE PRECISION
    close       DOUBLE PRECISION
    volume      DOUBLE PRECISION
    symbol      TEXT       (PK part)
    timeframe   TEXT       (PK part)

• indicator_historical_data
    timestamp   TIMESTAMP  (PK part)
    symbol      TEXT       (PK part)
    timeframe   TEXT       (PK part)
    keltner_upper  DOUBLE PRECISION
    keltner_lower  DOUBLE PRECISION
    rvi            DOUBLE PRECISION

• signals_data
    timestamp   TIMESTAMP  (PK part)
    symbol      TEXT       (PK part)
    timeframe   TEXT       (PK part)
    keltner_signal     INTEGER
    rvi_signal         INTEGER
    rvi_signal_15m     INTEGER DEFAULT 0
    final_signal       INTEGER

• indicator_params   (per symbol + timeframe)
    symbol      TEXT       (PK part)
    timeframe   TEXT       (PK part)
    keltner_upper_multiplier   DOUBLE PRECISION DEFAULT 3.0
    keltner_lower_multiplier   DOUBLE PRECISION DEFAULT 3.0
    keltner_period             INTEGER DEFAULT 24
    rvi_15m_period             INTEGER DEFAULT 10
    rvi_1h_period              INTEGER DEFAULT 10
    rvi_15m_upper_threshold    DOUBLE PRECISION DEFAULT  0.2
    rvi_15m_lower_threshold    DOUBLE PRECISION DEFAULT -0.2
    rvi_1h_upper_threshold     DOUBLE PRECISION DEFAULT  0.2
    rvi_1h_lower_threshold     DOUBLE PRECISION DEFAULT -0.2
    include_15m_rvi            INTEGER DEFAULT 1

• portfolio_risk_parameters  (per symbol)
    symbol              TEXT  (PK)
    stoploss            DOUBLE PRECISION DEFAULT 0.10
    position_size       DOUBLE PRECISION DEFAULT 0.05
    max_allocation      DOUBLE PRECISION DEFAULT 0.20
    partial_sell_fraction DOUBLE PRECISION DEFAULT 0.20

• tickers
    id          SERIAL PRIMARY KEY
    symbol      TEXT UNIQUE NOT NULL


-------------------------------------------------------------------------------
6) MODULE OVERVIEW (by responsibility)
-------------------------------------------------------------------------------
UI / Panels
- main_window.py         : Builds the main layout (left/center/right panes)
- plot_canvas.py         : Matplotlib chart (price, Keltner bands, signal markers)
- tickers_panel.py       : Add/remove/list tickers; drive chart refresh
- signal_parameters.py   : SignalManagementPanel (edit/save indicator_params)
- risk_parameters.py     : RiskManagementPanel (edit/save risk parameters)
- orders_panel.py        : Place orders and trigger OrderStatusChecker
- portfolio_panel.py     : Open positions, closed orders/trades tables
- backtest_panel.py      : Backtest tab: parameters, dates, run, results

Controllers / Logic
- indicator_generator.py : Keltner & RVI calculations
- signal_generator.py    : Compute & store per‑bar signals for symbol/timeframe
- signal_controller.py   : QThread wrapper to run signal generation asynchronously
- order_checker.py       : Poll order status until filled (emits Qt signal)

Core / Services
- data_handler.py        : ccxt scheduling, OHLCV ingestion, backfills
- trade_bot.py           : Glue for latest signal, portfolio evaluation, and actions
- executor.py            : Place orders via ccxt (Bitget); maintain local state
- database.py            : DB engine + migrations + common queries
- api_credentials.py     : Read/write ~/.crypto_trading_api_credentials

Notes
- Several modules rely on `LOCAL_TZ = UTC+1` for display. Data is stored in UTC.


-------------------------------------------------------------------------------
7) LOGGING & FILES
-------------------------------------------------------------------------------
- Logs: `logs/` (e.g., `logs/trading_bot.log`), created on first run.
- Saved state (optional): JSONs under `data/` (e.g., closed orders, trades).
- Credentials: `~/.crypto_trading_api_credentials`


-------------------------------------------------------------------------------
8) COMMON ISSUES / FAQ
-------------------------------------------------------------------------------
• psycopg2 build fails on Windows
  → Use `psycopg2-binary` during development.

• No data shows on chart
  → Confirm DB env vars, Postgres is running, and your symbol/timeframe has data.
  → Use the **Tickers** panel to add a symbol and wait for OHLCV to backfill.

• Orders rejected
  → Check API key/secret/passphrase, IP allowlists, and account permissions.
  → Ensure the symbol is tradable on Bitget spot/perp as configured in executor.

• Mixed timestamps
  → The UI shows **local time (UTC+1)** while data is stored in **UTC**.

• Images don’t render in README.txt
  → They will render if you duplicate this file as `README.md`.


-------------------------------------------------------------------------------
9) ROADMAP (ideas)
-------------------------------------------------------------------------------
- Multi‑asset backtest runner + parameter sweeps
- Strategy plug‑ins (additional indicators/filters)
- Risk overlay on chart (stop, targets, partial exits)
- Export results to CSV/Parquet
- Dockerized dev environment

-------------------------------------------------------------------------------
LICENSE
-------------------------------------------------------------------------------
Insert your chosen license here (e.g., MIT).


-------------------------------------------------------------------------------
CREDITS
-------------------------------------------------------------------------------
Built with PyQt6, Matplotlib, Pandas, NumPy, SQLAlchemy, psycopg2, ccxt, yfinance.
