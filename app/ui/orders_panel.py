import time

from PyQt6.QtWidgets import (
    QVBoxLayout, QLabel, QPushButton, QComboBox, QLineEdit, QMessageBox
)
from app.executor import TradeExecutor  
from app.controllers.order_checker import OrderStatusChecker
from typing import Any 

class OrdersPanel:
    def __init__(self, db_manager, trade_executor: TradeExecutor, main_window: Any):
        """
        Initializes the Orders Panel, which allows manual order placement.
        """
        self.db_manager = db_manager
        self.trade_executor = trade_executor  
        self.main_window = main_window  

        self.selected_ticker = None 

        # Create main layout
        self.layout = QVBoxLayout()

        # Section Label
        # self.order_label = QLabel("Manual Orders")
        # self.order_label.setStyleSheet("font-weight: bold; font-size: 16px;")
        # self.layout.addWidget(self.order_label)

        # Order Type Selection
        self.order_type_combo = QComboBox()
        self.order_type_combo.addItems(["Market", "Limit"])
        self.layout.addWidget(QLabel("Order Type:"))
        self.layout.addWidget(self.order_type_combo)

        # Limit Price Input (Hidden by Default)
        self.limit_price_label = QLabel("Limit Price:")
        self.limit_price_input = QLineEdit()
        self.limit_price_input.setPlaceholderText("Enter limit price")
        self.layout.addWidget(self.limit_price_label)
        self.layout.addWidget(self.limit_price_input)

        # Order Amount Input
        # self.order_amount_label = QLabel("Order Amount:")
        self.order_amount_input = QLineEdit()
        self.order_amount_input.setPlaceholderText("Enter order amount")
        # self.layout.addWidget(self.order_amount_label)
        self.layout.addWidget(self.order_amount_input)

        # Dollar Amount Input
        # self.dollar_amount_label = QLabel("Dollar Amount (Market Only):")
        self.dollar_amount_input = QLineEdit()
        self.dollar_amount_input.setPlaceholderText("Enter amount in USD")
        # self.layout.addWidget(self.dollar_amount_label)
        self.layout.addWidget(self.dollar_amount_input)

        # Buy & Sell Buttons
        self.buy_button = QPushButton("Buy")
        self.sell_button = QPushButton("Sell")
        self.layout.addWidget(self.buy_button)
        self.layout.addWidget(self.sell_button)
        self.buy_button.clicked.connect(self.buy_ticker)
        self.sell_button.clicked.connect(self.sell_ticker)

        # Connect Events
        self.order_type_combo.currentIndexChanged.connect(self.on_order_type_changed)
        self.order_amount_input.textChanged.connect(self.update_dollar_amount)
        self.dollar_amount_input.textChanged.connect(self.update_order_amount)

        # Hide limit price fields initially
        self.limit_price_label.setVisible(False)
        self.limit_price_input.setVisible(False)

    def reset_order_inputs(self, selected_ticker):
        """
        Reset order-related UI fields when a new ticker is selected.
        """
        self.selected_ticker = selected_ticker
        # self.order_label.setText(f"Selected Ticker: {self.selected_ticker}")
        self.order_type_combo.setCurrentIndex(0)  # Reset to "Market"
        self.limit_price_input.clear()
        self.limit_price_input.setVisible(False)
        self.order_amount_input.clear()
        self.dollar_amount_input.clear()

    def update_dollar_amount(self):
        """
        Update the dollar amount based on the order amount and the latest price.
        """
        if self.selected_ticker:
            latest_price = self.db_manager.get_latest_intraday_price(self.selected_ticker)
            if latest_price:
                order_amount_text = self.order_amount_input.text().strip()
                if order_amount_text:
                    try:
                        order_amount = float(order_amount_text)
                        dollar_amount = order_amount * latest_price
                        self.dollar_amount_input.blockSignals(True)
                        self.dollar_amount_input.setText(f"{dollar_amount:.2f}")
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
                dollar_amount_text = self.dollar_amount_input.text().strip()
                if dollar_amount_text:
                    try:
                        dollar_amount = float(dollar_amount_text)
                        order_amount = dollar_amount / latest_price
                        self.order_amount_input.blockSignals(True)
                        self.order_amount_input.setText(f"{order_amount:.8f}")
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


    def buy_ticker(self):
        """
        Handle buy action for the selected ticker with the specified order type and details.
        """
        if not self.selected_ticker:
            self.main_window.status_label.setText("⚠️ No Ticker Selected: Please select a ticker to place an order.")
            self.main_window.status_label.setStyleSheet("color: red; font-weight: bold;")
            return

        try:
            # Determine order type
            order_type = self.order_type_combo.currentText()

            # ✅ Market Order
            if order_type == "Market":
                dollar_amount_text = self.dollar_amount_input.text().strip()
                if not dollar_amount_text:
                    self.main_window.status_label.setText("⚠️ Invalid Input: Dollar amount cannot be empty for market order.")
                    self.main_window.status_label.setStyleSheet("color: red; font-weight: bold;")
                    return

                dollar_amount = float(dollar_amount_text)
                if dollar_amount <= 0:
                    self.main_window.status_label.setText("⚠️ Invalid Input: Dollar amount must be greater than 0.")
                    self.main_window.status_label.setStyleSheet("color: red; font-weight: bold;")
                    return

                # Execute market order with dollar amount
                response = self.trade_executor.place_order(
                    symbol=self.selected_ticker,
                    order_type="market",
                    side="buy",
                    amount=dollar_amount  # Cost in quote currency
                )

            # ✅ Limit Order
            else:
                order_amount_text = self.order_amount_input.text().strip()
                limit_price_text = self.limit_price_input.text().strip()

                if not order_amount_text or not limit_price_text:
                    self.main_window.status_label.setText("⚠️ Invalid Input: Order amount and limit price cannot be empty for limit orders.")
                    self.main_window.status_label.setStyleSheet("color: red; font-weight: bold;")
                    return

                order_amount = float(order_amount_text)
                price = float(limit_price_text)

                if order_amount <= 0 or price <= 0:
                    self.main_window.status_label.setText("⚠️ Invalid Input: Order amount and price must be greater than 0.")
                    self.main_window.status_label.setStyleSheet("color: red; font-weight: bold;")
                    return

                # Execute limit order with specified amount and price
                response = self.trade_executor.place_order(
                    symbol=self.selected_ticker,
                    order_type="limit",
                    side="buy",
                    amount=order_amount,  
                    price=price
                )

            # ✅ Handle API Response
            if "error" in response:
                self.main_window.status_label.setText(f"❌ Order Failed: {response['error']}")
                self.main_window.status_label.setStyleSheet("color: red; font-weight: bold;")
            else:
                order_id = response.get("order_id")
                if order_type == "Market":
                    display_value = dollar_amount
                    price_text = "market price"
                else:
                    display_value = order_amount 
                    price_text = f"{price:.2f}"

                self.main_window.status_label.setText(
                    f"✅ {order_type} Buy Order placed: {display_value} {self.selected_ticker} at {price_text}."
                )

                self.main_window.status_label.setStyleSheet("color: green; font-weight: bold;")
                # ✅ Start tracking the order until it's filled
                self.order_tracker = OrderStatusChecker(self.trade_executor, order_id, self.selected_ticker)
                self.order_tracker.order_filled.connect(self.main_window.update_portfolio)
                self.order_tracker.start()

        except ValueError:
            self.main_window.status_label.setText("❌ Invalid Input: Please enter valid numeric values for order amount and price.")
            self.main_window.status_label.setStyleSheet("color: red; font-weight: bold;")
        except Exception as e:
            self.main_window.status_label.setText(f"❌ Error: {str(e)}")
            self.main_window.status_label.setStyleSheet("color: red; font-weight: bold;")

    def sell_ticker(self):
        """
        Handle sell action for the selected ticker with the specified order type and details.
        """
        if not self.selected_ticker:
            self.main_window.status_label.setText("⚠️ No Ticker Selected: Please select a ticker to place an order.")
            self.main_window.status_label.setStyleSheet("font-weight: bold; color: red;")
            return

        try:
            # Determine order type
            order_type = self.order_type_combo.currentText()

            if order_type == "Market":
                # Validate amount in base currency
                order_amount_text = self.order_amount_input.text().strip()
                if not order_amount_text:
                    self.main_window.status_label.setText("⚠️ Invalid Input: Order amount cannot be empty for a market order.")
                    self.main_window.status_label.setStyleSheet("font-weight: bold; color: red;")
                    return
                base_amount = float(order_amount_text)
                if base_amount <= 0:
                    self.main_window.status_label.setText("⚠️ Invalid Input: Order amount must be greater than 0.")
                    self.main_window.status_label.setStyleSheet("font-weight: bold; color: red;")
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
                    self.main_window.status_label.setText("⚠️ Invalid Input: Order amount cannot be empty for a limit order.")
                    self.main_window.status_label.setStyleSheet("font-weight: bold; color: red;")
                    return
                base_amount = float(order_amount_text)
                if base_amount <= 0:
                    self.main_window.status_label.setText("⚠️ Invalid Input: Order amount must be greater than 0.")
                    self.main_window.status_label.setStyleSheet("font-weight: bold; color: red;")
                    return

                # Validate limit price
                limit_price_text = self.limit_price_input.text().strip()
                if not limit_price_text:
                    self.main_window.status_label.setText("⚠️ Invalid Input: Limit price cannot be empty for a limit order.")
                    self.main_window.status_label.setStyleSheet("font-weight: bold; color: red;")
                    return
                price = float(limit_price_text)
                if price <= 0:
                    self.main_window.status_label.setText("⚠️ Invalid Input: Limit price must be greater than 0.")
                    self.main_window.status_label.setStyleSheet("font-weight: bold; color: red;")
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
                self.main_window.status_label.setText(f"❌ Order Failed: {response['error']}")
                self.main_window.status_label.setStyleSheet("font-weight: bold; color: red;")
            else:
                order_id = response.get("order_id")
                self.main_window.status_label.setText(
                    f"✅ {order_type} Sell Order placed: {base_amount} {self.selected_ticker} at "
                    f"{'market price' if order_type == 'Market' else f'{price:.2f}'}."
                )
                self.main_window.status_label.setStyleSheet("font-weight: bold; color: green;")
                # ✅ Start tracking the order until it's filled
                self.order_tracker = OrderStatusChecker(self.trade_executor, order_id, self.selected_ticker)
                self.order_tracker.order_filled.connect(self.main_window.update_portfolio)
                self.order_tracker.start()

        except ValueError:
            self.main_window.status_label.setText("❌ Invalid Input: Please enter valid numeric values.")
            self.main_window.status_label.setStyleSheet("font-weight: bold; color: red;")
        except Exception as e:
            self.main_window.status_label.setText(f"❌ Error: {str(e)}")
            self.main_window.status_label.setStyleSheet("font-weight: bold; color: red;")
