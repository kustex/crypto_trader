from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget,
    QTableWidgetItem, QProgressBar, QLineEdit, QApplication
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
import sys
from datetime import date, timedelta
import pandas as pd
import ccxt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
from sqlalchemy import text
from app.backtest.backtest_engine import BacktestEngine

# Define parameter names and default values.
PARAMETER_NAMES = [
    "Keltner Upper Multiplier", "Keltner Lower Multiplier",
    "Keltner Period", "RVI 15m Period", "RVI 1h Period",
    "RVI 15m Upper Threshold", "RVI 15m Lower Threshold",
    "RVI 1h Upper Threshold", "RVI 1h Lower Threshold",
    "Include 15m RVI", "Stop-Loss %", "Position Size %",
    "Max Allocation %", "Partial Sell %"
]
DEFAULT_VALUES = [
    2.0, 2.0, 20, 10, 14, 0.3, -0.3, 0.3, -0.3, 0, 0.1, 0.05, 0.2, 0.5
]

class DataFetchThread(QThread):
    data_fetched = pyqtSignal(str, pd.DataFrame)  # Emits (timeframe, DataFrame)
    error = pyqtSignal(str, str)  # Emits (timeframe, error message)
    
    def __init__(self, ticker, timeframe, start_date, end_date):
        super().__init__()
        self.ticker = ticker
        self.timeframe = timeframe
        self.start_date = start_date
        self.end_date = end_date

    def run(self):
        try:
            exchange = ccxt.binance({'enableRateLimit': True})
            req_start = pd.to_datetime(self.start_date)
            req_end = pd.to_datetime(self.end_date)
            since = int(req_start.timestamp() * 1000)
            end_ts = int(req_end.timestamp() * 1000)
            ohlcv = []
            limit = 1000
            while True:
                data = exchange.fetch_ohlcv(self.ticker, self.timeframe, since=since, limit=limit)
                if not data:
                    break
                ohlcv += data
                last = data[-1][0]
                if last >= end_ts:
                    break
                since = last + 1
            df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            df = df[(df["timestamp"] >= req_start) & (df["timestamp"] <= req_end)]
            self.data_fetched.emit(self.timeframe, df)
        except Exception as e:
            self.error.emit(self.timeframe, str(e))

class BacktestPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.backtest_engine = BacktestEngine()
        # In-memory cache keyed by (ticker, timeframe, start_date, end_date)
        self.data_cache = {}
        self.thread1 = None  # For 1h data
        self.thread2 = None  # For 15m data
        self.init_ui()

    def init_ui(self):
        """Initialize the UI with left column (inputs) and right column (plots)."""
        main_layout = QHBoxLayout()

        # LEFT COLUMN
        left_layout = QVBoxLayout()
        
        # Ticker Input
        ticker_layout = QHBoxLayout()
        ticker_label = QLabel("Ticker:")
        self.ticker_input = QLineEdit()
        self.ticker_input.setText("BTC/USDT")
        ticker_layout.addWidget(ticker_label)
        ticker_layout.addWidget(self.ticker_input)
        left_layout.addLayout(ticker_layout)
        
        # Date Range Inputs
        date_layout = QHBoxLayout()
        start_date_label = QLabel("Start Date:")
        self.start_date_input = QLineEdit()
        self.start_date_input.setPlaceholderText("YYYY-MM-DD")
        today = date.today()
        self.start_date_input.setText(f"{today - timedelta(weeks=52)}")
        end_date_label = QLabel("End Date:")
        self.end_date_input = QLineEdit()
        self.end_date_input.setPlaceholderText("YYYY-MM-DD")
        self.end_date_input.setText(f"{today}")
        date_layout.addWidget(start_date_label)
        date_layout.addWidget(self.start_date_input)
        date_layout.addWidget(end_date_label)
        date_layout.addWidget(self.end_date_input)
        left_layout.addLayout(date_layout)
        
        # Parameter Table
        self.signal_param_table = QTableWidget(len(PARAMETER_NAMES), 2)
        self.signal_param_table.setHorizontalHeaderLabels(["Parameter", "Value"])
        for row, name in enumerate(PARAMETER_NAMES):
            item_name = QTableWidgetItem(name)
            item_value = QTableWidgetItem(str(DEFAULT_VALUES[row]))
            self.signal_param_table.setItem(row, 0, item_name)
            self.signal_param_table.setItem(row, 1, item_value)
        left_layout.addWidget(self.signal_param_table)
        
        # Run Backtest Button
        self.run_backtest_button = QPushButton("Run Backtest")
        self.run_backtest_button.clicked.connect(self.run_backtest)
        left_layout.addWidget(self.run_backtest_button)
        
        # Progress Bar and Status Label
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        left_layout.addWidget(self.progress_bar)
        self.status_label = QLabel("Status: Ready")
        left_layout.addWidget(self.status_label)
        
        # RIGHT COLUMN
        right_layout = QVBoxLayout()
        self.figure, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(8, 10))
        self.canvas = FigureCanvas(self.figure)
        right_layout.addWidget(self.canvas)
        self.stats_label = QLabel("PnL: - | Sharpe Ratio: - | Max Drawdown: - | Trades: -")
        right_layout.addWidget(self.stats_label)
        
        main_layout.addLayout(left_layout, 1)
        main_layout.addLayout(right_layout, 2)
        self.setLayout(main_layout)

    def run_backtest(self):
        """Run the backtest using parameters and date range from the UI."""
        params = self.get_parameters()
        self.backtest_engine.ticker = self.ticker_input.text().strip()
        self.status_label.setText("Status: Loading data...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        ticker = self.ticker_input.text().strip()
        start_date = self.start_date_input.text().strip()
        end_date = self.end_date_input.text().strip()
        
        # Build cache keys for 1h and 15m.
        key1h = (ticker, "1h", start_date, end_date)
        key15m = (ticker, "15m", start_date, end_date)
        
        # Launch background threads if data not in cache.
        if key1h not in self.data_cache:
            self.thread1 = DataFetchThread(ticker, "1h", start_date, end_date)
            self.thread1.data_fetched.connect(lambda tf, df: self.store_in_cache(tf, df, params))
            self.thread1.error.connect(lambda tf, err: self.status_label.setText(f"Error ({tf}): {err}"))
            self.thread1.start()
        else:
            print("Using in-memory cache for", key1h)
        
        if key15m not in self.data_cache:
            self.thread2 = DataFetchThread(ticker, "15m", start_date, end_date)
            self.thread2.data_fetched.connect(lambda tf, df: self.store_in_cache(tf, df, params))
            self.thread2.error.connect(lambda tf, err: self.status_label.setText(f"Error ({tf}): {err}"))
            self.thread2.start()
        else:
            print("Using in-memory cache for", key15m)
        
        # Check periodically if both datasets are available.
        self.check_and_run_backtest(params)

    def store_in_cache(self, timeframe, df, params):
        """Store fetched data in cache."""
        ticker = self.ticker_input.text().strip()
        start_date = self.start_date_input.text().strip()
        end_date = self.end_date_input.text().strip()
        key = (ticker, timeframe, start_date, end_date)
        self.data_cache[key] = df.copy()
        print(f"Cached {timeframe} data for", key)
        self.check_and_run_backtest(params)

    def check_and_run_backtest(self, params):
        """If both 1h and 15m data (if required) are cached, run the backtest."""
        ticker = self.ticker_input.text().strip()
        start_date = self.start_date_input.text().strip()
        end_date = self.end_date_input.text().strip()
        key1h = (ticker, "1h", start_date, end_date)
        key15m = (ticker, "15m", start_date, end_date)
        
        if params["include_15m_rvi"]:
            if key1h in self.data_cache and key15m in self.data_cache:
                df1h = self.data_cache[key1h].copy()
                df15m = self.data_cache[key15m].copy()
                self.run_backtest_with_data(df1h, df15m, params)
        else:
            if key1h in self.data_cache:
                df1h = self.data_cache[key1h].copy()
                self.run_backtest_with_data(df1h, None, params)

    def run_backtest_with_data(self, df1h, df15m, params):
        """Run the backtest with the provided data and update the UI."""
        self.status_label.setText("Status: Data loaded. Running backtest...")
        df = self.backtest_engine.calculate_indicators(df1h, df15m, params)
        df = self.backtest_engine.generate_signals(df, params)
        try:
            df, stats = self.backtest_engine.run_backtest(df, params)
            if df is None or stats is None:
                raise ValueError("❌ run_backtest() returned invalid data!")
        except Exception as e:
            self.status_label.setText(f"Error in backtest: {e}")
            return

        equity_title = (
            f"Backtest Equity Curve {self.ticker_input.text().strip()} | PnL: {stats.get('PnL', 0):.2f} | "
            f"Sharpe: {stats.get('Sharpe', 0):.2f} | Max Drawdown: {stats.get('MaxDrawdown', 0):.2f}%"
        )
        self.ax1.clear()
        self.ax1.plot(df['timestamp'], df["equity"], label="Equity Curve", color="blue")
        self.ax1.set_title(equity_title)
        self.ax1.set_xlabel("Time")
        self.ax1.set_ylabel("Equity")
        self.ax1.legend()

        self.ax2.clear()
        self.ax2.plot(df['timestamp'], df["invested_pct"], label="Invested Capital %", color="green")
        self.ax2.set_title("Invested Capital % of Total")
        self.ax2.set_xlabel("Time")
        self.ax2.set_ylabel("% Invested")
        self.ax2.legend()

        self.canvas.draw()
        self.stats_label.setText(
            f"PnL: {stats.get('PnL', 0):.2f} | Sharpe: {stats.get('Sharpe', 0):.2f} | "
            f"Max Drawdown: {stats.get('MaxDrawdown', 0):.2f}% | Trades: {stats.get('Trades', 0)}"
        )
        self.status_label.setText("Status: Backtest complete")
        self.progress_bar.setVisible(False)

    def get_parameters(self):
        """Retrieve parameters from the parameter table."""
        def safe_int(value):
            return int(float(value))
        params = {
            "keltner_upper_multiplier": float(self.signal_param_table.item(0, 1).text()),
            "keltner_lower_multiplier": float(self.signal_param_table.item(1, 1).text()),
            "keltner_period": safe_int(self.signal_param_table.item(2, 1).text()),
            "rvi_15m_period": safe_int(self.signal_param_table.item(3, 1).text()),
            "rvi_1h_period": safe_int(self.signal_param_table.item(4, 1).text()),
            "rvi_15m_upper_threshold": float(self.signal_param_table.item(5, 1).text()),
            "rvi_15m_lower_threshold": float(self.signal_param_table.item(6, 1).text()),
            "rvi_1h_upper_threshold": float(self.signal_param_table.item(7, 1).text()),
            "rvi_1h_lower_threshold": float(self.signal_param_table.item(8, 1).text()),
            "include_15m_rvi": int(float(self.signal_param_table.item(9, 1).text())),
            "stoploss": float(self.signal_param_table.item(10, 1).text()),
            "position_size": float(self.signal_param_table.item(11, 1).text()),
            "max_allocation": float(self.signal_param_table.item(12, 1).text()),
            "partial_sell_fraction": float(self.signal_param_table.item(13, 1).text())
        }
        return params

    def get_historical_data(self, timeframe="1h"):
        """
        Retrieve historical market data from Binance using ccxt.
        Uses the in-memory cache keyed by (ticker, timeframe, start_date, end_date).
        """
        ticker = self.ticker_input.text().strip()
        start_date = self.start_date_input.text().strip()
        end_date = self.end_date_input.text().strip()
        key = (ticker, timeframe, start_date, end_date)
        if key in self.data_cache:
            return self.data_cache[key].copy()
        else:
            self.status_label.setText("Status: Loading data...")
            self.data_thread = DataFetchThread(ticker, timeframe, start_date, end_date)
            self.data_thread.data_fetched.connect(lambda df: self.on_data_fetched(df, self.get_parameters()))
            self.data_thread.error.connect(lambda err: self.status_label.setText(f"Error: {err}"))
            self.data_thread.start()
            return pd.DataFrame()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    panel = BacktestPanel()
    panel.show()
    sys.exit(app.exec())
