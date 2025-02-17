import json
import os
from PyQt6.QtWidgets import (
    QVBoxLayout, QLabel, QLineEdit, QGridLayout, QCheckBox, QPushButton
)
from app.database import DatabaseManager
from app.controllers.signal_controller import SignalController

OPTIMAL_PARAMS_FILE = "optimal_signal_params.json"

class SignalManagementPanel:
    def __init__(self, db_manager: DatabaseManager, signal_controller: SignalController):
        self.db_manager = db_manager
        self.signal_controller = signal_controller

        self.layout = QVBoxLayout()
        self.param_grid = QGridLayout()
        self.param_labels = []
        self.param_inputs = []

        self.include_15m_rvi_checkbox = QCheckBox("Include 15m RVI Condition")

        # ✅ Buttons
        self.save_params_button = QPushButton("Save Parameters")
        self.save_params_button.clicked.connect(self.handle_save_button)

        self.load_params_button = QPushButton("Load Parameters")
        self.load_params_button.clicked.connect(self.load_parameters)  # ✅ New Load Button

        # ✅ Status Label
        self.status_label = QLabel("Status: Ready")

        self.layout.addWidget(self.include_15m_rvi_checkbox)
        self.layout.addLayout(self.param_grid)
        self.layout.addWidget(self.save_params_button)
        self.layout.addWidget(self.load_params_button)  # ✅ Add below save button
        self.layout.addWidget(self.status_label)

        self.current_symbol = None
        self.current_timeframe = None

    def update_signal_parameters(self, symbol, timeframe):
        """
        Fetch and update parameters for the selected ticker and timeframe.
        """
        self.current_symbol = symbol  
        self.current_timeframe = timeframe  

        params = self.db_manager.fetch_indicator_params(symbol, timeframe)
        if not params:
            self.status_label.setText(f"⚠️ No parameters found for {symbol} ({timeframe})")
            return

        param_names = [
            "Keltner Upper Multiplier", "Keltner Lower Multiplier", "Keltner Period",
            "RVI 15m Period", "RVI 1h Period",
            "RVI 15m Upper Threshold", "RVI 15m Lower Threshold",
            "RVI 1h Upper Threshold", "RVI 1h Lower Threshold"
        ]

        # ✅ Clear previous parameter inputs
        for widget in self.param_labels + self.param_inputs:
            self.param_grid.removeWidget(widget)
            widget.deleteLater()
        self.param_labels.clear()
        self.param_inputs.clear()

        # ✅ Populate with new parameters
        for i, (name, value) in enumerate(zip(param_names, params[:-1])):  # Exclude include_15m_rvi
            label = QLabel(name)
            input_field = QLineEdit(str(value))
            self.param_grid.addWidget(label, i, 0)
            self.param_grid.addWidget(input_field, i, 1)
            self.param_labels.append(label)
            self.param_inputs.append(input_field)

        # ✅ Update checkbox for include_15m_rvi
        self.include_15m_rvi_checkbox.setChecked(bool(params[-1]))

    def handle_save_button(self):
        """ Calls `save_parameters()` with the correct symbol and timeframe. """
        if not self.current_symbol or not self.current_timeframe:
            self.status_label.setText("⚠️ No ticker selected! Cannot save parameters.")
            return

        self.save_parameters(self.current_symbol, self.current_timeframe)

    def save_parameters(self, symbol, timeframe):
        """
        Save the updated parameters to the database and regenerate signals.
        """
        if not symbol or not timeframe:
            self.status_label.setText("⚠️ No symbol or timeframe provided.")
            return

        try:
            params = [float(input_field.text()) for input_field in self.param_inputs]
            include_15m_rvi = int(self.include_15m_rvi_checkbox.isChecked())

            # ✅ Save full set of parameters to database
            self.db_manager.save_indicator_params(
                symbol, timeframe,
                keltner_upper_multiplier=params[0],
                keltner_lower_multiplier=params[1],
                keltner_period=int(params[2]), 
                rvi_15m_period=int(params[3]),
                rvi_1h_period=int(params[4]),
                rvi_15m_upper_threshold=params[5], 
                rvi_15m_lower_threshold=params[6],
                rvi_1h_upper_threshold=params[7],
                rvi_1h_lower_threshold=params[8],
                include_15m_rvi=include_15m_rvi
            )

            self.status_label.setText(f"✅ Parameters saved for {symbol} ({timeframe}). Regenerating signals...")

            # ✅ Call SignalController to regenerate signals and refresh the graph
            self.signal_controller.regenerate_signals_and_refresh(symbol, timeframe)

        except ValueError:
            self.status_label.setText("❌ Invalid input! Enter valid numbers.")

    def load_parameters(self):
        """
        Load saved **signal** parameters from file for the current symbol and update the UI.
        """
        if not os.path.exists(OPTIMAL_PARAMS_FILE):
            self.status_label.setText("⚠️ No saved parameters found!")
            return

        if not self.current_symbol:
            self.status_label.setText("⚠️ No symbol selected to load parameters!")
            return

        try:
            with open(OPTIMAL_PARAMS_FILE, "r") as f:
                all_params = json.load(f)

            # Get parameters for the current symbol
            if self.current_symbol not in all_params:
                self.status_label.setText(f"⚠️ No parameters found for {self.current_symbol}!")
                return

            params = all_params[self.current_symbol]

            # Define the expected signal parameter keys.
            signal_param_keys = [
                "keltner_upper_multiplier", "keltner_lower_multiplier", "keltner_period",
                "rvi_15m_period", "rvi_1h_period",
                "rvi_15m_upper_threshold", "rvi_15m_lower_threshold",
                "rvi_1h_upper_threshold", "rvi_1h_lower_threshold"
            ]

            # Extract parameter values.
            param_values = [params[key] for key in signal_param_keys]

            # Update the UI input fields with the loaded parameter values.
            for row, value in enumerate(param_values):
                self.param_inputs[row].setText(str(value))

            # Update the checkbox separately.
            self.include_15m_rvi_checkbox.setChecked(bool(params.get("include_15m_rvi", 0)))

            self.status_label.setText("✅ Signal Parameters Loaded Successfully!")

        except KeyError as e:
            self.status_label.setText(f"❌ Missing parameter: {str(e)}")
        except Exception as e:
            self.status_label.setText(f"❌ Error loading parameters: {str(e)}")
