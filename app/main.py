import os
import re
import sys
import pandas as pd
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QTableWidget, QTableWidgetItem, QSizePolicy, QCheckBox,
    QWidget, QLabel, QLineEdit, QPushButton, QGridLayout, QMessageBox, QDoubleSpinBox, QSpacerItem, QSpacerItem, QComboBox 
)
from PyQt6.QtCore import QTimer, QDateTime, Qt, QThread, pyqtSignal
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
import matplotlib.pyplot as plt
from app.database import DatabaseManager
from app.signals import SignalGenerator
from app.executor import TradeExecutor
from app.gui import BITGET_QSS

class BackgroundWorker(QThread):
    data_ready_signal = pyqtSignal(object, str, str)  # Emit DataFrame, symbol, and timeframe
    progress_signal = pyqtSignal(str)  # Emit status messages

    def __init__(self, task, *args, **kwargs):
        super().__init__()
        self.task = task
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            # Run the task and unpack results
            result, symbol, timeframe = self.task(*self.args, **self.kwargs)
            if isinstance(result, pd.DataFrame):
                self.data_ready_signal.emit(result, symbol, timeframe)
            else:
                self.progress_signal.emit(result)
        except Exception as e:
            self.progress_signal.emit(f"Error: {str(e)}")


class PlotCanvas(FigureCanvas):
    def __init__(self, parent=None, width=10, height=10, dpi=100):
        self.fig, self.axs = plt.subplots(3, 1, figsize=(width, height), dpi=dpi)  # Three subplots
        super().__init__(self.fig)
        self.setParent(parent)

    def plot_data(self, df, symbol, timeframe):
        """
        Plot price with Keltner Channels and RVI, optionally including 15m RVI.
        """
        if df.empty:
            for ax in self.axs:
                ax.clear()
                ax.text(0.5, 0.5, "No Data Available", ha="center", va="center")
            self.draw()
            return

        # Determine date range dynamically based on timeframe
        max_date = df["timestamp"].max()
        lookback_period = pd.Timedelta(days=30) if timeframe == "1h" else pd.Timedelta(days=180)
        min_date = max_date - lookback_period

        # Filter DataFrame for the desired range
        df = df[df["timestamp"] >= min_date]

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

        # Plot 15m RVI if provided
        self.axs[2].clear()
        print(df.columns)
        if "rvi_15m" in df.columns:
            self.axs[2].plot(df["timestamp"], df["rvi_15m"], label="15m RVI", color="orange")
            self.axs[2].axhline(y=0, color="black", linestyle="--", linewidth=0.8)
            self.axs[2].set_title("15m RVI")
            self.axs[2].set_ylabel("RVI (15m)")
            self.axs[2].legend()
        else:
            self.axs[2].clear()
            self.axs[2].text(0.5, 0.5, "15m RVI not included", ha="center", va="center")

        self.fig.tight_layout()
        self.draw()


class TickerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.API_KEY = os.getenv("BITGET_API_KEY")
        self.API_SECRET = os.getenv("BITGET_API_SECRET")
        self.API_PASSPHRASE = os.getenv("BITGET_API_PASSPHRASE")

        # self.setStyleSheet(BITGET_QSS)

        # Instantiate TradeExecutor
        self.trade_executor = TradeExecutor(
            api_key=self.API_KEY,
            api_secret=self.API_SECRET,
            passphrase=self.API_PASSPHRASE,
            testnet=False
        )

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
        self.ticker_table.setColumnCount(3)
        self.ticker_table.setHorizontalHeaderLabels(["Ticker", "Last Price", "24h % Change"])
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

        self.save_params_button = QPushButton("Save Parameters")
        self.save_params_button.clicked.connect(self.save_parameters)

        self.include_15m_rvi_checkbox = QCheckBox("Include 15m RVI Condition")
        self.include_15m_rvi_checkbox.setChecked(True)  

        param_layout.addWidget(param_label)
        param_layout.addWidget(self.include_15m_rvi_checkbox)
        param_layout.addLayout(self.param_grid)
        param_layout.addWidget(self.save_params_button)

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

        # Manual Orders Section
        middle_layout = QVBoxLayout()

        order_label = QLabel("Manual Orders")
        order_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        middle_layout.addWidget(order_label)

        self.selected_ticker_label = QLabel("Selected Ticker: none")
        self.selected_ticker_label.setAlignment(Qt.AlignmentFlag.AlignLeft)

        # Buy and Sell Buttons
        self.buy_button = QPushButton("Buy")
        self.buy_button.setEnabled(False)
        self.buy_button.clicked.connect(self.buy_ticker)

        self.sell_button = QPushButton("Sell")
        self.sell_button.setEnabled(False)
        self.sell_button.clicked.connect(self.sell_ticker)

        # Order Type Combo Box
        self.order_type_combo = QComboBox()
        self.order_type_combo.addItems(["Market", "Limit"])
        self.order_type_combo.setEnabled(False)
        self.order_type_combo.currentIndexChanged.connect(self.on_order_type_changed)

        # Limit Price Input (Initially Hidden)
        self.limit_price_label = QLabel("Limit Price:")
        self.limit_price_input = QLineEdit()
        self.limit_price_input.setPlaceholderText("Enter limit price")
        self.limit_price_label.setVisible(False)
        self.limit_price_input.setVisible(False)

        # Order Amount
        self.order_amount_label = QLabel("Order Amount:")
        self.order_amount_input = QLineEdit()
        self.order_amount_input.setPlaceholderText("Enter number of shares")
        self.order_amount_input.setEnabled(False)
        self.order_amount_input.textChanged.connect(self.update_dollar_amount)

        # Dollar Amount
        self.dollar_amount_label = QLabel("Cash Amount:")
        self.dollar_amount_input = QLineEdit()
        self.dollar_amount_input.setPlaceholderText("Enter Amount in USD")
        self.dollar_amount_input.setEnabled(False)
        self.dollar_amount_input.textChanged.connect(self.update_order_amount)

        # Add Widgets to Middle Layout
        middle_layout.addWidget(self.selected_ticker_label)
        middle_layout.addWidget(self.order_type_combo)
        middle_layout.addWidget(self.limit_price_label)
        middle_layout.addWidget(self.limit_price_input)
        middle_layout.addWidget(self.buy_button)
        middle_layout.addWidget(self.sell_button)
        middle_layout.addWidget(self.order_amount_label)
        middle_layout.addWidget(self.order_amount_input)
        middle_layout.addWidget(self.dollar_amount_label)
        middle_layout.addWidget(self.dollar_amount_input)
        middle_layout.addStretch()

        # Right column (Plot)
        right_layout = QVBoxLayout()
        plot_label = QLabel("Price and Indicators")
        plot_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        plot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.plot_canvas = PlotCanvas()

        right_layout.addStretch(1)
        right_layout.addWidget(plot_label)
        right_layout.addWidget(self.plot_canvas)

        # Status Label
        self.status_label = QLabel("System Status: Idle | Last Updated: Not Yet Updated")
        self.status_label.setStyleSheet("font-weight: bold; color: green;")
        right_layout.addWidget(self.status_label)

        # Add a spacer to push the content to the top
        spacer = QSpacerItem(100, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        right_layout.addSpacerItem(spacer)

        # Add spacers for better alignment
        right_layout.addStretch()

        # Add to main grid layout
        main_layout.addLayout(left_layout, 0, 0)  # Left column
        main_layout.addLayout(middle_layout, 0, 1)  # Middle column
        main_layout.addLayout(right_layout, 0, 2)  # Right column

        # Adjust the main grid layout
        main_layout.setSpacing(15)  # Add more spacing between components for clarity
        main_layout.setContentsMargins(10, 10, 10, 10)  # Set margins around the layout

        # Update column stretches for better proportional space usage
        main_layout.setColumnStretch(0, 1)  # Left column (Tickers and management)
        main_layout.setColumnStretch(0, 1)  # Middle column (Manual Orders)
        main_layout.setColumnStretch(2, 5)  # Right column (Price and Indicators)

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
            last_price = self.get_last_price(symbol)
            change_24h = self.calculate_24h_change(symbol)

            self.ticker_table.setItem(i, 0, QTableWidgetItem(symbol))
            self.ticker_table.setItem(i, 1, QTableWidgetItem(f"{last_price:.2f}" if last_price else "N/A"))
            self.ticker_table.setItem(i, 2, QTableWidgetItem(f"{change_24h:.2f}%" if change_24h else "N/A"))

        if len(tickers) > 0:
            # Select the first row by default
            self.ticker_table.selectRow(0)
            self.current_symbol = tickers["symbol"].iloc[0]
            self.display_graph_with_timeframe("1h") # Automatically display the 1h timeframe for the first ticker

    def on_ticker_selected(self):
        """
        Handle ticker selection and reset order-related inputs.
        """
        selected_items = self.ticker_table.selectedItems()
        if not selected_items:
            return

        # Update the current symbol and load the graph
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

        # Reset order-related inputs
        self.selected_ticker = self.current_symbol
        self.selected_ticker_label.setText(f"Selected Ticker: {self.current_symbol}")
        self.order_type_combo.setCurrentIndex(0)  # Reset to "Market"
        self.limit_price_input.clear()  # Clear the limit price input
        self.limit_price_label.setVisible(False)  # Hide the limit price label
        self.limit_price_input.setVisible(False)  # Hide the limit price input
        self.order_amount_input.clear()  # Clear the order amount input
        self.dollar_amount_input.clear()  # Clear the dollar amount input

        # Enable the order input fields
        self.buy_button.setEnabled(True)
        self.sell_button.setEnabled(True)
        self.order_amount_input.setEnabled(True)
        self.dollar_amount_input.setEnabled(True)
        self.order_type_combo.setEnabled(True)

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
        for i, (name, value) in enumerate(zip(param_names, params[:-1])):  # Exclude include_15m_rvi from param inputs
            label = QLabel(name)
            input_field = QLineEdit(str(value))
            self.param_grid.addWidget(label, i, 0)
            self.param_grid.addWidget(input_field, i, 1)
            self.param_labels.append(label)
            self.param_inputs.append(input_field)

        # Set the state of the include_15m_rvi checkbox
        include_15m_rvi = bool(params[-1])  
        self.include_15m_rvi_checkbox.setChecked(include_15m_rvi)
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
            include_15m_rvi = int(self.include_15m_rvi_checkbox.isChecked())  

            self.db_manager.save_indicator_params(
                self.current_symbol, self.current_timeframe,
                params[0], params[1], params[2], params[3], params[4], include_15m_rvi
            )
            self.update_status_label("Parameters Saved. Regenerating Signals...", QDateTime.currentDateTime())
            self.regenerate_signals_and_refresh()
        except ValueError as e:
            print("Invalid input in parameter fields:", e)
            QMessageBox.warning(self, "Error", "Please enter valid numerical values.")

    def regenerate_signals_and_refresh(self):
        """
        Regenerate signals using the updated parameters and refresh the graph.
        """
        if not self.current_symbol or not self.current_timeframe:
            self.update_status_label("No Ticker Selected", QDateTime.currentDateTime())
            return

        def task():
            try:
                # Query the main DataFrame
                df = self.db_manager.query_data(self.current_symbol, self.current_timeframe)
                if df is None or df.empty:
                    print(f"No data available for {self.current_symbol} ({self.current_timeframe}).")
                    return None

                # Fetch indicator parameters
                params = self.db_manager.fetch_indicator_params(self.current_symbol, self.current_timeframe)
                if not params or len(params) < 6:
                    print(f"Invalid or missing parameters for {self.current_symbol} ({self.current_timeframe}): {params}")
                    return None

                keltner_params = {"period": params[0], "multiplier": params[1]}
                rvi_params = {"period": params[2], "thresholds": {"lower": params[3], "upper": params[4]}}
                include_15m_rvi = bool(params[5])

                # Query 15m data if necessary
                df_15m = None
                if include_15m_rvi:
                    df_15m = self.db_manager.query_data(self.current_symbol, "15m")
                    if df_15m is None or df_15m.empty:
                        print(f"Warning: 15m data unavailable for {self.current_symbol}. Proceeding without it.")
                        include_15m_rvi = False

                # Generate signals
                signal_generator = SignalGenerator(db_manager=self.db_manager)
                final_signals = signal_generator.generate_signals(
                    df, keltner_params=keltner_params, rvi_params=rvi_params, timeframe=self.current_timeframe, df_15m=df_15m
                )

                if final_signals is None or final_signals.empty:
                    print("Signal generation returned an empty DataFrame.")
                    return None

                if not include_15m_rvi:
                    final_signals['rvi_signal_15m'] = 0

                # Prepare a DataFrame for saving to the database
                db_signals = final_signals[[  # Ensure all columns exist
                    "timestamp", "symbol", "timeframe", "keltner_signal",
                    "rvi_signal", "final_signal", "keltner_upper",
                    "keltner_lower", "rvi", "rvi_signal_15m"
                ]].copy()

                # Save signals to the database
                self.db_manager.save_signals_to_db(db_signals)

                # Return updated DataFrame for plotting
                return final_signals, self.current_symbol, self.current_timeframe

            except Exception as e:
                print(f"Error in task: {e}")
                return None

        # Start background worker
        self.worker = BackgroundWorker(task)
        self.worker.data_ready_signal.connect(self.handle_data_ready)
        self.worker.progress_signal.connect(self.update_status_label)
        self.worker.finished.connect(self.cleanup_worker)
        self.worker.start()

    def refresh_data(self):
        if not self.current_symbol or not self.current_timeframe:
            self.update_status_label("No Ticker Selected", None)
            return

        # Define the worker task
        def task():
            include_15m_rvi = self.db_manager.fetch_include_15m_rvi(self.current_symbol, self.current_timeframe)

            query = f"""
                SELECT h.timestamp, h.close, h.open, h.high, h.low, h.volume,
                    COALESCE(s.keltner_upper, 0) AS keltner_upper,
                    COALESCE(s.keltner_lower, 0) AS keltner_lower,
                    COALESCE(s.rvi, 0) AS rvi,
                    COALESCE(s.keltner_signal, 0) AS keltner_signal,
                    COALESCE(s.rvi_signal, 0) AS rvi_signal,
                    COALESCE(s.final_signal, 0) AS final_signal
            """

            if include_15m_rvi:
                query += """,
                    COALESCE(s15.rvi, 0) AS rvi_15m
                FROM historical_data h
                LEFT JOIN signals_data s
                ON h.timestamp = s.timestamp AND h.symbol = s.symbol AND h.timeframe = s.timeframe
                LEFT JOIN signals_data s15
                ON h.timestamp = s15.timestamp AND h.symbol = s15.symbol AND s15.timeframe = '15m'
                """
            else:
                query += """
                FROM historical_data h
                LEFT JOIN signals_data s
                ON h.timestamp = s.timestamp AND h.symbol = s.symbol AND h.timeframe = s.timeframe
                """

            query += f"""
                WHERE h.symbol = '{self.current_symbol}' AND h.timeframe = '{self.current_timeframe}'
                ORDER BY h.timestamp ASC
            """

            with self.db_manager.engine.connect() as connection:
                df = pd.read_sql(query, connection)

            print(f'Dataframe for {self.current_symbol, self.current_timeframe}')
            print(df)
            quit()

            if df.empty:
                return f"No data available for {self.current_symbol} ({self.current_timeframe}).", self.current_symbol, self.current_timeframe

            df["timestamp"] = pd.to_datetime(df["timestamp"])
            return df, self.current_symbol, self.current_timeframe

        # Create and start the worker
        self.worker = BackgroundWorker(task)
        self.worker.data_ready_signal.connect(self.handle_data_ready)
        self.worker.progress_signal.connect(self.update_status_label)
        self.worker.finished.connect(self.cleanup_worker)
        self.worker.start()


    def handle_data_ready(self, df, symbol, timeframe):
        """
        Handles data from the worker and updates the plot.
        """
        self.plot_canvas.plot_data(df, symbol, timeframe)
        self.update_status_label("Data Refreshed Successfully", QDateTime.currentDateTime())

    def cleanup_worker(self):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()  # Ensure the thread is stopped
            print("Background worker cleaned up.")

    def update_status_label(self, status, last_updated=None):
        """
        Update the system status label with the current status and last update time.
        """
        last_updated_str = last_updated.toString("yyyy-MM-dd HH:mm") if last_updated else "Not Yet Updated"
        self.status_label.setText(f"System Status: {status} | Last Updated: {last_updated_str}")

    def buy_ticker(self):
        """
        Handle buy action for the selected ticker with the specified order type and details.
        """
        if not self.selected_ticker:
            QMessageBox.warning(self, "No Ticker Selected", "Please select a ticker to place an order.")
            return

        try:
            # Determine order type
            order_type = self.order_type_combo.currentText()

            # Validate dollar amount for market orders
            if order_type == "Market":
                dollar_amount_text = self.dollar_amount_input.text().strip()
                if not dollar_amount_text:
                    QMessageBox.warning(self, "Invalid Input", "Dollar amount cannot be empty for a market order.")
                    return
                dollar_amount = float(dollar_amount_text)
                if dollar_amount <= 0:
                    QMessageBox.warning(self, "Invalid Input", "Dollar amount must be greater than 0.")
                    return

                # Execute market order with dollar amount as cost
                response = self.trade_executor.place_order(
                    symbol=self.selected_ticker,
                    order_type="market",
                    side="buy",
                    amount=dollar_amount  # Cost in quote currency
                )
            else:  # Limit order
                # Validate order amount
                order_amount_text = self.order_amount_input.text().strip()
                if not order_amount_text:
                    QMessageBox.warning(self, "Invalid Input", "Order amount cannot be empty for a limit order.")
                    return
                order_amount = float(order_amount_text)
                if order_amount <= 0:
                    QMessageBox.warning(self, "Invalid Input", "Order amount must be greater than 0.")
                    return

                # Validate limit price
                limit_price_text = self.limit_price_input.text().strip()
                if not limit_price_text:
                    QMessageBox.warning(self, "Invalid Input", "Limit price cannot be empty for a limit order.")
                    return
                price = float(limit_price_text)
                if price <= 0:
                    QMessageBox.warning(self, "Invalid Input", "Limit price must be greater than 0.")
                    return

                # Execute limit order with specified amount and price
                response = self.trade_executor.place_order(
                    symbol=self.selected_ticker,
                    order_type="limit",
                    side="buy",
                    amount=order_amount,  # Amount in base currency
                    price=price
                )

            # Handle API response
            if "error" in response:
                QMessageBox.critical(self, "Order Failed", f"Failed to place order: {response['error']}")
            else:
                QMessageBox.information(
                    self,
                    "Order Placed",
                    f"{order_type} Buy Order placed for "
                    f"{dollar_amount if order_type == 'Market' else order_amount} of {self.selected_ticker} at "
                    f"{'market price' if order_type == 'Market' else f'{price:.2f}'}. Order details: {response}."
                )
        except ValueError:
            QMessageBox.critical(self, "Invalid Input", "Please enter valid numeric values for order amount and price.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {str(e)}")

    def sell_ticker(self):
        """
        Handle sell action for the selected ticker with the specified order type and details.
        """
        if not self.selected_ticker:
            QMessageBox.warning(self, "No Ticker Selected", "Please select a ticker to place an order.")
            return

        try:
            # Determine order type
            order_type = self.order_type_combo.currentText()

            if order_type == "Market":
                # Validate amount in base currency
                order_amount_text = self.order_amount_input.text().strip()
                if not order_amount_text:
                    QMessageBox.warning(self, "Invalid Input", "Order amount cannot be empty for a market order.")
                    return
                base_amount = float(order_amount_text)
                if base_amount <= 0:
                    QMessageBox.warning(self, "Invalid Input", "Order amount must be greater than 0.")
                    return

                # Execute market order
                response = self.trade_executor.place_order(
                    symbol=self.selected_ticker,
                    order_type="market",
                    side="sell",
                    amount=base_amount  # Amount in base currency
                )
            else:  # Limit order
                # Validate order amount in base currency
                order_amount_text = self.order_amount_input.text().strip()
                if not order_amount_text:
                    QMessageBox.warning(self, "Invalid Input", "Order amount cannot be empty for a limit order.")
                    return
                base_amount = float(order_amount_text)
                if base_amount <= 0:
                    QMessageBox.warning(self, "Invalid Input", "Order amount must be greater than 0.")
                    return

                # Validate limit price
                limit_price_text = self.limit_price_input.text().strip()
                if not limit_price_text:
                    QMessageBox.warning(self, "Invalid Input", "Limit price cannot be empty for a limit order.")
                    return
                price = float(limit_price_text)
                if price <= 0:
                    QMessageBox.warning(self, "Invalid Input", "Limit price must be greater than 0.")
                    return

                # Execute limit order
                response = self.trade_executor.place_order(
                    symbol=self.selected_ticker,
                    order_type="limit",
                    side="sell",
                    amount=base_amount,  # Amount in base currency
                    price=price
                )

            # Handle API response
            if "error" in response:
                QMessageBox.critical(self, "Order Failed", f"Failed to place order: {response['error']}")
            else:
                QMessageBox.information(
                    self,
                    "Order Placed",
                    f"{order_type} Sell Order placed for "
                    f"{base_amount} of {self.selected_ticker} at "
                    f"{'market price' if order_type == 'Market' else f'{price:.2f}'}. Order details: {response}."
                )
        except ValueError:
            QMessageBox.critical(self, "Invalid Input", "Please enter valid numeric values for order amount and price.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {str(e)}")

    def update_dollar_amount(self):
        """
        Update the dollar amount based on the order amount and the latest price.
        """
        if self.selected_ticker:
            latest_price = self.db_manager.get_latest_intraday_price(self.selected_ticker)
            if latest_price:
                order_amount_text = self.order_amount_input.text()
                if order_amount_text.strip():  # Ensure the input is not empty
                    try:
                        order_amount = float(order_amount_text)
                        dollar_amount = order_amount * latest_price
                        # Prevent feedback loop and update the dollar amount
                        self.dollar_amount_input.blockSignals(True)
                        self.dollar_amount_input.setText(f"{dollar_amount:.2f}")  # 2 decimal precision
                        self.dollar_amount_input.blockSignals(False)
                    except ValueError:
                        pass  # Ignore invalid input

    def update_order_amount(self):
        """
        Update the order amount based on the dollar amount and the latest price.
        """
        if self.selected_ticker:
            latest_price = self.db_manager.get_latest_intraday_price(self.selected_ticker)
            if latest_price:
                dollar_amount_text = self.dollar_amount_input.text()
                if dollar_amount_text.strip():  # Ensure the input is not empty
                    try:
                        dollar_amount = float(dollar_amount_text)
                        order_amount = dollar_amount / latest_price
                        # Prevent feedback loop and update the order amount
                        self.order_amount_input.blockSignals(True)
                        self.order_amount_input.setText(f"{order_amount:.8f}")  # 8 decimal precision
                        self.order_amount_input.blockSignals(False)
                    except ValueError:
                        pass  # Ignore invalid input

    def on_order_type_changed(self, index):
        """
        Show or hide the limit price input based on the selected order type.
        """
        is_limit_order = self.order_type_combo.currentText() == "Limit"
        self.limit_price_label.setVisible(is_limit_order)
        self.limit_price_input.setVisible(is_limit_order)

    def update_order_type(self):
        """
        Update the selected order type and handle any necessary changes in UI.
        """
        selected_order_type = self.order_type_combo.currentText()
        print(f"Selected Order Type: {selected_order_type}")

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

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TickerApp()
    window.show()
    sys.exit(app.exec())


