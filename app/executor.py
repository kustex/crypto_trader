import ccxt
import logging
import os


class TradeExecutor:
    """
    A class to interact with the Bitget exchange using CCXT for trading.
    """

    def __init__(self, api_key, api_secret, passphrase, testnet=True):
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

        # Setup logging
        self._setup_logging()

    def _setup_logging(self):
        """Configure logging for trade execution."""
        logging.basicConfig(
            filename="logs/trading_log.txt",
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s"
        )

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
                    amount=amount,  # amount is treated as cost
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
            return order
        except Exception as e:
            logging.error(f"Error placing order: {e}")
            return {"error": str(e)}

# Test the TradeExecutor
if __name__ == "__main__":
    API_KEY = os.getenv("BITGET_API_KEY")
    API_SECRET = os.getenv("BITGET_API_SECRET")
    API_PASSPHRASE = os.getenv("BITGET_API_PASSPHRASE")

    # Initialize the executor
    executor = TradeExecutor(API_KEY, API_SECRET, API_PASSPHRASE, testnet=False)

    # symbol = "USDT/EUR"  
    symbol = "BTC/USDT"  

    # Place a market order
    print("Placing a market order...")
    order = executor.place_order(
        symbol=symbol,
        order_type="limit",
        side="buy",
        amount=float(0.00002),
        price=95000
    )


