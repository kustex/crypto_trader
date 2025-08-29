import ccxt
import logging
import json
import os
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from app.ui.api_credentials import load_api_credentials, save_api_credentials

LOCAL_TZ = timezone(timedelta(hours=1))

class TradeExecutor:

    def __init__(self, api_key=None, api_secret=None, passphrase=None, testnet=False):
        """
        Initialize the Bitget client and load persisted state.
        If API credentials aren't provided, they will be loaded automatically.
        """
        # Setup logging first so we can log during initialization
        self._setup_logging()
        
        # If any credentials are missing, load them from the credentials file
        if api_key is None or api_secret is None or passphrase is None:
            from app.ui.api_credentials import load_api_credentials
            loaded_key, loaded_secret, loaded_passphrase = load_api_credentials()
            
            # Only override if the parameter wasn't provided
            self.api_key = api_key if api_key is not None else loaded_key
            self.api_secret = api_secret if api_secret is not None else loaded_secret
            self.passphrase = passphrase if passphrase is not None else loaded_passphrase
            
            logging.debug("API credentials loaded from credentials file")
        else:
            self.api_key = api_key
            self.api_secret = api_secret
            self.passphrase = passphrase

        # Log the lengths of the credentials for debugging (do not log the actual values)
        logging.info(f"Initializing TradeExecutor with API Key Length: {len(self.api_key)}, "
                     f"API Secret Length: {len(self.api_secret)}, "
                     f"Passphrase Length: {len(self.passphrase)}")

        # Log whether testnet is being used
        logging.debug(f"Using testnet: {testnet}")

        # Initialize Bitget exchange with CCXT
        self.exchange = ccxt.bitget({
            "apiKey": self.api_key,
            "secret": self.api_secret,
            "password": self.passphrase,
            "enableRateLimit": True,
        })

        # Use testnet if specified
        if testnet:
            self.exchange.set_sandbox_mode(True)
            logging.debug("Bitget exchange set to sandbox mode.")

        # State variables
        self.portfolio = {}          # { symbol: [ { "entry_price": float, "units": float }, ... ] }
        self.completed_trades = []   # Records of closed SELL trades with realized PnL
        self.processed_order_ids = set()

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
        """
        Load state from JSON files:
          - portfolio.json
          - completed_trades.json
          - closed_orders.json (for processed_order_ids)
        """
        try:
            # 1) Closed orders
            closed_orders = self._load_json("data/closed_orders.json")
            if closed_orders:
                for order in closed_orders:
                    if "id" in order:
                        self.processed_order_ids.add(order["id"])

            # 2) Completed trades
            loaded_trades = self._load_json("data/completed_trades.json")
            if loaded_trades:
                self.completed_trades = loaded_trades

            # 3) Portfolio
            loaded_portfolio = self._load_json("data/portfolio.json")
            if loaded_portfolio:
                self.portfolio = loaded_portfolio

            logging.info("State loaded successfully from JSON files.")
        except Exception as e:
            logging.error(f"Error loading state from JSON files: {e}")

    def get_closed_orders(self):
        """Fetch all closed orders from the exchange and save them to data/closed_orders.json."""
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
                price_avg = float(order.get("average", 0))
                amount = float(order.get("amount", 0))
                cost = float(order.get("cost", price_avg * amount))
                filled = float(order.get("filled", 0))

                # For limit orders, 'size' might differ, but we'll keep it simple:
                if order_type == "limit":
                    size = cost
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
                    "filled": filled,
                    "cost": cost
                })

            co = sorted(orders, key=lambda x: x["timestamp"], reverse=False)
            self._save_json("data/closed_orders.json", co)
            return co
        except Exception as e:
            logging.error(f"Error fetching closed orders: {e}")
            return []

    def fetch_completed_trades_with_pnl(self):
        """
        Fetch closed orders from the exchange. For each new closed order:
          - If it's a BUY, add a new FIFO layer to self.portfolio[symbol].
          - If it's a SELL, remove units from the oldest layer(s) in self.portfolio[symbol].
            Compute realized PnL for those sold units.

        The resulting trades are appended to self.completed_trades, and we
        save updated self.portfolio to 'data/portfolio.json' each time.
        """
        closed_orders = self.get_closed_orders()

        for order in closed_orders:
            order_id = order.get("id")
            if order_id is None or order_id in self.processed_order_ids:
                continue

            symbol = order["symbol"]
            side = order["side"]
            timestamp = order["timestamp"]

            # Exchange-provided data:
            filled = float(order.get("filled", 0))    # number of base units
            cost = float(order.get("cost", 0))        # total in quote currency (e.g. USDT)
            trade_price = float(order.get("priceAvg", 0))
            base_currency, quote_currency = symbol.split("/")

            # Skip if no real fill
            if filled <= 0:
                self.processed_order_ids.add(order_id)
                continue

            # -------------- BUY --------------
            if side == "buy":
                # If symbol not in portfolio, create an empty list
                if symbol not in self.portfolio:
                    self.portfolio[symbol] = []
                # Add a new FIFO layer
                self.portfolio[symbol].append({
                    "entry_price": trade_price,
                    "units": filled
                })

                # If there's a "USDT/EUR" entry, we adjust it to reflect spent USDT
                # But this logic is optional, depending on your usage
                if quote_currency == "USDT" and "USDT/EUR" in self.portfolio:
                    # E.g. self.portfolio["USDT/EUR"]["total_invested"] -= cost
                    pass

            # -------------- SELL --------------
            elif side == "sell":
                if symbol not in self.portfolio:
                    # No position to sell; ignore
                    self.processed_order_ids.add(order_id)
                    continue

                trades_list = self.portfolio[symbol]
                if not trades_list:
                    # Empty list means no open trades
                    self.processed_order_ids.add(order_id)
                    continue

                remaining_to_sell = filled
                realized_cost_basis = 0.0
                realized_pnl_usdt = 0.0
                sold_units_total = 0.0

                # FIFO: remove from the oldest
                i = 0
                while remaining_to_sell > 0 and i < len(trades_list):
                    layer = trades_list[i]
                    layer_units = layer["units"]
                    if layer_units <= 0:
                        i += 1
                        continue

                    if layer_units <= remaining_to_sell:
                        # Sell this entire layer
                        cost_basis_for_layer = layer["entry_price"] * layer_units
                        layer_pnl = layer_units * (trade_price - layer["entry_price"])

                        realized_cost_basis += cost_basis_for_layer
                        realized_pnl_usdt += layer_pnl
                        sold_units_total += layer_units

                        remaining_to_sell -= layer_units
                        layer["units"] = 0
                        i += 1
                    else:
                        # Partially sell this layer
                        cost_basis_sold = layer["entry_price"] * remaining_to_sell
                        pnl_sold = remaining_to_sell * (trade_price - layer["entry_price"])

                        realized_cost_basis += cost_basis_sold
                        realized_pnl_usdt += pnl_sold
                        sold_units_total += remaining_to_sell

                        layer["units"] -= remaining_to_sell
                        remaining_to_sell = 0

                # Remove empty layers
                trades_list = [t for t in trades_list if t["units"] > 1e-8]
                self.portfolio[symbol] = trades_list

                if sold_units_total > 0:
                    avg_buy_price_for_sold = realized_cost_basis / sold_units_total
                    pnl_percent = 0.0
                    if avg_buy_price_for_sold != 0:
                        pnl_percent = (trade_price - avg_buy_price_for_sold) / avg_buy_price_for_sold * 100.0

                    # Save the trade record
                    self.completed_trades.append({
                        "timestamp": timestamp,
                        "symbol": symbol,
                        "buy_price": round(avg_buy_price_for_sold, 6),
                        "sell_price": round(trade_price, 6),
                        "units_sold": round(sold_units_total, 6),
                        "cost_basis": round(realized_cost_basis, 2),
                        "pnl_usdt": round(realized_pnl_usdt, 2),
                        "pnl_percent": round(pnl_percent, 2)
                    })

                # If there's a "USDT/EUR" entry, we might add the USDT back (depending on your logic)
                if quote_currency == "USDT" and "USDT/EUR" in self.portfolio:
                    # e.g. self.portfolio["USDT/EUR"]["total_invested"] += realized_cost_basis
                    pass

            # Mark this order as processed
            self.processed_order_ids.add(order_id)

        # Sort completed trades by timestamp (oldest first) for readability
        self.completed_trades.sort(key=lambda x: x["timestamp"], reverse=False)

        # Save updated portfolio & trades
        self._save_json("data/completed_trades.json", self.completed_trades)
        self._save_json("data/portfolio.json", self.portfolio)

        return self.completed_trades

    def fetch_open_positions(self):
        """
        Rebuild a simple "open_positions" summary from self.portfolio in FIFO form.
        Summarize how many total units are held per symbol.
        """
        open_positions = []
        for symbol, trades_list in self.portfolio.items():
            total_units = sum(t["units"] for t in trades_list)
            if total_units > 0:
                # Weighted average entry price
                invested = sum(t["units"] * t["entry_price"] for t in trades_list)
                avg_price = invested / total_units if total_units > 0 else 0
                open_positions.append({
                    "symbol": symbol,
                    "size": round(total_units, 8),
                    "avg_price": round(avg_price, 8)
                })

        self._save_json("data/open_positions.json", open_positions)
        return open_positions

    def get_current_price(self, symbol):
        """Fetch the latest market price for the given symbol from the exchange."""
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

    def place_order(self, symbol, order_type, side, amount,
                    margin_mode=None, trade_side=None, price=None):
        """
        Place an order on the Bitget exchange (market or limit).
        For a market BUY, 'amount' is the QUOTE amount (e.g., USDT).
        For a market SELL, 'amount' is the BASE amount (e.g., BTC).
        """
        try:
            params = {}
            if margin_mode:
                params["marginMode"] = margin_mode
            if trade_side:
                params["tradeSide"] = trade_side

            if order_type == "market" and side == "buy":
                params["createMarketBuyOrderRequiresPrice"] = False
                order = self.exchange.create_order(
                    symbol=symbol,
                    type="market",
                    side=side,
                    amount=amount,  # QUOTE amount for market BUY
                    params=params
                )
            elif order_type == "market" and side == "sell":
                order = self.exchange.create_order(
                    symbol=symbol,
                    type="market",
                    side=side,
                    amount=amount,  # BASE amount for market SELL
                    params=params
                )
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

            logging.info(f"Order placed: {order}")
            order_id = order.get("id", None)
            return {"order_id": order_id, "status": order["status"]}

        except Exception as e:
            logging.error(f"Error placing order: {e}")
            return {"error": str(e)}

    def check_order_status(self, order_id, symbol):
        """
        Check the status of an order on the exchange.
        Possible returns: "open", "closed", "canceled", or "error".
        """
        try:
            order = self.exchange.fetch_order(order_id, symbol)
            return order.get("status", "unknown")
        except Exception as e:
            print(f"Error checking order status for {order_id}: {e}")
            return "error"
