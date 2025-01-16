import logging
import os

class PortfolioManager:
    """
    Handles portfolio management, including risk management and position sizing.
    """

    def __init__(self, trade_executor, risk_per_trade=0.01):
        """
        Initialize the portfolio manager.

        :param trade_executor: Instance of the TradeExecutor class for API interactions.
        :param risk_per_trade: Percentage of portfolio to risk per trade (e.g., 0.01 for 1%).
        """
        self.trade_executor = trade_executor
        self.risk_per_trade = risk_per_trade
        self.positions = {}  # To track open positions
        self._setup_logging()

    def _setup_logging(self):
        """
        Configure logging for portfolio management.
        """
        logging.basicConfig(
            filename="logs/portfolio_log.txt",
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s"
        )

    def fetch_portfolio_balance(self):
        """
        Fetch the current portfolio balance.
        :return: Total account balance in the base currency.
        """
        balance = self.trade_executor.fetch_balance()
        if "error" in balance:
            logging.error(f"Error fetching balance: {balance['error']}")
            return None
        return balance.get('total', {}).get('USDT', 0)  

    def calculate_position_size(self, stop_loss_pct, balance=None):
        """
        Calculate position size based on risk per trade and stop loss percentage.

        :param stop_loss_pct: Stop loss percentage for the trade (e.g., 0.02 for 2%).
        :param balance: Optional; current account balance. If None, it will be fetched.
        :return: Position size in the trading pair's base currency.
        """
        if balance is None:
            balance = self.fetch_portfolio_balance()
            if balance is None:
                logging.error("Failed to fetch portfolio balance. Cannot calculate position size.")
                return None

        risk_amount = balance * self.risk_per_trade
        if stop_loss_pct <= 0:
            logging.error("Invalid stop loss percentage. Must be greater than zero.")
            return None

        position_size = risk_amount / stop_loss_pct
        logging.info(f"Calculated position size: {position_size} for stop loss {stop_loss_pct}")
        return position_size

    def open_position(self, symbol, side, stop_loss_pct, price=None):
        """
        Open a new position.

        :param symbol: Trading pair (e.g., "BTC/USDT").
        :param side: "buy" or "sell".
        :param stop_loss_pct: Stop loss percentage for the trade.
        :param price: Optional; price for limit orders.
        :return: Order response.
        """
        position_size = self.calculate_position_size(stop_loss_pct)
        if position_size is None:
            logging.error("Failed to calculate position size. Aborting trade.")
            return None

        order_type = "market" if price is None else "limit"
        order = self.trade_executor.place_order(symbol, order_type, side, position_size, price=price)
        
        if "error" not in order:
            self.positions[symbol] = {
                "side": side,
                "size": position_size,
                "entry_price": price or order.get("price"),
                "stop_loss_pct": stop_loss_pct,
            }
            logging.info(f"Opened position: {self.positions[symbol]}")
        else:
            logging.error(f"Failed to open position: {order['error']}")
        return order

    def close_position(self, symbol):
        """
        Close an existing position.

        :param symbol: Trading pair of the position to close.
        :return: Order response.
        """
        position = self.positions.get(symbol)
        if not position:
            logging.error(f"No open position found for {symbol}")
            return None

        side = "sell" if position["side"] == "buy" else "buy"
        order = self.trade_executor.place_order(symbol, "market", side, position["size"])
        
        if "error" not in order:
            logging.info(f"Closed position: {symbol}")
            del self.positions[symbol]
        else:
            logging.error(f"Failed to close position: {order['error']}")
        return order

    def monitor_positions(self):
        """
        Monitor open positions and log unrealized P&L.
        """
        for symbol, position in self.positions.items():
            ticker_data = self.trade_executor.exchange.fetch_ticker(symbol)
            current_price = ticker_data.get("last")
            if current_price is None:
                logging.warning(f"Failed to fetch price for {symbol}")
                continue

            entry_price = position["entry_price"]
            side = position["side"]
            size = position["size"]

            unrealized_pnl = (current_price - entry_price) * size if side == "buy" else (entry_price - current_price) * size
            logging.info(f"Unrealized P&L for {symbol}: {unrealized_pnl}")

    def fetch_open_positions(self):
        """
        Retrieve a summary of all open positions.
        :return: Dictionary of open positions.
        """
        return self.positions


if __name__ == "__main__":
    from app.executor import TradeExecutor

    API_KEY = os.getenv("BITGET_API_KEY")
    API_SECRET = os.getenv("BITGET_API_SECRET")
    API_PASSPHRASE = os.getenv("BITGET_API_PASSPHRASE")

    # Initialize TradeExecutor
    executor = TradeExecutor(API_KEY, API_SECRET, API_PASSPHRASE, testnet=False)

    # Initialize PortfolioManager
    portfolio_manager = PortfolioManager(trade_executor=executor, risk_per_trade=0.01)

    # Fetch balance
    print("Fetching portfolio balance...")
    balance = portfolio_manager.fetch_portfolio_balance()
    print(f"Balance: {balance}")

    # # Open a position
    # print("Opening a position...")
    # open_order = portfolio_manager.open_position(symbol="BTC/USDT", side="buy", stop_loss_pct=0.02)
    # print(f"Open Order Response: {open_order}")

    # # Monitor positions
    # print("Monitoring positions...")
    # portfolio_manager.monitor_positions()

    # # Close the position
    # print("Closing the position...")
    # close_order = portfolio_manager.close_position(symbol="BTC/USDT")
    # print(f"Close Order Response: {close_order}")
