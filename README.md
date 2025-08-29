# Crypto Trader (PyQt6) — Signals, Backtests & One‑Click Orders

## What
A desktop app to **explore trading ideas** and **execute trades** from the same screen. Tune parameters, regenerate signals, run quick backtests, and submit orders through your exchange account.

<p align="center">
  <img src="docs/images/dashboard.PNG" alt="Dashboard with chart, indicators, signal controls, orders and portfolio" loading="lazy">
</p>

---

## Why
- **Tight feedback loop:** tweak → see signals → backtest → place trade — all in one place.  
- **Desktop-first:** fast, focused PyQt6 UI without browser clutter.  
- **Practical stack:** ccxt + PostgreSQL keep data and execution reliable and portable.

---

## Features
- **Dashboard:** Price chart with **Keltner Channels**, **RVI**, and **buy/sell markers**.  
  Signal and risk controls on the left; orders and portfolio on the right.
- **Signals:** Independent Keltner multipliers/periods, RVI thresholds, optional **15m RVI filter**.  
  Signals combine into a single **final signal** used for backtests & execution.
- **Backtester:** Single‑asset runs with summary metrics and a visual of the test period.  
- **Trading:** Market/Limit orders to **Bitget** (via **ccxt**); a background worker tracks fills.  
- **Portfolio:** Open/closed positions view updated as orders fill.  
- **Storage:** Candles, indicators, and signals in **PostgreSQL** (via **SQLAlchemy**).  
- **Cross‑platform:** Windows, macOS, Linux (Python 3.11+).

<p align="center">
  <img src="docs/images/backtester.PNG" alt="Backtester: parameters, run results and plot" loading="lazy">
</p>

**Tech used**
- **Python 3.11+**, **PyQt6**, **Matplotlib**
- **ccxt** (Bitget) for trading; **yfinance** for quick quotes
- **PostgreSQL** via **SQLAlchemy** (use `psycopg2-binary` for dev on Windows)
- Utility deps: `tenacity`, `schedule`, `python-dateutil`

---

## Getting Started

> Works on **Windows 11** (Git Bash or PowerShell), **macOS**, and **Linux**. Use **Python 3.11+**.

### 1) Create and activate a virtual environment
```bash
python -m venv .venv
# Windows (PowerShell)
. .venv/Scripts/Activate.ps1
# Windows (Git Bash)
source .venv/Scripts/activate
# macOS/Linux
# source .venv/bin/activate
```

### 2) Install dependencies
```bash
pip install -U pip wheel
pip install PyQt6 matplotlib pandas numpy SQLAlchemy psycopg2-binary ccxt yfinance tenacity schedule python-dateutil
```

### 3) Configure PostgreSQL (environment variables)
**Bash (macOS/Linux/Git Bash):**
```bash
export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=5432
export POSTGRES_DB=crypto_trader
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=postgres
```
**Windows PowerShell (persist for new shells):**
```powershell
setx POSTGRES_HOST 127.0.0.1
setx POSTGRES_PORT 5432
setx POSTGRES_DB crypto_trader
setx POSTGRES_USER postgres
setx POSTGRES_PASSWORD postgres
```

### 4) Add exchange API credentials (Bitget via ccxt)
Create the file `~/.crypto_trading_api_credentials` with three lines:
```
<API_KEY>
<API_SECRET>
<API_PASSPHRASE>
```
> On Unix, restrict permissions: `chmod 600 ~/.crypto_trading_api_credentials`

### 5) Run the app
From the repo root:
```bash
# Module entry (most setups)
python -m app.ui.main_window
# Or if you keep a top-level runner
python main.py
```

---

## Documentation
- **Core components:** Dashboard, Signal Engine (Keltner + RVI + optional 15m filter), Backtester, Orders & Portfolio.  
- **Usage flow:** select ticker & timeframe → adjust params → regenerate signals → (optional) backtest → place order.  
- **Notes:** Candles/signals stored in **UTC**; UI can display local time. For Windows builds, prefer `psycopg2-binary` during development.

---

## Roadmap
- Batch backtests & parameter sweeps  
- Strategy plug‑ins (more indicators/filters)  
- Risk overlays on chart (stops/targets)  
- CSV/Parquet export  
- Dockerized dev setup

---

## License
Add your license file and mention it here (e.g., MIT, Apache‑2.0).
