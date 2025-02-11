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
from app.ui.risk_parameters import RiskManagementPanel
from app.database import DatabaseManager
from app.executor import TradeExecutor
from app.controllers.signal_controller import SignalController

# Load Bitget API credentials
API_KEY = os.getenv("BITGET_API_KEY")
API_SECRET = os.getenv("BITGET_API_SECRET")
API_PASSPHRASE = os.getenv("BITGET_API_PASSPHRASE")


class SignalUpdater(QThread):
    """Threaded class for handling background signal updates."""
    finished = pyqtSignal()  

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


from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QGroupBox, QWidget

class TickerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ticker Viewer")
        self.resize(1400, 1000)

        # Initialize components (as before)
        self.db_manager = DatabaseManager()
        self.trade_executor = TradeExecutor(API_KEY, API_SECRET, API_PASSPHRASE)
        self.plot_canvas = PlotCanvas(self.db_manager)
        self.signal_controller = SignalController(self.db_manager, self.plot_canvas)
        self.signal_management = SignalManagementPanel(self.db_manager, self.signal_controller)
        self.risk_management = RiskManagementPanel(self.db_manager)
        self.orders_panel = OrdersPanel(self.db_manager, self.trade_executor, self)
        self.portfolio_panel = PortfolioPanel(self.trade_executor, self.db_manager)
        self.tickers_panel = TickersPanel(self.db_manager, self.plot_canvas, self.signal_management, self.orders_panel, self.risk_management)

        # Create group boxes for a clear visual grouping
        tickers_group = QGroupBox("Tickers")
        tickers_group.setLayout(self.tickers_panel.layout)

        signal_group = QGroupBox("Signal Parameters")
        signal_group.setLayout(self.signal_management.layout)

        risk_group = QGroupBox("Risk Parameters")
        risk_group.setLayout(self.risk_management.layout)

        orders_group = QGroupBox("Manual Orders")
        orders_group.setLayout(self.orders_panel.layout)

        portfolio_group = QGroupBox("Portfolio")
        portfolio_group.setLayout(self.portfolio_panel.layout)

        # Create left sidebar (for tickers, signals, and risk)
        left_layout = QVBoxLayout()
        left_layout.addWidget(tickers_group)
        left_layout.addWidget(signal_group)
        left_layout.addWidget(risk_group)
        left_layout.addStretch()  # Push content to the top

        # Create right sidebar (for orders and portfolio)
        right_layout = QVBoxLayout()
        right_layout.addWidget(orders_group)
        right_layout.addWidget(portfolio_group)
        right_layout.addStretch()

        # Create central area for the plot canvas
        center_layout = QVBoxLayout()
        center_layout.addWidget(self.plot_canvas)

        # Assemble the main layout using an HBox to separate the three regions
        main_hlayout = QHBoxLayout()
        main_hlayout.addLayout(left_layout, stretch=1)
        main_hlayout.addLayout(center_layout, stretch=2)
        main_hlayout.addLayout(right_layout, stretch=1)

        # Create a main vertical layout to add a status bar at the bottom
        main_vlayout = QVBoxLayout()
        main_vlayout.addLayout(main_hlayout)
        self.status_label = QLabel("System Status: Idle | Last Updated: Not Yet Updated")
        self.status_label.setStyleSheet("font-weight: bold; color: green;")
        main_vlayout.addWidget(self.status_label)

        # Set central widget with the main vertical layout
        central_widget = QWidget(self)
        central_widget.setLayout(main_vlayout)
        self.setCentralWidget(central_widget)

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
