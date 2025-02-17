from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel, QTableWidget, QTableWidgetItem,
    QHBoxLayout, QProgressBar, QLineEdit
)
from PyQt6.QtCore import QThread, pyqtSignal
import os
import pandas as pd
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
from sqlalchemy import text
from app.database import DatabaseManager
from app.backtest.backtest_engine import BacktestEngine

class OptimizationThread(QThread):
    progress_signal = pyqtSignal(int)   # Signal to update progress bar
    finished_signal = pyqtSignal(dict)  # Signal to update UI when done

    def __init__(self, backtest_engine, max_evals=50):
        super().__init__()
        self.backtest_engine = backtest_engine
        self.max_evals = max_evals

    def run(self):
        """Run optimization in a separate thread."""
        print("🚀 Running Parameter Optimization in Background Thread...")
        best_params = None

        # Run one iteration at a time so we can update the progress bar
        for i in range(1, self.max_evals + 1):
            best_params = self.backtest_engine.optimize_parameters(max_evals=1)
            progress = int((i / self.max_evals) * 100)
            self.progress_signal.emit(progress)
        self.finished_signal.emit(best_params)


class BacktestPanel(QWidget):
    def __init__(self, db_manager: DatabaseManager):
        super().__init__()
        self.db_manager = db_manager
        self.backtest_engine = BacktestEngine()
        self.init_ui()
        self.optimization_thread = None  

    def init_ui(self):
        """Initialize the Backtest UI."""
        layout = QVBoxLayout()

        # --- Ticker Input ---
        ticker_layout = QHBoxLayout()
        ticker_label = QLabel("Ticker:")
        self.ticker_input = QLineEdit()
        self.ticker_input.setText("BTC/USDT")  
        ticker_layout.addWidget(ticker_label)
        ticker_layout.addWidget(self.ticker_input)
        layout.addLayout(ticker_layout)

        # --- Parameter Table ---
        self.signal_param_table = QTableWidget(14, 2)
        self.signal_param_table.setHorizontalHeaderLabels(["Parameter", "Value"])
        self.signal_param_table.setVerticalHeaderLabels([
            "Keltner Upper Multiplier", "Keltner Lower Multiplier",
            "Keltner Period", "RVI 15m Period", "RVI 1h Period",
            "RVI 15m Upper Threshold", "RVI 15m Lower Threshold",
            "RVI 1h Upper Threshold", "RVI 1h Lower Threshold",
            "Include 15m RVI", "Stop-Loss %", "Position Size %",
            "Max Allocation %", "Partial Sell %"
        ])

        # --- Buttons ---
        self.run_backtest_button = QPushButton("Run Backtest")
        self.run_backtest_button.clicked.connect(self.run_backtest)

        self.optimize_button = QPushButton("Optimize Parameters")
        self.optimize_button.clicked.connect(self.start_optimization)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.run_backtest_button)
        button_layout.addWidget(self.optimize_button)

        # --- Progress Bar & Status ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.status_label = QLabel("Status: Ready")

        # --- Matplotlib Figure with Dual Plots ---
        # Top plot: Equity Curve; Bottom plot: Invested Capital %
        self.figure, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(8, 10))
        self.canvas = FigureCanvas(self.figure)

        # --- Statistics Label ---
        self.stats_label = QLabel("PnL: - | Sharpe Ratio: - | Sortino Ratio: - | Max Drawdown: - | Trades: -")

        # --- Assemble Layout ---
        layout.addWidget(self.signal_param_table)
        layout.addLayout(button_layout)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.status_label)
        layout.addWidget(self.canvas)
        layout.addWidget(self.stats_label)
        self.setLayout(layout)

    def start_optimization(self):
        """
        Runs Bayesian Optimization in a background thread.
        The current ticker is passed to the backtest engine so that
        the optimal parameters are saved under that ticker.
        """
        print("🚀 Starting Background Parameter Optimization...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status_label.setText("🔄 Optimizing parameters...")

        # Pass the current ticker to the backtest engine
        self.backtest_engine.ticker = self.ticker_input.text()

        self.optimization_thread = OptimizationThread(self.backtest_engine, max_evals=50)
        self.optimization_thread.progress_signal.connect(self.progress_bar.setValue)
        self.optimization_thread.finished_signal.connect(self.on_optimization_complete)
        self.optimization_thread.start()

    def on_optimization_complete(self, best_params):
        """
        Called when optimization completes.
        Updates the UI with the best parameters found.
        """
        print("✅ Optimization Complete. Updating UI...")
        self.progress_bar.setValue(100)
        self.status_label.setText("✅ Optimization Complete. Parameters saved!")
        # Update the parameter table with the best parameters
        param_values = list(best_params.values())
        for row, value in enumerate(param_values):
            self.signal_param_table.setItem(row, 1, QTableWidgetItem(str(round(value, 4))))
        print("✅ Best Parameters Updated in UI!")

    def run_backtest(self):
        """Run the backtest using current parameters and display the results."""
        params = self.get_parameters()
        # Pass the current ticker to the backtest engine
        self.backtest_engine.ticker = self.ticker_input.text()

        df = self.get_historical_data(timeframe="1h")
        df_15m = self.get_historical_data(timeframe="15m") if params["include_15m_rvi"] else None

        if df is None:
            self.stats_label.setText("⚠️ No data available for backtesting.")
            return

        df = self.backtest_engine.calculate_indicators(df, df_15m, params)
        df = self.backtest_engine.generate_signals(df, params)

        try:
            df, stats = self.backtest_engine.run_backtest(df, params)
            if df is None or stats is None:
                raise ValueError("❌ run_backtest() returned invalid data!")
        except Exception as e:
            print(f"❌ Error in run_backtest(): {e}")
            return

        # --- Plot Equity Curve ---
        self.ax1.clear()
        self.ax1.plot(df['timestamp'], df["equity"], label="Equity Curve", color="blue")
        self.ax1.set_title("Backtest Equity Curve")
        self.ax1.set_xlabel("Time")
        self.ax1.set_ylabel("Equity")
        self.ax1.legend()

        # --- Plot Invested Capital % ---
        self.ax2.clear()
        self.ax2.plot(df['timestamp'], df["invested_pct"], label="Invested Capital %", color="green")
        self.ax2.set_title("Invested Capital % of Total")
        self.ax2.set_xlabel("Time")
        self.ax2.set_ylabel("% Invested")
        self.ax2.legend()

        self.canvas.draw()

        # --- Update Statistics ---
        self.stats_label.setText(
            f"PnL: {stats['PnL']:.2f} | Sharpe Ratio: {stats['Sharpe Ratio']:.2f} | "
            f"Sortino Ratio: {stats['Sortino Ratio']:.2f} | Max Drawdown: {stats['Max Drawdown']:.2f}% | "
            f"Trades: {stats['Trades']}"
        )

    def get_parameters(self):
        """
        Retrieve user-defined backtest parameters from the table.
        Converts integer parameters safely.
        """
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
        Fetch historical market data for the given timeframe.
        """
        ticker = self.ticker_input.text()
        query = text(f"""
            SELECT timestamp, open, high, low, close, volume
            FROM historical_data
            WHERE symbol = '{ticker}' AND timeframe = '{timeframe}'
            ORDER BY timestamp ASC
        """)
        with self.db_manager.engine.connect() as connection:
            result = connection.execute(query)
            df = pd.DataFrame(result.fetchall(), columns=[col.lower().strip() for col in result.keys()])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df
