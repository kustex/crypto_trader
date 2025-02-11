from PyQt6.QtWidgets import QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QWidget, QHeaderView
from datetime import datetime 


class PortfolioPanel(QWidget):
    def __init__(self, trade_executor, db_manager):
        super().__init__()
        self.trade_executor = trade_executor
        self.db_manager = db_manager

        self.layout = QVBoxLayout(self)

        # Open Positions Label
        self.open_positions_label = QLabel("Open Positions")
        self.open_positions_label.setStyleSheet("font-size: 10px;")
        self.layout.addWidget(self.open_positions_label)

        # Table for Open Positions
        self.open_positions_table = QTableWidget()
        self.open_positions_table.setColumnCount(6)  # Updated to 6 columns
        self.open_positions_table.setHorizontalHeaderLabels(["Symbol", "Size", "Entry Price", "Current Price", "Value in USDT", "Unrealized PnL", "PnL (%)"])
        self.layout.addWidget(self.open_positions_table)

        # Closed Orders Label
        self.closed_orders_label = QLabel("Closed Orders")
        self.closed_orders_label.setStyleSheet("font-size: 10px;")
        self.layout.addWidget(self.closed_orders_label)

        # Table for Closed Orders
        self.closed_orders_table = QTableWidget()
        self.closed_orders_table.setColumnCount(7)
        self.closed_orders_table.setHorizontalHeaderLabels(["Datetime", "Symbol", "Size", "Price", "Order Type", "Side", "Price Avg"]) 
        self.layout.addWidget(self.closed_orders_table)

        # Completed Trades Label
        self.completed_trades_label= QLabel("Completed Trades")
        self.completed_trades_label.setStyleSheet("font-size: 10px;")
        self.layout.addWidget(self.completed_trades_label)

        # Completed Trades (PnL) Table
        self.completed_trades_table = QTableWidget()
        self.layout.addWidget(self.completed_trades_table)

        # Initial data load
        self.update_closed_orders()
        self.update_completed_trades()
        self.update_open_positions()

    def update_closed_orders(self):
        """Fetch and update closed orders sorted by time."""
        closed_orders = self.trade_executor.get_closed_orders()[::-1]
        self.closed_orders_table.setRowCount(len(closed_orders))

        for row, order in enumerate(closed_orders):
            self.closed_orders_table.setItem(row, 0, QTableWidgetItem(order["datetime"]))
            self.closed_orders_table.setItem(row, 1, QTableWidgetItem(order["symbol"]))
            self.closed_orders_table.setItem(row, 2, QTableWidgetItem(str(order["size"])))
            self.closed_orders_table.setItem(row, 3, QTableWidgetItem(str(order["price"])))
            self.closed_orders_table.setItem(row, 4, QTableWidgetItem(order["orderType"]))
            self.closed_orders_table.setItem(row, 5, QTableWidgetItem(order["side"]))
            self.closed_orders_table.setItem(row, 6, QTableWidgetItem(str(order["priceAvg"])))

    def update_completed_trades(self):
        """Fetch and display completed trades with realized PnL, sorted by time."""
        completed_trades = self.trade_executor.fetch_completed_trades_with_pnl()

        # ✅ Sort by time before displaying
        completed_trades = sorted(completed_trades, key=lambda x: x["timestamp"], reverse=True)

        self.completed_trades_table.setRowCount(len(completed_trades))
        self.completed_trades_table.setColumnCount(6)
        self.completed_trades_table.setHorizontalHeaderLabels(["Datetime", "Symbol", "Buy Price", "Sell Price", "Size of order (USDT)", "PnL %"])
        
        for row, trade in enumerate(completed_trades):
            formatted_datetime = datetime.utcfromtimestamp(trade["timestamp"] / 1000).strftime("%d/%m/%Y - %H:%M")
            self.completed_trades_table.setItem(row, 0, QTableWidgetItem(formatted_datetime))
            self.completed_trades_table.setItem(row, 1, QTableWidgetItem(trade["symbol"]))
            self.completed_trades_table.setItem(row, 2, QTableWidgetItem(str(trade["buy_price"])))
            self.completed_trades_table.setItem(row, 3, QTableWidgetItem(str(trade["sell_price"])))
            self.completed_trades_table.setItem(row, 4, QTableWidgetItem(str(trade["size"])))
            # self.completed_trades_table.setItem(row, 5, QTableWidgetItem(str(trade["pnl_usdt"])))
            self.completed_trades_table.setItem(row, 5, QTableWidgetItem(f"{trade['pnl_percent']:.2f}%"))

        self.completed_trades_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

    def update_open_positions(self):
        """Track open positions correctly, accounting for partial sells."""
        open_positions = self.trade_executor.fetch_open_positions()

        self.open_positions_table.setRowCount(len(open_positions))
        self.open_positions_table.setColumnCount(6)  
        self.open_positions_table.setHorizontalHeaderLabels(["Symbol", "Total (USDT)", "Avg Buy Price", "Current Price", "PnL (USDT)", "PnL %"])

        for row, position in enumerate(open_positions):
            symbol = position["symbol"]
            size_in_usdt = position["size"]  
            avg_price = position["avg_price"]
            current_price = self.trade_executor.get_current_price(symbol)

            if current_price is None:
                current_price = avg_price 

            unrealized_pnl = size_in_usdt * ((current_price / avg_price) - 1)  
            pnl_percent = (unrealized_pnl / size_in_usdt) * 100 if size_in_usdt > 0 else 0

            self.open_positions_table.setItem(row, 0, QTableWidgetItem(symbol))
            self.open_positions_table.setItem(row, 1, QTableWidgetItem(str(round(size_in_usdt, 6))))  
            self.open_positions_table.setItem(row, 2, QTableWidgetItem(str(round(avg_price, 6))))
            self.open_positions_table.setItem(row, 3, QTableWidgetItem(str(round(current_price, 6)) if current_price else "N/A"))
            self.open_positions_table.setItem(row, 4, QTableWidgetItem(str(round(unrealized_pnl, 6))))
            self.open_positions_table.setItem(row, 5, QTableWidgetItem(f"{round(pnl_percent, 2)}%"))

        self.open_positions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
