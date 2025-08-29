# Crypto Trader (PyQt6) — Signals, Backtests & One‑Click Orders

A desktop app to **explore trading ideas** and **execute trades** from the same screen. Tune parameters, regenerate signals, backtest quickly, and send orders when you’re ready.

---

## Core Components

### Dashboard (Chart + Controls)
- Chart with **price**, **Keltner Channels**, **RVI**, and **buy/sell markers**.
- **Left**: Tickers, Signal params (Keltner & RVI), Risk params.
- **Right**: Orders (Market/Limit) and Portfolio (open/closed).

<p align="center">
  <img src="docs/images/dashboard.PNG" alt="Dashboard with chart, indicators, signal controls, orders and portfolio" loading="lazy">
</p>

### Signal Engine
- **Keltner Channels** (independent upper/lower multipliers; configurable period).
- **RVI** with thresholds and optional **15m RVI filter** to tighten entries.
- Merges indicators into a single **final signal** used by backtests and trading.

### Backtesting
- Single‑asset backtests with summary metrics and a plot of the run.
- Iterate quickly by tweaking parameters and rerunning.

<p align="center">
  <img src="docs/images/backtester.PNG" alt="Backtester: parameters, run results and plot" loading="lazy">
</p>

### Orders & Portfolio
- Send Market/Limit orders to **Bitget** (via **ccxt**).
- Background worker monitors order status and updates **Portfolio** views.

---

## Install on Your PC

> Works on **Windows 11** (Git Bash or PowerShell), **macOS**, and **Linux**. Use **Python 3.11+**.

1) **Create and activate a virtual environment**
```bash
python -m venv .venv
# Windows (PowerShell)
. .venv/Scripts/Activate.ps1
# Windows (Git Bash)
source .venv/Scripts/activate
# macOS/Linux
# source .venv/bin/activate
```

2) **Install dependencies**
```bash
pip install -U pip wheel
pip install PyQt6 matplotlib pandas numpy SQLAlchemy psycopg2-binary ccxt yfinance tenacity schedule python-dateutil
```

3) **Configure PostgreSQL (environment variables)**
- **Bash (macOS/Linux/Git Bash):**
```bash
export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=5432
export POSTGRES_DB=crypto_trader
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=postgres
```
- **Windows PowerShell (persists for new shells):**
```powershell
setx POSTGRES_HOST 127.0.0.1
setx POSTGRES_PORT 5432
setx POSTGRES_DB crypto_trader
setx POSTGRES_USER postgres
setx POSTGRES_PASSWORD postgres
```

4) **Add exchange API credentials (Bitget via ccxt)**
Create the file `~/.crypto_trading_api_credentials` with three lines:
```
<API_KEY>
<API_SECRET>
<API_PASSPHRASE>
```
> On Unix, restrict permissions: `chmod 600 ~/.crypto_trading_api_credentials`

5) **Run the app**
From the repo root:
```bash
# Module entry (most setups)
python -m app.ui.main_window
# Or if you keep a top-level runner
python main.py
```

---

## Tech Stack

- **Language & UI**: Python 3.11+, **PyQt6**, **Matplotlib**
- **Market Data & Trading**: **ccxt** (Bitget), **yfinance** (quotes)
- **Storage**: **PostgreSQL** via **SQLAlchemy** (`psycopg2-binary` recommended for dev)
- **Utilities**: `tenacity`, `schedule`, `python-dateutil`

**Notes**
- Candles/signals are stored in **UTC**; timestamps in the UI can display local time.
- If `psycopg2` compiles poorly on Windows, stick with `psycopg2-binary` during development.
- To keep commits clean, consider a `.gitignore` with `__pycache__/`, `*.pyc`, etc.

---

## FAQ (Quick Hits)
- **No data on chart?** Check DB env vars and that your symbol/timeframe has candles ingested.
- **Orders rejected?** Verify API key/secret/passphrase, instrument availability, and exchange permissions.
- **Images not visible on GitHub?** Ensure `README.md` is at the repo root and image paths exist under `docs/images/`.

---

## License
Choose and include a license (e.g., MIT, Apache‑2.0).
