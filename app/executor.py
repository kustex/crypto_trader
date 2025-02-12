import ccxt
import logging
import json
import os 
from collections import defaultdict
from datetime import datetime, timezone, timedelta

LOCAL_TZ = timezone(timedelta(hours=1))

class TradeExecutor:
    """
    A class to interact with the Bitget exchange using CCXT for trading.
    """
    PORTFOLIO_FILE = "data/portfolio.json"

    def __init__(self, api_key, api_secret, passphrase, testnet=False):
        """
        Initialize the Bitget client and load persisted state.
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

        # State variables
        self.portfolio = {}          
        self.completed_trades = []   
        self.processed_order_ids = set()  

        # Setup logging
        self._setup_logging()

        # Load previously saved state from JSON files
        self._load_state()

    def _setup_logging(self):
        """Configure logging for trade execution."""
        logging.basicConfig(
            filename="logs/trading_log.txt",
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s"
        )

    def _save_json(self, filename, data):
        """Helper method to ensure the data folder exists and save JSON data."""
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)

    def _load_json(self, filename):
        """Helper method to load JSON data if the file exists."""
        if os.path.exists(filename):
            with open(filename, "r") as f:
                return json.load(f)
        return None

    def _load_state(self):
        """Load state from JSON files so we don't duplicate orders, trades, and positions."""
        try:
            # Load closed orders (if needed, you might want to store them for reference)
            closed_orders = self._load_json("data/closed_orders.json")
            if closed_orders:
                # If closed orders have an 'id', add them to processed_order_ids
                for order in closed_orders:
                    if "id" in order:
                        self.processed_order_ids.add(order["id"])
            # Load completed trades
            loaded_trades = self._load_json("data/completed_trades.json")
            if loaded_trades:
                self.completed_trades = loaded_trades
            # Load portfolio data
            loaded_portfolio = self._load_json("data/portfolio.json")
            if loaded_portfolio:
                self.portfolio = loaded_portfolio

            logging.info("State loaded successfully from JSON files.")
        except Exception as e:
            logging.error(f"Error loading state from JSON files: {e}")

    def get_closed_orders(self):
        """Fetch all closed orders and ensure correct size representation."""
        try:
            closed_orders = self.exchange.fetch_closed_orders()
            orders = []
            for order in closed_orders:
                order_id = order.get("id", None)
                timestamp = order.get("timestamp", 0)
                formatted_datetime = (
                    datetime.fromtimestamp(timestamp / 1000, tz=LOCAL_TZ).strftime("%d/%m/%Y - %H:%M")
                    if timestamp else ""
                )
                base_currency, quote_currency = order["symbol"].split("/")
                order_type = order.get("type", "")
                side = order.get("side", "")
                price = float(order.get("price", 0))
                # Use "average" from the order for the executed price.
                price_avg = float(order.get("average", 0))
                amount = float(order.get("amount", 0))
                # The exchange provides a "cost" field for the total cost in quote currency.
                cost = float(order.get("cost", amount * price_avg))
                filled = float(order.get("filled", 0))
                
                # For limit orders, we might calculate size differently,
                # but for now, we'll use cost as the USDT value.
                if order_type == "limit":
                    size = cost  # or you could use filled * price_avg
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
                    "filled": filled,  # new field
                    "cost": cost       # new field
                })

            co = sorted(orders, key=lambda x: x["timestamp"], reverse=False)
            self._save_json("data/closed_orders.json", co)
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
            for symbol, data in self.portfolio.items() if data["total_quantity"] > 0
        ]
        self._save_json("data/open_positions.json", open_positions)
        return open_positions  

    def fetch_completed_trades_with_pnl(self):
        """Fetch closed orders and calculate realized PnL while updating the portfolio
        using delta updates. The portfolio state is maintained as:
        - total_invested: Total USDT spent (or recovered) on the asset.
        - units: Number of asset units held.
        For sell orders, the realized PnL is computed based on the cost basis of the sold units.
        """
        closed_orders = self.get_closed_orders()

        for order in closed_orders:
            order_id = order.get("id")
            if order_id is None or order_id in self.processed_order_ids:
                continue

            symbol = order["symbol"]
            side = order["side"]
            timestamp = order["timestamp"]

            # Get exchange-provided values:
            # 'filled' is the number of asset units actually executed,
            # 'cost' is the total USDT amount for this order.
            filled = float(order.get("filled", 0))
            order_cost = float(order.get("cost", filled * float(order.get("priceAvg", 0))))
            trade_price = float(order.get("priceAvg", 0))
            base_currency, quote_currency = symbol.split("/")

            if side == "buy":
                # Update portfolio for a buy order.
                if symbol not in self.portfolio:
                    self.portfolio[symbol] = {"total_invested": 0.0, "units": 0.0}
                current_invested = self.portfolio[symbol]["total_invested"]
                current_units = self.portfolio[symbol]["units"]

                new_total_invested = current_invested + order_cost
                new_units = current_units + filled
                # New average buy price calculated as total invested / total units.
                new_avg_price = new_total_invested / new_units if new_units > 0 else trade_price

                self.portfolio[symbol]["total_invested"] = new_total_invested
                self.portfolio[symbol]["units"] = new_units

                # If the quote currency is USDT and there's a USDT/EUR entry, subtract the cost.
                if quote_currency == "USDT" and "USDT/EUR" in self.portfolio:
                    self.portfolio["USDT/EUR"]["total_invested"] -= order_cost

            elif side == "sell":
                # For sell orders, ensure the symbol exists in the portfolio.
                if symbol not in self.portfolio:
                    continue
                current_invested = self.portfolio[symbol]["total_invested"]
                current_units = self.portfolio[symbol]["units"]
                if current_units <= 0:
                    continue

                # Determine effective units sold (should not exceed units held).
                effective_sell_units = min(filled, current_units)
                # Calculate average buy price from the portfolio.
                avg_buy_price = current_invested / current_units if current_units > 0 else trade_price
                # Cost basis for the sold units:
                cost_basis = effective_sell_units * avg_buy_price
                # Realized PnL in USDT:
                realized_pnl_usdt = effective_sell_units * (trade_price - avg_buy_price)
                pnl_percent = ((trade_price - avg_buy_price) / avg_buy_price * 100) if avg_buy_price else 0

                # Update the portfolio by subtracting the sold units and the corresponding cost.
                new_units = current_units - effective_sell_units
                new_total_invested = current_invested - cost_basis
                if new_units > 0:
                    self.portfolio[symbol]["total_invested"] = new_total_invested
                    self.portfolio[symbol]["units"] = new_units
                else:
                    del self.portfolio[symbol]

                # Append the trade record.
                self.completed_trades.append({
                    "timestamp": timestamp,
                    "symbol": symbol,
                    "buy_price": round(avg_buy_price, 6),
                    "sell_price": round(trade_price, 6),
                    "units_sold": round(effective_sell_units, 6),
                    "cost_basis": round(cost_basis, 2),
                    "pnl_usdt": round(realized_pnl_usdt, 2),
                    "pnl_percent": round(pnl_percent, 2)
                })

                # If the quote currency is USDT and there's a USDT/EUR entry, add back the cost.
                if quote_currency == "USDT" and "USDT/EUR" in self.portfolio:
                    self.portfolio["USDT/EUR"]["total_invested"] += cost_basis

            # Mark this order as processed.
            self.processed_order_ids.add(order_id)

        # Sort completed trades by timestamp (oldest first).
        self.completed_trades.sort(key=lambda x: x["timestamp"], reverse=False)
        self._save_json("data/completed_trades.json", self.completed_trades)
        self._save_json("data/portfolio.json", self.portfolio)
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
