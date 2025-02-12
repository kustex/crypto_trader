# risk_parameters.py
from PyQt6.QtWidgets import QVBoxLayout, QLabel, QLineEdit, QGridLayout, QPushButton
from app.database import DatabaseManager

class RiskManagementPanel:
    def __init__(self, db_manager: DatabaseManager):
        """
        Initializes the Risk Management Panel.
        Displays and saves risk parameters for a selected symbol.
        """
        self.db_manager = db_manager

        # Main vertical layout for the panel
        self.layout = QVBoxLayout()

        # Create a grid layout to hold the risk parameter labels and input fields
        self.param_grid = QGridLayout()
        self.param_labels = []
        self.param_inputs = []

        self.layout.addLayout(self.param_grid)
        # Save button to persist changes
        self.save_button = QPushButton("Save Risk Parameters")
        self.save_button.clicked.connect(self.handle_save_button)
        self.layout.addWidget(self.save_button)

        # Store the current symbol to know for which ticker risk parameters are being managed
        self.current_symbol = None

    def update_risk_parameters(self, symbol):
        """
        Fetch and update parameters for the selected ticker and timeframe.
        """
        self.current_symbol = symbol  

        params = self.db_manager.fetch_risk_params(symbol)
        if not params:
            print(f"No parameters found for {symbol}.")
            return

        param_names = [
            "Stoploss",              
            "Position Size",         
            "Max Allocation",        
            "Partial Sell Fraction"  
        ]

        # Clear previous parameter inputs
        for widget in self.param_labels + self.param_inputs:
            self.param_grid.removeWidget(widget)
            widget.deleteLater()
        self.param_labels.clear()
        self.param_inputs.clear()

        # Populate with new parameters
        for i, (name, value) in enumerate(zip(param_names, params)):
            label = QLabel(name)
            input_field = QLineEdit(str(value))
            self.param_grid.addWidget(label, i, 0)
            self.param_grid.addWidget(input_field, i, 1)
            self.param_labels.append(label)
            self.param_inputs.append(input_field)

    def handle_save_button(self):
        """
        Reads the input fields, converts them to numbers, and calls the database
        method to save the updated risk parameters.
        """
        if not self.current_symbol:
            print("No symbol selected for risk parameters!")
            return

        try:
            # Convert all input field values to floats
            params = [float(field.text()) for field in self.param_inputs]
            # Save risk parameters using the database manager method save_risk_params
            self.db_manager.save_risk_params(
                self.current_symbol,
                stoploss=params[0],
                position_size=params[1],
                max_allocation=params[2],
                partial_sell_fraction=params[3]
            )
            print(f"Risk parameters saved for {self.current_symbol}.")
        except ValueError:
            print("Invalid input in risk parameters. Please enter valid numerical values.")
