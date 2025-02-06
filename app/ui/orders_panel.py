from PyQt6.QtWidgets import QVBoxLayout, QLabel, QPushButton, QComboBox, QLineEdit

class OrdersPanel:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.layout = QVBoxLayout()

        self.order_label = QLabel("Manual Orders")
        self.order_type_combo = QComboBox()
        self.order_type_combo.addItems(["Market", "Limit"])
        self.limit_price_input = QLineEdit()
        self.order_amount_input = QLineEdit()
        self.dollar_amount_input = QLineEdit()
        self.buy_button = QPushButton("Buy")
        self.sell_button = QPushButton("Sell")

        self.layout.addWidget(self.order_label)
        self.layout.addWidget(self.order_type_combo)
        self.layout.addWidget(self.limit_price_input)
        self.layout.addWidget(self.order_amount_input)
        self.layout.addWidget(self.dollar_amount_input)
        self.layout.addWidget(self.buy_button)
        self.layout.addWidget(self.sell_button)

    def reset_order_inputs(self, selected_ticker):
        """
        Reset order-related UI fields when a new ticker is selected.
        """
        self.selected_ticker = selected_ticker
        self.order_label.setText(f"Selected Ticker: {self.selected_ticker}")
        self.order_type_combo.setCurrentIndex(0)  # Reset to "Market"
        self.limit_price_input.clear()
        self.limit_price_input.setVisible(False)
        self.order_amount_input.clear()
        self.dollar_amount_input.clear()

        # Enable order input fields
        self.buy_button.setEnabled(True)
        self.sell_button.setEnabled(True)
        self.order_amount_input.setEnabled(True)
        self.dollar_amount_input.setEnabled(True)
        self.order_type_combo.setEnabled(True)

