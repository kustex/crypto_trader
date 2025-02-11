import re
from PyQt6.QtWidgets import QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QPushButton, QMessageBox, QLineEdit
from app.ui.plot_canvas import PlotCanvas
from app.database import DatabaseManager
from app.ui.signal_parameters import SignalManagementPanel
from app.ui.orders_panel import OrdersPanel

class TickersPanel:
    def __init__(self, db_manager: DatabaseManager, plot_canvas: PlotCanvas, signal_panel: SignalManagementPanel, orders_panel: OrdersPanel):
        self.db_manager = db_manager
        self.plot_canvas = plot_canvas  
        self.signal_panel = signal_panel 
        self.orders_panel = orders_panel  

        # UI Elements
        self.layout = QVBoxLayout()
        self.ticker_label = QLabel("Tickers")
        self.ticker_table = QTableWidget()
        self.ticker_table.setColumnCount(3)
        self.ticker_table.setHorizontalHeaderLabels(["Ticker", "Last Price", "24h % Change"])
        self.ticker_table.itemSelectionChanged.connect(self.on_ticker_selected) 

                # Input for adding tickers
        self.ticker_input = QLineEdit()
        self.ticker_input.setPlaceholderText("Enter ticker (e.g., BTC/USDT)")

        self.add_ticker_button = QPushButton("Add Ticker")
        self.add_ticker_button.clicked.connect(self.add_ticker)

        self.remove_ticker_button = QPushButton("Remove Selected Ticker")
        self.remove_ticker_button.clicked.connect(self.remove_selected_ticker)

        # Add elements to layout
        self.layout.addWidget(self.ticker_label)
        self.layout.addWidget(self.ticker_table)
        self.layout.addWidget(self.ticker_input)
        self.layout.addWidget(self.add_ticker_button)
        self.layout.addWidget(self.remove_ticker_button)

        self.current_symbol = None
        self.current_timeframe = "1h"

    def validate_ticker(self, ticker):
        """
        Validate if the ticker is in the correct format (e.g., BTC/USDT).
        """
        pattern = re.compile(r"^[A-Z]{3,5}/[A-Z]{3,5}$")
        return pattern.match(ticker)

    def add_ticker(self):
        """
        Add a new ticker to the database and refresh the table.
        """
        ticker = self.ticker_input.text().strip().upper()
        if not self.validate_ticker(ticker):
            QMessageBox.warning(None, "Invalid Ticker", "The ticker must be in the format AAA/BBB (e.g., BTC/USDT).")
            return

        try:
            self.db_manager.insert_ticker(ticker)
            QMessageBox.information(None, "Success", f"The ticker {ticker} has been added.")
            self.load_tickers()
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Failed to add ticker: {e}")

    def remove_selected_ticker(self):
        """
        Remove the selected ticker from the database and refresh the table.
        """
        selected_items = self.ticker_table.selectedItems()
        if not selected_items:
            QMessageBox.warning(None, "No Selection", "Please select a ticker to remove.")
            return

        ticker = selected_items[0].text()
        try:
            self.db_manager.remove_ticker(ticker)
            QMessageBox.information(None, "Success", f"The ticker {ticker} has been removed.")
            self.load_tickers()  
        except Exception as e:
            QMessageBox.critical(None, "Error", f"Failed to remove ticker: {e}")

    def load_tickers(self):
        """
        Load unique tickers from the database and set up a default selection.
        """
        tickers = self.db_manager.fetch_tickers()

        self.ticker_table.setRowCount(len(tickers))
        for i, symbol in enumerate(tickers["symbol"]):
            last_price = self.get_last_price(symbol)
            change_24h = self.calculate_24h_change(symbol)

            self.ticker_table.setItem(i, 0, QTableWidgetItem(symbol))
            self.ticker_table.setItem(i, 1, QTableWidgetItem(f"{last_price:.2f}" if last_price else "N/A"))
            self.ticker_table.setItem(i, 2, QTableWidgetItem(f"{change_24h:.2f}%" if change_24h else "N/A"))

        if len(tickers) > 0:
            self.ticker_table.selectRow(0)
            self.current_symbol = tickers["symbol"].iloc[0]
            self.display_graph_with_timeframe("1h")  

    def get_last_price(self, ticker):
        """
        Fetch the last price for the given ticker from the database.
        """
        return self.db_manager.get_latest_intraday_price(ticker)

    def calculate_24h_change(self, ticker):
        """
        Calculate the 24-hour percentage change for the given ticker.
        """
        prices = self.db_manager.get_prices_for_last_24h(ticker)
        if prices and len(prices) >= 2:
            latest_price = prices[-1]
            oldest_price = prices[0]
            return ((latest_price - oldest_price) / oldest_price) * 100
        return None

    def on_ticker_selected(self):
        """
        Handles ticker selection and delegates updates to other panels.
        """
        selected_items = self.ticker_table.selectedItems()
        if not selected_items:
            return

        self.current_symbol = selected_items[0].text()
        self.current_timeframe = "1h"  

        self.display_graph_with_timeframe(self.current_timeframe)  
        self.signal_panel.update_parameters(self.current_symbol, self.current_timeframe)  
        self.orders_panel.reset_order_inputs(self.current_symbol) 

    def display_graph_with_timeframe(self, timeframe):
        """
        Display the graph and parameters for the selected ticker and timeframe.
        """
        if not self.current_symbol:
            return

        self.current_timeframe = timeframe
        self.signal_panel.update_parameters(self.current_symbol, self.current_timeframe)
        params = self.db_manager.fetch_indicator_params(self.current_symbol, self.current_timeframe)
        if not params:
            print(f"No parameters found for {self.current_symbol} ({self.current_timeframe}).")
            return

        include_15m_rvi = bool(params[5])

        self.plot_canvas.plot_data(
            symbol=self.current_symbol,
            timeframe=self.current_timeframe,
            include_15m_rvi=include_15m_rvi
        )

    def load_tickers(self):
        """
        Load unique tickers from the database and set up a default selection.
        """
        tickers = self.db_manager.fetch_tickers()

        self.ticker_table.setRowCount(len(tickers))
        for i, symbol in enumerate(tickers["symbol"]):
            last_price = self.get_last_price(symbol)
            change_24h = self.calculate_24h_change(symbol)

            self.ticker_table.setItem(i, 0, QTableWidgetItem(symbol))
            self.ticker_table.setItem(i, 1, QTableWidgetItem(f"{last_price:.2f}" if last_price else "N/A"))
            self.ticker_table.setItem(i, 2, QTableWidgetItem(f"{change_24h:.2f}%" if change_24h else "N/A"))

        if len(tickers) > 0:
            self.ticker_table.selectRow(0)
            self.current_symbol = tickers["symbol"].iloc[0] 
