import ccxt
import logging
import json
import os 
from collections import defaultdict
from datetime import datetime


class TradeExecutor:
    """
    A class to interact with the Bitget exchange using CCXT for trading.
    """

    PORTFOLIO_FILE = "data/portfolio.json"

    def __init__(self, api_key, api_secret, passphrase, testnet=False):
        """
        Initialize the Bitget client.
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase

        # Initialize Bitget exchange with CCXT
        self.exchange = ccxt.bitget({
            "apiKey": api_key,
            "secret": api_secret,
            "password": passphrase,
            "enableRateLimit": True,
        })

        # Use testnet if specified
        if testnet:
            self.exchange.set_sandbox_mode(True)

        self.portfolio = {}
        self.completed_trades = []

        # NEW: Set to track already processed closed order IDs
        self.processed_order_ids = set()

        # Setup logging
        self._setup_logging()

    def _setup_logging(self):
        """Configure logging for trade execution."""
        logging.basicConfig(
            filename="logs/trading_log.txt",
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s"
        )

    def get_closed_orders(self):
        """Fetch all closed orders and ensure correct size representation."""
        try:
            closed_orders = self.exchange.fetch_closed_orders()
            orders = []

            for order in closed_orders:
                # Get the unique order ID (ensure your exchange provides this)
                order_id = order.get("id", None)
                timestamp = order.get("timestamp", 0)
                formatted_datetime = (
                    datetime.fromtimestamp(timestamp / 1000).strftime("%d/%m/%Y - %H:%M")
                    if timestamp else ""
                )
                base_currency, quote_currency = order["symbol"].split("/")
                order_type = order.get("type", "")
                side = order.get("side", "")
                price = float(order.get("price", 0))
                price_avg = float(order.get("average", 0))
                amount = float(order.get("amount", 0))
                cost = float(order.get("cost", amount * price_avg))  # Default if cost missing

                # Convert size to quote currency (for limit orders, use amount * price_avg)
                if order_type == "limit":
                    size = amount * price_avg  
                else:
                    size = cost  

                orders.append({
                    "id": order_id,
                    "datetime": formatted_datetime,
                    "symbol": order.get("symbol", ""),
                    "size": size,  
                    "price": price,
                    "orderType": order_type,
                    "side": side,
                    "priceAvg": price_avg,
                    "timestamp": timestamp,
                })

            # Sort orders by timestamp (oldest first)
            co = sorted(orders, key=lambda x: x["timestamp"], reverse=False)
            return co 
        except Exception as e:
            logging.error(f"Error fetching closed orders: {e}")
            return []

    def fetch_open_positions(self):
        """Rebuild open positions from the current state of self.portfolio."""
        open_positions = [
            {
                "symbol": symbol,
                "size": round(data["total_quantity"], 2),
                "avg_price": round(data["avg_price"], 2) if data["total_quantity"] > 0 else 0,
            }
            # for symbol, data in portfolio.items() if data["total_quantity"] > 0
            for symbol, data in self.portfolio.items() if data["total_quantity"] > 0
        ]

        return open_positions  
    def fetch_completed_trades_with_pnl(self):
        """Fetch closed trades and calculate realized PnL correctly while updating the portfolio
        using delta updates. This method updates the portfolio with new buy orders by recalculating
        the weighted average price, and for sell orders, it computes the realized PnL on the sold quantity.
        """
        closed_orders = self.get_closed_orders()

        for order in closed_orders:
            order_id = order.get("id")
            # Skip if the order has no id or has already been processed.
            if order_id is None or order_id in self.processed_order_ids:
                continue

            symbol = order["symbol"]
            size = float(order["size"])           # quantity involved in this order
            trade_price = float(order["priceAvg"])  # executed price for this order
            side = order["side"]
            timestamp = order["timestamp"]
            base_currency, quote_currency = symbol.split("/")

            # Ensure the portfolio entry exists for a buy order.
            # For a sell order, if the symbol is missing, we cannot process it.
            if symbol not in self.portfolio:
                if side == "buy":
                    # Initialize portfolio entry for new buy
                    self.portfolio[symbol] = {"avg_price": 0.0, "total_quantity": 0.0}
                else:
                    # Sell order for an unknown symbol: skip or log a warning.
                    continue

            current_qty = self.portfolio[symbol]["total_quantity"]
            current_avg_price = self.portfolio[symbol]["avg_price"]

            if side == "buy":
                # Recalculate weighted average price for the position
                new_total_qty = current_qty + size
                # Avoid division by zero; if current_qty is zero, the new_avg_price is just the trade price.
                new_avg_price = (
                    ((current_avg_price * current_qty) + (trade_price * size)) / new_total_qty
                    if new_total_qty else trade_price
                )
                # Update portfolio entry with new totals
                self.portfolio[symbol]["total_quantity"] = new_total_qty
                self.portfolio[symbol]["avg_price"] = new_avg_price

                # Optionally, if you have special handling (e.g. for USDT/EUR adjustments), add it here.
                # For example:
                if quote_currency == "USDT" and "USDT/EUR" in self.portfolio:
                    self.portfolio["USDT/EUR"]["total_quantity"] -= size

            elif side == "sell":
                if current_qty <= 0:
                    # Nothing to sell; skip or log a warning.
                    continue

                # Determine the effective quantity to sell (if the order size is larger than our position, limit to what we have)
                effective_sell_qty = min(size, current_qty)
                # Calculate realized PnL: (sell_price - average_buy_price) * quantity sold
                # realized_pnl = (trade_price - current_avg_price) * effective_sell_qty
                # Calculate PnL percentage relative to the average buy price
                pnl_percent = ((trade_price - current_avg_price) / current_avg_price * 100) if current_avg_price else 0

                new_total_qty = current_qty - effective_sell_qty

                if new_total_qty > 0:
                    # For a partial sale, the average price remains the same.
                    self.portfolio[symbol]["total_quantity"] = new_total_qty
                else:
                    # Position completely closed—remove the symbol from the portfolio.
                    del self.portfolio[symbol]

                self.completed_trades.append({
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "buy_price": round(current_avg_price, 6),
                    "sell_price": round(trade_price, 6),
                    "size": round(effective_sell_qty, 6),
                    # "pnl_usdt": round(realized_pnl, 6),
                    "pnl_percent": round(pnl_percent, 2)
                })

                # Optionally, if you have special adjustments for other symbols (e.g., USDT/EUR), process them here.
                # For example:
                if quote_currency == "USDT" and "USDT/EUR" in self.portfolio:
                    self.portfolio["USDT/EUR"]["total_quantity"] += effective_sell_qty

            # Mark this order as processed.
            self.processed_order_ids.add(order_id)

        # Sort the completed trades by timestamp (oldest first) for display consistency.
        self.completed_trades.sort(key=lambda x: x["timestamp"], reverse=False)
        return self.completed_trades


    def get_current_price(self, symbol):
        """Fetch the latest market price for the given symbol."""
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return float(ticker["last"]) if "last" in ticker and ticker["last"] else None
        except Exception as e:
            print(f"Error fetching price for {symbol}: {e}")
            return None

    def get_account_balance(self):
        """Fetch account balances from Bitget."""
        try:
            balance_data = self.exchange.fetch_balance()
            balances = []

            for asset, details in balance_data['total'].items():
                if details > 0:
                    balances.append({
                        "symbol": asset,
                        "balance": details,
                        "available": balance_data['free'].get(asset, 0),
                        "reserved": balance_data['used'].get(asset, 0)
                    })

            return balances
        except Exception as e:
            logging.error(f"Error fetching account balance: {e}")
            return []

    def place_order(self, symbol, order_type, side, amount, margin_mode=None, trade_side=None, price=None):
        """
        Place an order on the Bitget exchange.
        """
        try:
            params = {}
            if margin_mode:
                params["marginMode"] = margin_mode
            if trade_side:
                params["tradeSide"] = trade_side

            # Market buy order handling
            if order_type == "market" and side == "buy":
                params["createMarketBuyOrderRequiresPrice"] = False
                order = self.exchange.create_order(
                    symbol=symbol,
                    type="market",
                    side=side,
                    amount=amount,  
                    params=params
                )
            # Market sell or other orders
            elif order_type == "market" and side == 'sell':
                order = self.exchange.create_order(
                    symbol=symbol,
                    type="market",
                    side=side,
                    amount=amount,
                    params=params
                )
            # Limit order
            elif order_type == "limit":
                if not price:
                    raise ValueError("Price is required for limit orders.")
                order = self.exchange.create_order(
                    symbol=symbol,
                    type="limit",
                    side=side,
                    amount=amount,
                    price=price,
                    params=params
                )
            else:
                raise ValueError("Invalid order type. Use 'market' or 'limit'.")

            # Log and return the order
            logging.info(f"Order placed: {order}")
            order_id = order.get("id", None)
            return {"order_id": order_id, "status": order["status"]}

        except Exception as e:
            logging.error(f"Error placing order: {e}")
            return {"error": str(e)}

    def check_order_status(self, order_id, symbol):
        """
        Check the status of an order on the exchange.

        Args:
            order_id (str): The unique order ID.
            symbol (str): The trading pair (e.g., "BTC/USDT").

        Returns:
            str: The status of the order (e.g., "open", "closed", "canceled").
        """
        try:
            order = self.exchange.fetch_order(order_id, symbol)
            return order.get("status", "unknown")  # Possible values: "open", "closed", "canceled"
        except Exception as e:
            print(f"Error checking order status for {order_id}: {e}")
            return "error"
