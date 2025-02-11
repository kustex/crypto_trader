import os
import pandas as pd
from PyQt6.QtWidgets import (
    QMainWindow, QVBoxLayout, QWidget, QGridLayout, QLabel, QPushButton
)
from PyQt6.QtCore import QTimer, QThread, pyqtSignal, QDateTime
from app.ui.plot_canvas import PlotCanvas
from app.ui.orders_panel import OrdersPanel
from app.ui.tickers_panel import TickersPanel
from app.ui.signal_parameters import SignalManagementPanel
from app.ui.portfolio_panel import PortfolioPanel  
from app.database import DatabaseManager
from app.executor import TradeExecutor
from app.controllers.signal_controller import SignalController

# Load Bitget API credentials
API_KEY = os.getenv("BITGET_API_KEY")
API_SECRET = os.getenv("BITGET_API_SECRET")
API_PASSPHRASE = os.getenv("BITGET_API_PASSPHRASE")


class SignalUpdater(QThread):
    """Threaded class for handling background signal updates."""
    finished = pyqtSignal()  # Signal emitted when all updates are done

    def __init__(self, db_manager: DatabaseManager, signal_controller: SignalController):
        super().__init__()
        self.db_manager = db_manager
        self.signal_controller = signal_controller
        self.active_updates = set()  

    def run(self):
        """Run signal updates for all available symbols."""
        print("🔄 Running background signal updates...")

        symbols = self.db_manager.fetch_tickers()
        tickers = symbols['symbol'].tolist()  
        for symbol in tickers:
            for timeframe in ["1h", "15m"]:
                if (symbol, timeframe) in self.active_updates:
                    print(f"⚠️ Skipping {symbol} ({timeframe}): Already updating...")
                    continue
                self.active_updates.add((symbol, timeframe))

                try:
                    query = f"""
                        SELECT timestamp, open, high, low, close, volume, symbol, timeframe
                        FROM historical_data
                        WHERE symbol = '{symbol}' AND timeframe = '{timeframe}'
                        ORDER BY timestamp ASC
                    """
                    with self.db_manager.engine.connect() as connection:
                        data = pd.read_sql(query, connection)
                    if data is not None and not data.empty:
                        self.signal_controller.regenerate_signals_and_refresh(symbol, timeframe)
                    else:
                        print(f"⚠️ No data available for {symbol} ({timeframe}). Skipping...")
                except Exception as e:
                    print(f"❌ Error updating signals for {symbol} ({timeframe}): {e}")
                finally:
                    self.active_updates.remove((symbol, timeframe))  # ✅ Ensure removal even on error

        print("✅ Signal updates completed.")
        self.finished.emit()


class TickerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ticker Viewer")
        self.resize(1400, 1000)

        # Initialize components
        self.db_manager = DatabaseManager()
        self.trade_executor = TradeExecutor(API_KEY, API_SECRET, API_PASSPHRASE)
        self.plot_canvas = PlotCanvas(self.db_manager)
        self.signal_controller = SignalController(self.db_manager, self.plot_canvas)
        self.signal_management = SignalManagementPanel(self.db_manager, self.signal_controller)
        self.orders_panel = OrdersPanel(self.db_manager, self.trade_executor, self)
        self.portfolio_panel = PortfolioPanel(self.trade_executor, self.db_manager)
        self.tickers_panel = TickersPanel(self.db_manager, self.plot_canvas, self.signal_management, self.orders_panel)

        # UI Layouts
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QGridLayout(central_widget)
        main_layout.addLayout(self.tickers_panel.layout, 0, 0)
        main_layout.addLayout(self.signal_management.layout, 1, 0)
        main_layout.addLayout(self.orders_panel.layout, 0, 1)
        main_layout.addWidget(self.portfolio_panel, 1, 1)
        main_layout.addWidget(self.plot_canvas, 0, 2, 2, 1)

        # Status Label
        self.status_label = QLabel("System Status: Idle | Last Updated: Not Yet Updated")
        self.status_label.setStyleSheet("font-weight: bold; color: green;")
        main_layout.addWidget(self.status_label, 2, 0, 1, 3)

        # ✅ Persistent SignalUpdater instance
        # self.signal_updater = SignalUpdater(self.db_manager, self.signal_controller)
        # self.signal_updater.finished.connect(self.on_refresh_complete)

        # # Timer for automatic refresh
        # self.refresh_timer = QTimer(self)
        # self.refresh_timer.timeout.connect(self.refresh_application)
        # self.refresh_timer.start(60000 * 5)  

        # Load initial tickers
        self.initialize_tickers()

    def refresh_application(self):
        """Refresh all symbols and update the UI every minute."""
        print("🔄 Refreshing application...")

        # ✅ Step 1: Update Portfolio Data
        self.update_portfolio()

        # ✅ Step 2: Start background signal update if not already running
        if not self.signal_updater.isRunning():
            self.signal_updater.start()
        else:
            print("⚠️ SignalUpdater is already running, skipping duplicate execution.")

    def on_refresh_complete(self):
        """Update UI after background refresh is complete."""
        self.status_label.setText(f"System Status: Updated | Last Updated: {QDateTime.currentDateTime().toString('yyyy-MM-dd HH:mm:ss')}")
        print("✅ Application refresh completed.")

    def update_portfolio(self):
        """Update portfolio panel after a trade is executed."""
        self.portfolio_panel.update_closed_orders()
        self.portfolio_panel.update_completed_trades()
        self.portfolio_panel.update_open_positions()

    def initialize_tickers(self):
        """Load tickers at application startup and display the first ticker's graph."""
        self.tickers_panel.load_tickers()

        # Automatically display the first ticker's graph
        if self.tickers_panel.current_symbol:
            self.tickers_panel.display_graph_with_timeframe("1h")
