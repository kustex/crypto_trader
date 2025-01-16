import re
import sys
import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QTableWidget, QTableWidgetItem,
    QWidget, QLabel, QLineEdit, QPushButton, QGridLayout, QMessageBox
)
from PyQt6.QtCore import QTimer, QDateTime, Qt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
from app.database import DatabaseManager
from app.signals import SignalGenerator


class PlotCanvas(FigureCanvas):
    def __init__(self, parent=None, width=10, height=6, dpi=100):
        self.fig, self.axs = plt.subplots(2, 1, figsize=(width, height), dpi=dpi)
        super().__init__(self.fig)
        self.setParent(parent)

    def plot_data(self, df, symbol, timeframe):
        """
        Plot price with Keltner Channels and RVI with buy/sell annotations.
        """
        if df.empty:
            self.axs[0].clear()
            self.axs[1].clear()
            self.axs[0].text(0.5, 0.5, "No Data Available", ha="center", va="center")
            self.axs[1].text(0.5, 0.5, "No Data Available", ha="center", va="center")
            self.draw()
            return

        # Plot price with Keltner Channels
        self.axs[0].clear()
        self.axs[0].plot(df["timestamp"], df["close"], label="Price", color="blue")
        self.axs[0].plot(df["timestamp"], df["keltner_upper"], label="Keltner Upper", color="green", linestyle="--")
        self.axs[0].plot(df["timestamp"], df["keltner_lower"], label="Keltner Lower", color="red", linestyle="--")

        # Annotate buy and sell signals
        buy_signals = df[df["final_signal"] == 1]
        sell_signals = df[df["final_signal"] == -1]

        self.axs[0].scatter(buy_signals["timestamp"], buy_signals["close"], color="green", label="Buy Signal", marker="^")
        self.axs[0].scatter(sell_signals["timestamp"], sell_signals["close"], color="red", label="Sell Signal", marker="v")

        self.axs[0].set_title(f"{symbol} ({timeframe}) - Price and Keltner Channels")
        self.axs[0].legend()
        self.axs[0].set_ylabel("Price")

        # Plot RVI
        self.axs[1].clear()
        self.axs[1].plot(df["timestamp"], df["rvi"], label="RVI", color="purple")
        self.axs[1].axhline(y=0, color="black", linestyle="--", linewidth=0.8)
        self.axs[1].set_title("Relative Vigor Index (RVI)")
        self.axs[1].set_ylabel("RVI")
        self.axs[1].legend()

        self.fig.tight_layout()
        self.draw()

class TickerApp(QMainWindow):
    def __init__(self):
        super().__init__()

        # Database manager instance
        self.db_manager = DatabaseManager(db_path="data/crypto_data.db")

        # Main widget and layout
        self.setWindowTitle("Ticker Viewer")
        self.resize(1400, 800)
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)

        # Main grid layout
        main_layout = QGridLayout(central_widget)

        # Left column (Ticker List, Timeframe Buttons, Parameter Settings, Portfolio Risk Management)
        left_layout = QVBoxLayout()

        # Ticker List + Add/Remove Options
        ticker_layout = QVBoxLayout()
        ticker_label = QLabel("Tickers")
        ticker_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        self.ticker_table = QTableWidget()
        self.ticker_table.setColumnCount(1)
        self.ticker_table.setHorizontalHeaderLabels(["Ticker"])
        self.ticker_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.ticker_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.ticker_table.itemSelectionChanged.connect(self.on_ticker_selected)

        # Ticker management (Add/Remove)
        ticker_management_layout = QVBoxLayout()
        self.ticker_input = QLineEdit()
        self.ticker_input.setPlaceholderText("Enter ticker (e.g., BTC/USDT)")
        self.add_ticker_button = QPushButton("Add Ticker")
        self.add_ticker_button.clicked.connect(self.add_ticker)
        self.remove_ticker_button = QPushButton("Remove Selected Ticker")
        self.remove_ticker_button.clicked.connect(self.remove_selected_ticker)
        ticker_management_layout.addWidget(self.ticker_input)
        ticker_management_layout.addWidget(self.add_ticker_button)
        ticker_management_layout.addWidget(self.remove_ticker_button)

        ticker_layout.addWidget(ticker_label)
        ticker_layout.addWidget(self.ticker_table)
        ticker_layout.addLayout(ticker_management_layout)

        # Timeframe Buttons
        timeframe_layout = QVBoxLayout()
        timeframe_label = QLabel("Select Timeframe:")
        timeframe_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        timeframe_layout.addWidget(timeframe_label)
        self.setup_timeframe_buttons(timeframe_layout)  # Use existing method to set up buttons

        # Parameter Settings
        param_layout = QVBoxLayout()
        param_label = QLabel("Parameter Settings")
        param_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        self.param_grid = QGridLayout()
        self.param_labels = []
        self.param_inputs = []

        save_params_button = QPushButton("Save Parameters")
        save_params_button.clicked.connect(self.save_parameters)

        param_layout.addWidget(param_label)
        param_layout.addLayout(self.param_grid)
        param_layout.addWidget(save_params_button)

        # Portfolio Risk Management
        risk_layout = QVBoxLayout()
        risk_label = QLabel("Portfolio Risk Management")
        risk_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        self.risk_grid = QGridLayout()
        self.risk_labels = []
        self.risk_inputs = []

        # Risk management options
        risk_options = [
            "Stoploss (%)", 
            "Position Size (%)", 
            "Max Allocation (%)", 
            "Partial Sell Fraction"
        ]

        for i, label_text in enumerate(risk_options):
            label = QLabel(label_text)
            input_field = QLineEdit()
            self.risk_grid.addWidget(label, i, 0)
            self.risk_grid.addWidget(input_field, i, 1)
            self.risk_labels.append(label)
            self.risk_inputs.append(input_field)

        save_risk_button = QPushButton("Save Risk Settings")
        save_risk_button.clicked.connect(self.save_risk_settings)

        risk_layout.addWidget(risk_label)
        risk_layout.addLayout(self.risk_grid)
        risk_layout.addWidget(save_risk_button)

        # Add ticker, timeframe, parameter, and risk sections to the left layout
        left_layout.addLayout(ticker_layout)
        left_layout.addLayout(timeframe_layout)  # Add timeframe buttons below ticker list
        left_layout.addLayout(param_layout)
        left_layout.addLayout(risk_layout)  # Add Portfolio Risk Management section

        # Right column (Plot)
        right_layout = QVBoxLayout()
        plot_label = QLabel("Price and Indicators")
        plot_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        plot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot_canvas = PlotCanvas()

        right_layout.addWidget(plot_label)
        right_layout.addWidget(self.plot_canvas)

        # Status Label
        self.status_label = QLabel("System Status: Idle | Last Updated: Not Yet Updated")
        self.status_label.setStyleSheet("font-weight: bold; color: green;")
        right_layout.addWidget(self.status_label)

        # Add spacers for better alignment
        right_layout.addStretch()

        # Add to main grid layout
        main_layout.addLayout(left_layout, 0, 0)  # Left column
        main_layout.addLayout(right_layout, 0, 1)  # Right column
        main_layout.setColumnStretch(0, 1)  # Left column stretch
        main_layout.setColumnStretch(1, 3)  # Right column stretch

        # Timer for periodic updates
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_data)
        self.timer.start(60 * 1000)  # Refresh every 60 seconds

        # Initialize app with default data
        self.current_symbol = None
        self.current_timeframe = "1h"  # Default to 1h timeframe
        self.load_tickers()

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
            QMessageBox.warning(self, "Invalid Ticker", "The ticker must be in the format AAA/BBB (e.g., BTC/USDT).")
            return

        try:
            self.db_manager.insert_ticker(ticker)
            QMessageBox.information(self, "Success", f"The ticker {ticker} has been added.")
            self.load_tickers()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add ticker: {e}")

    def remove_selected_ticker(self):
        """
        Remove the selected ticker from the database and refresh the table.
        """
        selected_items = self.ticker_table.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "No Selection", "Please select a ticker to remove.")
            return

        ticker = selected_items[0].text()
        try:
            self.db_manager.remove_ticker(ticker)
            QMessageBox.information(self, "Success", f"The ticker {ticker} has been removed.")
            self.load_tickers()  # Refresh the ticker list
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to remove ticker: {e}")


    def setup_timeframe_buttons(self, layout):
        """
        Add buttons to select timeframe and refresh the graphs/parameters.
        """
        self.timeframe_buttons = {
            "1h": QPushButton("1h"),
            "1d": QPushButton("1d")
        }

        for timeframe, button in self.timeframe_buttons.items():
            button.clicked.connect(lambda checked, tf=timeframe: self.display_graph_with_timeframe(tf))
            layout.addWidget(button)

    def load_tickers(self):
        """
        Load unique tickers from the database and set up a default selection.
        """
        tickers = self.db_manager.fetch_tickers()

        self.ticker_table.setRowCount(len(tickers))
        for i, symbol in enumerate(tickers["symbol"]):
            self.ticker_table.setItem(i, 0, QTableWidgetItem(symbol))

        if len(tickers) > 0:
            # Select the first row by default
            self.ticker_table.selectRow(0)
            self.current_symbol = tickers["symbol"].iloc[0]
            self.display_graph_with_timeframe("1h") # Automatically display the 1h timeframe for the first ticker

    def on_ticker_selected(self):
        """
        Handle ticker selection and default to 1h timeframe.
        Also load portfolio risk parameters for the selected ticker.
        """
        selected_items = self.ticker_table.selectedItems()
        if not selected_items:
            return

        self.current_symbol = selected_items[0].text()
        self.display_graph_with_timeframe("1h")  # Automatically show the 1h timeframe when a ticker is selected

        # Load portfolio risk parameters for the selected ticker
        risk_params = self.db_manager.fetch_risk_params(self.current_symbol)
        if not risk_params:
            print(f"No risk parameters found for {self.current_symbol}. Using default values.")
            risk_params = [10.0, 5.0, 20.0, 0.5]  # Default values for stoploss, position size, max allocation, and partial sell fraction

        # Populate the Portfolio Risk Management inputs
        for input_field, value in zip(self.risk_inputs, risk_params):
            input_field.setText(str(value))


    def display_graph_with_timeframe(self, timeframe):
        """
        Display the graph and parameters for the selected ticker and timeframe.
        """
        if not self.current_symbol:
            return

        self.current_timeframe = timeframe

        # Clear previous parameter inputs
        for widget in self.param_labels + self.param_inputs:
            self.param_grid.removeWidget(widget)
            widget.deleteLater()
        self.param_labels.clear()
        self.param_inputs.clear()

        # Fetch parameters from the database
        params = self.db_manager.fetch_indicator_params(self.current_symbol, self.current_timeframe)
        if not params:
            print(f"No parameters found for {self.current_symbol} ({self.current_timeframe}).")
            return

        param_names = [
            "Keltner Period", "Keltner Multiplier", "RVI Period",
            "RVI Lower Threshold", "RVI Upper Threshold"
        ]
        for i, (name, value) in enumerate(zip(param_names, params)):
            label = QLabel(name)
            input_field = QLineEdit(str(value))
            self.param_grid.addWidget(label, i, 0)
            self.param_grid.addWidget(input_field, i, 1)
            self.param_labels.append(label)
            self.param_inputs.append(input_field)

        self.refresh_data()

    def save_risk_settings(self):
        """
        Save the updated portfolio risk parameters for the selected ticker.
        """
        if not self.current_symbol:
            QMessageBox.warning(self, "No Ticker Selected", "Please select a ticker before saving risk settings.")
            return

        try:
            # Extract values from the risk inputs
            risk_values = [float(input_field.text()) for input_field in self.risk_inputs]
            self.db_manager.save_risk_params(
                symbol=self.current_symbol,
                stoploss=risk_values[0],
                position_size=risk_values[1],
                max_allocation=risk_values[2],
                partial_sell_fraction=risk_values[3]
            )
            QMessageBox.information(self, "Success", f"Risk settings saved for {self.current_symbol}.")
        except ValueError:
            QMessageBox.critical(self, "Error", "Invalid input in risk settings fields.")

    def save_parameters(self):
        """
        Save the updated parameters for the selected ticker and regenerate signals.
        """
        if not self.current_symbol or not self.current_timeframe:
            return

        try:
            params = [float(input_field.text()) for input_field in self.param_inputs]
            self.db_manager.save_indicator_params(
                self.current_symbol, self.current_timeframe,
                params[0], params[1], params[2], params[3], params[4]
            )
            self.update_status_label("Parameters Saved. Regenerating Signals...", QDateTime.currentDateTime())
            self.regenerate_signals_and_refresh()
            print(f"Parameters saved and signals regenerated for {self.current_symbol} ({self.current_timeframe}).")
        except ValueError:
            print("Invalid input in parameter fields.")

    def regenerate_signals_and_refresh(self):
        """
        Regenerate signals using the updated parameters and refresh the graph.
        """
        df = self.db_manager.query_data(self.current_symbol, self.current_timeframe)
        if df.empty:
            print(f"No data available for {self.current_symbol} ({self.current_timeframe}). Skipping signal regeneration.")
            return

        params = self.db_manager.fetch_indicator_params(self.current_symbol, self.current_timeframe)
        keltner_params = {"period": params[0], "multiplier": params[1]}
        rvi_params = {"period": params[2], "thresholds": {"lower": params[3], "upper": params[4]}}

        signal_generator = SignalGenerator(db_manager=self.db_manager)
        final_signals = signal_generator.generate_signals(df, keltner_params=keltner_params, rvi_params=rvi_params)

        self.db_manager.save_signals_to_db(final_signals)
        self.update_status_label("Signals Regenerated and Display Updated", QDateTime.currentDateTime())

        self.refresh_data()

    def refresh_data(self):
        """
        Refresh the data for the currently selected ticker and timeframe.
        """
        if not self.current_symbol or not self.current_timeframe:
            self.update_status_label("No Ticker Selected", last_updated=None)
            return

        lookback_days = 30 if self.current_timeframe == "1h" else 180

        query = f"""
            SELECT h.timestamp, h.close, h.open, h.high, h.low, h.volume,
                s.keltner_upper, s.keltner_lower, s.rvi, s.keltner_signal, 
                s.rvi_signal, s.final_signal
            FROM historical_data h
            LEFT JOIN signals_data s
            ON h.timestamp = s.timestamp AND h.symbol = s.symbol AND h.timeframe = s.timeframe
            WHERE h.symbol = '{self.current_symbol}' AND h.timeframe = '{self.current_timeframe}'
            AND h.timestamp >= datetime('now', '-{lookback_days} days')
            ORDER BY h.timestamp ASC
        """
        try:
            with self.db_manager.engine.connect() as connection:
                df = pd.read_sql(query, connection)

            if df.empty:
                self.update_status_label(f"No Data Available for {self.current_symbol} ({self.current_timeframe})")
                print(f"No data available for {self.current_symbol} ({self.current_timeframe}).")
                return

            df["timestamp"] = pd.to_datetime(df["timestamp"])
            self.plot_canvas.plot_data(df, self.current_symbol, self.current_timeframe)

            # Update the status label with success
            self.update_status_label("Data Refreshed Successfully", QDateTime.currentDateTime())

        except Exception as e:
            # Handle errors and update status label
            self.update_status_label(f"Error: {str(e)}")
            print(f"Error while refreshing data: {e}")


    def update_status_label(self, status, last_updated=None):
        """
        Update the system status label with the current status and last update time.
        """
        last_updated_str = last_updated.toString("yyyy-MM-dd HH:mm") if last_updated else "Not Yet Updated"
        self.status_label.setText(f"System Status: {status} | Last Updated: {last_updated_str}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TickerApp()
    window.show()
    sys.exit(app.exec())


