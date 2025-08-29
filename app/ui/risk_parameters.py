from PyQt6.QtWidgets import QVBoxLayout, QLabel, QLineEdit, QGridLayout, QPushButton
from app.database import DatabaseManager
import json
import os

ALGORITHM_CONFIG_FILE = os.path.join("data", "algorithm_config.json")

class RiskManagementPanel:
    def __init__(self, db_manager: DatabaseManager):
        """
        Initializes the Risk Management Panel.
        Displays and saves risk parameters for a selected symbol.
        """
        self.db_manager = db_manager

        # Main vertical layout for the panel
        self.layout = QVBoxLayout()

        # --- Algorithm toggle button ---
        self.algorithm_toggle = QPushButton("Algorithm: OFF")
        self.algorithm_toggle.setCheckable(True)
        # Set initial style with very light red for OFF
        self.algorithm_toggle.setStyleSheet("background-color: #ffcccc;")
        self.algorithm_toggle.toggled.connect(self.handle_toggle_algorithm)
        self.layout.addWidget(self.algorithm_toggle)

        # Create a grid layout to hold the risk parameter labels and input fields
        self.param_grid = QGridLayout()
        self.param_labels = []
        self.param_inputs = []
        self.layout.addLayout(self.param_grid)

        # ✅ "Save Risk Parameters" Button
        self.save_button = QPushButton("Save Risk Parameters")
        self.save_button.clicked.connect(self.handle_save_button)
        self.layout.addWidget(self.save_button)

        # ✅ Status Label
        self.status_label = QLabel("Status: Ready")
        self.layout.addWidget(self.status_label)

        # Store the current symbol for which risk parameters are managed
        self.current_symbol = None

    def get_algorithm_state(self):
        """Return the current algorithm state for the selected symbol."""
        if self.current_symbol:
            config = self.load_algorithm_config()
            return config.get(self.current_symbol, False)
        return False

    def load_algorithm_config(self):
        """Load the algorithm configuration from file and ensure all tickers are present."""
        config = {}
        if os.path.exists(ALGORITHM_CONFIG_FILE):
            with open(ALGORITHM_CONFIG_FILE, "r") as f:
                config = json.load(f)
        else:
            with open(ALGORITHM_CONFIG_FILE, "w") as f:
                json.dump(config, f) 
        tickers_df = self.db_manager.fetch_tickers()
        if tickers_df is not None and not tickers_df.empty:
            tickers = tickers_df["symbol"].tolist()
            for ticker in tickers:
                if ticker not in config:
                    config[ticker] = False  
        return config

    def save_algorithm_config(self, config):
        """Save the algorithm configuration to file."""
        os.makedirs(os.path.dirname(ALGORITHM_CONFIG_FILE), exist_ok=True)
        with open(ALGORITHM_CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)

    def update_risk_parameters(self, symbol):
        """
        Fetch and update parameters for the selected ticker.
        """
        self.current_symbol = symbol  

        algorithm_state = self.get_algorithm_state()
        self.algorithm_toggle.setChecked(algorithm_state)
        self.handle_toggle_algorithm(algorithm_state)  

        params = self.db_manager.fetch_risk_params(symbol)
        if not params:
            self.status_label.setText(f"⚠️ No parameters found for {symbol}.")
            return

        param_names = [
            "Stoploss",              
            "Position Size",         
            "Max Allocation",        
            "Partial Sell Fraction"  
        ]

        # ✅ Clear previous parameter inputs
        for widget in self.param_labels + self.param_inputs:
            self.param_grid.removeWidget(widget)
            widget.deleteLater()
        self.param_labels.clear()
        self.param_inputs.clear()

        # ✅ Populate with new parameters
        for i, (name, value) in enumerate(zip(param_names, params)):
            label = QLabel(name)
            input_field = QLineEdit(str(value))
            self.param_grid.addWidget(label, i, 0)
            self.param_grid.addWidget(input_field, i, 1)
            self.param_labels.append(label)
            self.param_inputs.append(input_field)

    def handle_toggle_algorithm(self, checked):
        """
        Toggle the algorithm state for the current symbol and save to the config file.
        """
        if checked:
            self.algorithm_toggle.setText("Algorithm: ON")
            self.algorithm_toggle.setStyleSheet("background-color: #ccffcc;")
        else:
            self.algorithm_toggle.setText("Algorithm: OFF")
            self.algorithm_toggle.setStyleSheet("background-color: #ffcccc;")
        # Save the new state for the current symbol if one is selected
        if self.current_symbol:
            config = self.load_algorithm_config()
            config[self.current_symbol] = checked
            self.save_algorithm_config(config)

    def handle_save_button(self):
        """
        Reads the input fields, converts them to numbers, and calls the database
        method to save the updated risk parameters.
        """
        if not self.current_symbol:
            self.status_label.setText("⚠️ No symbol selected for saving risk parameters!")
            return

        try:
            params = [float(field.text()) for field in self.param_inputs]

            # ✅ Save risk parameters to the database
            self.db_manager.save_risk_params(
                self.current_symbol,
                stoploss=params[0],
                position_size=params[1],
                max_allocation=params[2],
                partial_sell_fraction=params[3]
            )

            self.status_label.setText(f"✅ Risk Parameters saved for {self.current_symbol}!")

        except ValueError:
            self.status_label.setText("❌ Invalid input! Enter valid numbers.")
