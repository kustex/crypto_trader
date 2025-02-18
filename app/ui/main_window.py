import os
import pandas as pd
from datetime import datetime
from PyQt6.QtWidgets import (
    QMainWindow, QVBoxLayout, QWidget, QGridLayout, QLabel, QPushButton, QTabWidget, QLineEdit
)
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QGroupBox, QWidget
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
from app.ui.api_credentials import load_api_credentials, save_api_credentials
from app.ui.backtest_panel import BacktestPanel
from datetime import timezone, timedelta

API_KEY, API_SECRET, API_PASSPHRASE = load_api_credentials()
LOCAL_TZ = timezone(timedelta(hours=1))


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
                    self.active_updates.remove((symbol, timeframe))  

        print("✅ Signal updates completed.")
        self.finished.emit()

class TickerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ticker Viewer")
        self.resize(1400, 1000)

        # Initialize database & trading components
        self.db_manager = DatabaseManager()
        self.trade_executor = TradeExecutor(API_KEY, API_SECRET, API_PASSPHRASE)
        self.plot_canvas = PlotCanvas(self.db_manager)
        self.signal_controller = SignalController(self.db_manager, self.plot_canvas)
        self.signal_management = SignalManagementPanel(self.db_manager, self.signal_controller)
        self.risk_management = RiskManagementPanel(self.db_manager)
        self.orders_panel = OrdersPanel(self.db_manager, self.trade_executor, self)
        self.portfolio_panel = PortfolioPanel(self.trade_executor, self.db_manager)
        self.tickers_panel = TickersPanel(self.db_manager, self.plot_canvas, self.signal_management, self.orders_panel, self.risk_management, self.trade_executor)
        self.backtest_widget = BacktestPanel()

        # Create tab interface
        self.tabs = QTabWidget(self)
        self.main_widget = QWidget()
        self.settings_widget = QWidget()

        # Set up UI components
        self.setup_main_ui()
        self.setup_settings_ui()

        # Add tabs
        self.tabs.addTab(self.main_widget, "Dashboard")
        self.tabs.addTab(self.backtest_widget, "Backtester")
        self.tabs.addTab(self.settings_widget, "Settings")

        # Set central widget with tabs
        self.setCentralWidget(self.tabs)

        # UI Timer for auto-updates
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self.update_ui)
        self.ui_timer.start(60 * 1000)

        # Load initial tickers
        self.initialize_tickers()

    def setup_main_ui(self):
        """Set up the main dashboard UI."""
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

        # Left Sidebar
        left_layout = QVBoxLayout()
        left_layout.addWidget(tickers_group)
        left_layout.addWidget(signal_group)
        left_layout.addWidget(risk_group)
        left_layout.addStretch()

        # Right Sidebar
        right_layout = QVBoxLayout()
        right_layout.addWidget(orders_group)
        right_layout.addWidget(portfolio_group)
        right_layout.addStretch()

        # Center (Graph)
        center_layout = QVBoxLayout()
        center_layout.addWidget(self.plot_canvas)

        # Combine all layouts
        main_hlayout = QHBoxLayout()
        main_hlayout.addLayout(left_layout, stretch=1)
        main_hlayout.addLayout(center_layout, stretch=2)
        main_hlayout.addLayout(right_layout, stretch=1)

        # Main Layout
        main_vlayout = QVBoxLayout()
        main_vlayout.addLayout(main_hlayout)
        self.status_label = QLabel("System Status: Idle | Last Updated: Not Yet Updated")
        self.status_label.setStyleSheet("font-weight: bold; color: green;")
        main_vlayout.addWidget(self.status_label)

        self.main_widget.setLayout(main_vlayout)

    def setup_settings_ui(self):
        """Set up the settings tab for API credentials."""
        layout = QVBoxLayout()

        # Input Fields
        self.api_key_input = QLineEdit()
        self.api_secret_input = QLineEdit()
        self.api_passphrase_input = QLineEdit()

        self.api_key_input.setPlaceholderText("Enter Bitget API Key")
        self.api_secret_input.setPlaceholderText("Enter Bitget API Secret")
        self.api_passphrase_input.setPlaceholderText("Enter Bitget API Passphrase")

        # Pre-fill with existing credentials
        self.api_key_input.setText(API_KEY)
        self.api_secret_input.setText(API_SECRET)
        self.api_passphrase_input.setText(API_PASSPHRASE)

        # Save button
        self.save_button = QPushButton("Save API Credentials")
        self.save_button.clicked.connect(self.save_api_credentials)

        # Grid layout
        grid = QGridLayout()
        grid.addWidget(QLabel("API Key:"), 0, 0)
        grid.addWidget(self.api_key_input, 0, 1)
        grid.addWidget(QLabel("API Secret:"), 1, 0)
        grid.addWidget(self.api_secret_input, 1, 1)
        grid.addWidget(QLabel("API Passphrase:"), 2, 0)
        grid.addWidget(self.api_passphrase_input, 2, 1)
        grid.addWidget(self.save_button, 3, 0, 1, 2)

        layout.addLayout(grid)
        self.settings_widget.setLayout(layout)

    def save_api_credentials(self):
        """Save API credentials."""
        save_api_credentials(self.api_key_input.text(), self.api_secret_input.text(), self.api_passphrase_input.text())

    def update_ui(self):
        """
        Called every minute (by the QTimer) or by the notifier.
        Updates:
        - Portfolio panels (open positions, closed orders, completed trades)
        - Graph (via plot_canvas) using the currently selected ticker and timeframe
        - Tickers table with current live prices and 24h % change
        - Status label with current timestamp.
        """
        # Update portfolio-related panels.
        self.portfolio_panel.update_open_positions()
        self.portfolio_panel.update_closed_orders()
        self.portfolio_panel.update_completed_trades()
        self.portfolio_panel.update_account_balance()

        # Update the graph if a ticker is selected.
        if self.tickers_panel.current_symbol:
            self.tickers_panel.display_graph_with_timeframe("1h")

        # Refresh the tickers table (which now uses live prices).
        self.tickers_panel.load_tickers()

        self.status_label.setText(
            f"System Status: Updated at {datetime.now(LOCAL_TZ).strftime('%Y-%m-%d %H:%M:%S')}"
        )

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
