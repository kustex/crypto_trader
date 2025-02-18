import yfinance as yf
from PyQt6.QtWidgets import QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QWidget, QHeaderView
from datetime import datetime, timezone, timedelta

# Define the local timezone (UTC+1)
LOCAL_TZ = timezone(timedelta(hours=1))

class PortfolioPanel(QWidget):
    def __init__(self, trade_executor, db_manager):
        super().__init__()
        self.trade_executor = trade_executor
        self.db_manager = db_manager

        self.layout = QVBoxLayout(self)

        # Open Positions Label
        self.open_positions_label = QLabel("Open Positions")
        self.open_positions_label.setStyleSheet("font-weight: bold; font-size: 10px;")
        self.layout.addWidget(self.open_positions_label)

        # Table for Open Positions
        self.open_positions_table = QTableWidget()
        self.open_positions_table.setColumnCount(7)  # Symbol, Total Invested, Avg Buy Price, Current Price, Current Value, PnL (USDT), PnL (%)
        self.open_positions_table.setHorizontalHeaderLabels([
            "Symbol", 
            "Total Invested (USDT)", 
            "Current Value (USDT)", 
            "PnL (%)",
            "PnL (USDT)", 
            "Current Price", 
            "Avg Buy Price", 
        ])
        # Allow manual adjustment of columns
        self.open_positions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # self.open_positions_table.setSortingEnabled(True)
        self.layout.addWidget(self.open_positions_table)

        # Closed Orders Label
        self.closed_orders_label = QLabel("Closed Orders")
        self.closed_orders_label.setStyleSheet("font-weight: bold; font-size: 10px;")
        self.layout.addWidget(self.closed_orders_label)

        # Table for Closed Orders
        self.closed_orders_table = QTableWidget()
        self.closed_orders_table.setColumnCount(7)
        self.closed_orders_table.setHorizontalHeaderLabels([
            "Datetime", "Symbol", "Side","Size", "Price", "Order Type",  "Price Avg"
        ])
        # Allow manual adjustment of columns
        self.closed_orders_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # self.closed_orders_table.setSortingEnabled(True)
        self.layout.addWidget(self.closed_orders_table)

        # Completed Trades Label
        self.completed_trades_label = QLabel("Completed Trades")
        self.completed_trades_label.setStyleSheet("font-weight: bold; font-size: 10px;")
        self.layout.addWidget(self.completed_trades_label)

        # Table for Completed Trades
        self.completed_trades_table = QTableWidget()
        # Column count and header labels will be set in update_completed_trades()
        # Allow manual adjustment of columns
        self.completed_trades_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # self.completed_trades_table.setSortingEnabled(True)
        self.layout.addWidget(self.completed_trades_table)

        # Account Balance Label
        self.account_balance_label = QLabel("Account Balance")
        self.account_balance_label.setStyleSheet("font-weight: bold; font-size: 10px;")
        self.layout.addWidget(self.account_balance_label)

        # Table for Account Balance with columns: Ticker, Value (USDT), % of Total
        self.account_balance_table = QTableWidget()
        # Allow manual adjustment of columns
        self.account_balance_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # self.account_balance_table.setSortingEnabled(True)
        self.layout.addWidget(self.account_balance_table)

        # Initial data load for all panels.
        self.update_closed_orders()
        self.update_completed_trades()
        self.update_open_positions()
        self.update_account_balance()

    def update_open_positions(self):
        """
        Update the open positions table using the portfolio data stored in the TradeExecutor.
        Assumes each portfolio entry is stored as:
          { "total_invested": <total USDT>, "units": <number of asset units held> }
        """
        portfolio = self.trade_executor.portfolio
        open_positions = []
        for symbol, data in portfolio.items():
            if symbol == "USDT/EUR":
                continue  # Skip conversion entry if not needed.
            total_invested = data.get("total_invested", 0)
            units = data.get("units", 0)
            if units <= 0:
                continue
            avg_buy_price = total_invested / units if units > 0 else 0
            current_price = self.trade_executor.get_current_price(symbol)
            if current_price is None:
                current_price = avg_buy_price  # fallback
            current_value = units * current_price
            pnl_usdt = current_value - total_invested
            pnl_percent = (pnl_usdt / total_invested * 100) if total_invested > 0 else 0

            open_positions.append({
                "symbol": symbol,
                "total_invested": round(total_invested, 2),
                "avg_buy_price": round(avg_buy_price, 4),
                "current_price": round(current_price, 4),
                "current_value": round(current_value, 2),
                "pnl_usdt": round(pnl_usdt, 2),
                "pnl_percent": round(pnl_percent, 2)
            })

        self.open_positions_table.setRowCount(len(open_positions))
        for row, pos in enumerate(open_positions):
            self.open_positions_table.setItem(row, 0, QTableWidgetItem(pos["symbol"]))
            self.open_positions_table.setItem(row, 1, QTableWidgetItem(str(pos["total_invested"])))
            self.open_positions_table.setItem(row, 2, QTableWidgetItem(str(pos["current_value"])))
            self.open_positions_table.setItem(row, 3, QTableWidgetItem(f"{pos['pnl_percent']:.2f}%"))
            self.open_positions_table.setItem(row, 4, QTableWidgetItem(str(pos["pnl_usdt"])))
            self.open_positions_table.setItem(row, 5, QTableWidgetItem(str(pos["current_price"])))
            self.open_positions_table.setItem(row, 6, QTableWidgetItem(str(pos["avg_buy_price"])))
        # Allow manual adjustment of columns
        self.open_positions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

    def update_closed_orders(self):
        """Fetch and update closed orders sorted by time."""
        closed_orders = self.trade_executor.get_closed_orders()[::-1]
        self.closed_orders_table.setRowCount(len(closed_orders))
        for row, order in enumerate(closed_orders):
            self.closed_orders_table.setItem(row, 0, QTableWidgetItem(order["datetime"]))
            self.closed_orders_table.setItem(row, 1, QTableWidgetItem(order["symbol"]))
            self.closed_orders_table.setItem(row, 2, QTableWidgetItem(order["side"]))
            self.closed_orders_table.setItem(row, 3, QTableWidgetItem(str(order["size"])))
            self.closed_orders_table.setItem(row, 4, QTableWidgetItem(str(order["price"])))
            self.closed_orders_table.setItem(row, 5, QTableWidgetItem(order["orderType"]))
            self.closed_orders_table.setItem(row, 6, QTableWidgetItem(str(order["priceAvg"])))
        # Allow manual adjustment of columns
        self.closed_orders_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

    def update_completed_trades(self):
        """Fetch and display completed trades with realized PnL, sorted by time."""
        completed_trades = self.trade_executor.fetch_completed_trades_with_pnl()
        completed_trades = sorted(completed_trades, key=lambda x: x["timestamp"], reverse=True)
        self.completed_trades_table.setRowCount(len(completed_trades))
        self.completed_trades_table.setColumnCount(7)
        self.completed_trades_table.setHorizontalHeaderLabels([
            "Datetime", "Symbol", "Cost Basis (USDT)", "PnL (%)", "Buy Price", "Sell Price", "Units Sold"
        ])
        for row, trade in enumerate(completed_trades):
            # Convert timestamp to local time (UTC+1)
            formatted_datetime = datetime.fromtimestamp(trade["timestamp"] / 1000, tz=LOCAL_TZ).strftime("%d/%m/%Y - %H:%M")
            self.completed_trades_table.setItem(row, 0, QTableWidgetItem(formatted_datetime))
            self.completed_trades_table.setItem(row, 1, QTableWidgetItem(trade["symbol"]))
            self.completed_trades_table.setItem(row, 2, QTableWidgetItem(str(trade.get("cost_basis", "N/A"))))
            self.completed_trades_table.setItem(row, 3, QTableWidgetItem(f"{trade['pnl_percent']:.2f}%"))
            self.completed_trades_table.setItem(row, 4, QTableWidgetItem(str(trade["buy_price"])))
            self.completed_trades_table.setItem(row, 5, QTableWidgetItem(str(trade["sell_price"])))
            self.completed_trades_table.setItem(row, 6, QTableWidgetItem(str(trade.get("units_sold", "N/A"))))
        # Allow manual adjustment of columns
        self.completed_trades_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

    def update_account_balance(self):
        """
        Update the account balance table that displays:
        - Ticker
        - Value (USDT)
        - % of Total Balance

        For assets with symbol "EUR", the current price is fetched from Yahoo Finance
        using the ticker "EURUSD=X". For other assets (except USDT), the current price
        is fetched using TradeExecutor.get_current_price().
        """
        # Fetch the current account balances.
        balances = self.trade_executor.get_account_balance()
        # Filter out assets with zero balance.
        positive_balances = [asset for asset in balances if asset["balance"] > 0]

        asset_values = []
        for asset in positive_balances:
            symbol = asset["symbol"].upper()
            balance = asset["balance"]
            # For USDT, the value is just the balance.
            if symbol == "USDT":
                value = balance
            # For EUR, use Yahoo Finance to get the current EUR/USD rate.
            elif symbol == "EUR":
                try:
                    ticker_yf = yf.Ticker("EURUSD=X")
                    data = ticker_yf.history(period="1d", interval="1m")
                    if data.empty:
                        value = 0
                    else:
                        current_price = float(data['Close'].iloc[-1])
                        value = balance * current_price
                except Exception as e:
                    print(f"Error fetching EUR/USD rate: {e}")
                    value = 0
            else:
                # For other assets, assume a trading pair of SYMBOL/USDT exists.
                pair = f"{symbol}/USDT"
                current_price = self.trade_executor.get_current_price(pair)
                if current_price is None:
                    value = 0
                else:
                    value = balance * current_price
            asset_values.append((symbol, value))

        # Calculate the total USDT value of all assets.
        total_value = sum(val for (_, val) in asset_values)

        # Update the table with 3 columns: Ticker, Value (USDT), and % of Total.
        self.account_balance_table.setColumnCount(3)
        self.account_balance_table.setHorizontalHeaderLabels([
            "Ticker", "Value (USDT)", "% of Total"
        ])
        self.account_balance_table.setRowCount(len(asset_values))
        for row, (symbol, value) in enumerate(asset_values):
            percent = (value / total_value * 100) if total_value > 0 else 0
            self.account_balance_table.setItem(row, 0, QTableWidgetItem(symbol))
            self.account_balance_table.setItem(row, 1, QTableWidgetItem(f"{value:.2f}"))
            self.account_balance_table.setItem(row, 2, QTableWidgetItem(f"{percent:.2f}%"))
        # Allow manual adjustment of columns
        self.account_balance_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)