from PyQt6.QtWidgets import QVBoxLayout, QLabel, QLineEdit, QGridLayout, QCheckBox, QPushButton
from app.database import DatabaseManager
from app.controllers.signal_controller import SignalController

class SignalManagementPanel:
    def __init__(self, db_manager: DatabaseManager, signal_controller: SignalController):
        self.db_manager = db_manager
        self.signal_controller = signal_controller

        self.layout = QVBoxLayout()

        self.param_grid = QGridLayout()
        self.param_labels = []
        self.param_inputs = []

        self.include_15m_rvi_checkbox = QCheckBox("Include 15m RVI Condition")

        self.save_params_button = QPushButton("Save Parameters")
        self.save_params_button.clicked.connect(self.handle_save_button)  # ✅ FIXED

        self.layout.addWidget(self.include_15m_rvi_checkbox)
        self.layout.addLayout(self.param_grid)
        self.layout.addWidget(self.save_params_button)

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
            print(f"No parameters found for {symbol} ({timeframe}).")
            return

        param_names = [
            "Keltner Upper Multiplier", "Keltner Lower Multiplier", "Keltner Period",
            "RVI 15m Period", "RVI 1h Period",
            "RVI 15m Upper Threshold", "RVI 15m Lower Threshold",
            "RVI 1h Upper Threshold", "RVI 1h Lower Threshold"
        ]

        # Clear previous parameter inputs
        for widget in self.param_labels + self.param_inputs:
            self.param_grid.removeWidget(widget)
            widget.deleteLater()
        self.param_labels.clear()
        self.param_inputs.clear()

        # Populate with new parameters
        for i, (name, value) in enumerate(zip(param_names, params[:-1])):  # Exclude include_15m_rvi
            label = QLabel(name)
            input_field = QLineEdit(str(value))
            self.param_grid.addWidget(label, i, 0)
            self.param_grid.addWidget(input_field, i, 1)
            self.param_labels.append(label)
            self.param_inputs.append(input_field)

        # Update checkbox for include_15m_rvi
        self.include_15m_rvi_checkbox.setChecked(bool(params[-1]))

    def handle_save_button(self):
        """ Calls `save_parameters()` with the correct symbol and timeframe. """
        if not self.current_symbol or not self.current_timeframe:
            print("No ticker selected! Cannot save parameters.")
            return

        self.save_parameters(self.current_symbol, self.current_timeframe)

    def save_parameters(self, symbol, timeframe):
        """
        Save the updated parameters to the database and regenerate signals.
        """
        if not symbol or not timeframe:
            print("Error: No symbol or timeframe provided.")
            return

        try:
            params = [float(input_field.text()) for input_field in self.param_inputs]
            include_15m_rvi = int(self.include_15m_rvi_checkbox.isChecked())

            # ✅ Save full set of parameters
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

            print(f"Parameters saved for {symbol} ({timeframe}). Regenerating signals...")

            # ✅ Call SignalController to regenerate signals and refresh the graph
            self.signal_controller.regenerate_signals_and_refresh(symbol, timeframe)

        except ValueError:
            print("Invalid input in parameter fields. Please enter valid numerical values.")
