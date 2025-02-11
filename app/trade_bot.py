# trade_bot.py
import os
import time
import logging
import threading
import yfinance as yf 
from datetime import datetime, timezone
from sqlalchemy import text

import pandas as pd

from app.database import DatabaseManager
from app.executor import TradeExecutor

# Configure logging for the trade bot
LOG_LEVEL = "INFO"
LOG_FILE = "logs/trading_bot.log"
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE),
              logging.StreamHandler()
    ]
)
logger = logging.getLogger("TradeBot")

class TradeBot:
    """
    Executes trades based on risk parameters and generated signals.
    
    Decision logic:
      - For each active symbol, use the 1h signal:
          * If final_signal == 1 (BUY):
              - If no open position: buy an amount equal to (position size % × total capital),
                but not exceeding (max allocation % × total capital).
              - If an open position exists and its allocation (in USDT) is below max allocation,
                add additional buy order for the minimum of (position size % × total capital)
                or the difference needed to reach max allocation.
          * If final_signal == -1 (SELL):
              - If an open position exists: sell partial_sell_fraction of the position.
      - Regardless of signal, if a position is open and the current price falls below
        (entry_price × (1 - stoploss)), then sell the entire position.
    """
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.trade_executor = TradeExecutor(
            os.getenv("BITGET_API_KEY"),
            os.getenv("BITGET_API_SECRET"),
            os.getenv("BITGET_API_PASSPHRASE")
        )
        # Run risk management cycle every 60 seconds.
        self.risk_cycle_interval = 60  
        # Run signal-based cycle every 15 minutes.
        self.signal_cycle_interval = 15 * 60  
        # Store the last executed signal timestamp per symbol
        self.last_executed_signal_timestamp = {}

    def get_total_capital(self):
        """
        Return a tuple (total_capital, free_usdt) where:
        - total_capital is the sum (in USDT) of the USDT value of every asset in your account.
        - free_usdt is the amount of USDT that is free (available) for new orders.
        """
        balances = self.trade_executor.get_account_balance()
        total_capital = 0.0
        free_usdt = 0.0

        for asset in balances:
            symbol = asset["symbol"].upper()
            balance = asset["balance"]
            available = asset["available"]

            if symbol == "USDT":
                total_capital += balance
                free_usdt = available
            elif symbol == "EUR":
                # Use Yahoo Finance to fetch the EUR/USD conversion rate.
                try:
                    ticker_yf = yf.Ticker("EURUSD=X")
                    # Fetch recent data; here we request a 1-day history with a 1-minute interval.
                    data = ticker_yf.history(period="1d", interval="1m")
                    if data.empty:
                        raise Exception("No data available for EUR/USD")
                    eur_usd_rate = data['Close'].iloc[-1]
                    asset_value = balance * eur_usd_rate
                    total_capital += asset_value
                except Exception as e:
                    logging.error(f"Error fetching EUR/USD rate from Yahoo Finance: {e}")
            else:
                # For all other assets, assume a conversion pair of SYMBOL/USDT exists.
                pair = f"{symbol}/USDT"
                try:
                    price = self.trade_executor.get_current_price(pair)
                    if price is None:
                        raise Exception("Price not available")
                    asset_value = balance * price
                    total_capital += asset_value
                except Exception as e:
                    logging.error(f"Error fetching price for {pair}: {e}")
        return total_capital, free_usdt

    def fetch_active_symbols(self):
        """Return a list of active ticker symbols from the database."""
        tickers_df = self.db_manager.fetch_tickers()
        if tickers_df is not None and not tickers_df.empty:
            return tickers_df["symbol"].tolist()
        return []

    def fetch_latest_signal(self, symbol, timeframe="1h"):
        query = text("""
            SELECT timestamp, symbol, timeframe, keltner_signal, rvi_signal, rvi_signal_15m, final_signal
            FROM signals_data
            WHERE symbol = :symbol AND timeframe = :timeframe
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        with self.db_manager.engine.connect() as connection:
            result = connection.execute(query, {"symbol": symbol, "timeframe": timeframe}).fetchone()
        if result is not None:
            # Adjust the keys according to your SELECT statement order.
            keys = ["timestamp", "symbol", "timeframe", "keltner_signal", "rvi_signal", "rvi_signal_15m", "final_signal"]
            result = dict(zip(keys, result))
        return result

    def get_open_position(self, symbol):
        """
        Return the open position for the given symbol from the trade executor.
        Assumes trade_executor.fetch_open_positions() returns a list of dicts with key "symbol".
        """
        positions = self.trade_executor.fetch_open_positions()
        for pos in positions:
            if pos["symbol"] == symbol:
                return pos
        return None

    def execute_risk_management(self):
        """
        Check each open position for risk thresholds (e.g. stoploss) and, if exceeded,
        sell the entire position.
        This function runs every minute.
        """
        symbols = self.fetch_active_symbols()
        for symbol in symbols:
            # Get current market price.
            current_price = self.trade_executor.get_current_price(symbol)
            if current_price is None:
                logging.warning(f"Could not fetch current price for {symbol} in risk management.")
                continue

            # Get current open position (if any)
            position = self.get_open_position(symbol)
            if not position:
                continue

            current_allocation = position["size"]  # in USDT
            entry_price = position["avg_price"]

            # Fetch risk parameters for the symbol.
            risk_params = self.db_manager.fetch_risk_params(symbol)
            if not risk_params:
                logging.warning(f"No risk parameters for {symbol} in risk management.")
                continue

            stoploss, _, _, _ = risk_params

            # Check if the current price is below the threshold.
            stoploss_threshold = entry_price * (1 - stoploss)
            if current_price < stoploss_threshold:
                # Sell the entire position.
                sell_amount_base = current_allocation / current_price
                logging.info(f"Risk management: Stoploss triggered for {symbol}: current price {current_price} < threshold {stoploss_threshold}. Selling entire position.")
                self.execute_sell_order(symbol, sell_amount_base)
                # Optionally update internal state, etc.

    def execute_signal_based_trading(self):
        """
        For each active symbol, check if a new 15-minute signal is available.
        If so, execute a buy (or sell) order based on that signal using the core order execution.
        This function should only trigger new orders when the signal is new.
        """
        symbols = self.fetch_active_symbols()
        total_capital, free_usdt = self.get_total_capital()
        if total_capital is None:
            logging.warning("Total capital could not be determined in signal cycle.")
            return

        for symbol in symbols:
            # Fetch the latest 15m signal.
            signal = self.fetch_latest_signal(symbol, timeframe="15m")
            # if symbol == 'BTC/USDT':
            #     signal['final_signal'] = 1

            if signal is None:
                logging.info(f"No 15m signal for {symbol}.")
                continue

            signal_timestamp = signal["timestamp"]
            # Only execute if the signal is new.
            if symbol in self.last_executed_signal_timestamp and signal_timestamp <= self.last_executed_signal_timestamp[symbol]:
                continue

            final_signal = signal["final_signal"]
            logging.info(f"Signal-based trading: New signal for {symbol}: final_signal = {final_signal}")

            # Fetch risk parameters.
            risk_params = self.db_manager.fetch_risk_params(symbol)
            if not risk_params:
                logging.warning(f"No risk parameters for {symbol} in signal-based trading.")
                continue
            stoploss, position_size_pct, max_allocation_pct, partial_sell_fraction = risk_params

            desired_order_amount = total_capital * position_size_pct
            max_allocation_amount = total_capital * max_allocation_pct

            current_price = self.trade_executor.get_current_price(symbol)
            if current_price is None:
                logging.warning(f"Could not fetch current price for {symbol} in signal-based trading.")
                continue

            # Get current open position (if any)
            position = self.get_open_position(symbol)
            if position:
                current_allocation = position["size"]  # in USDT
            else:
                current_allocation = 0

            if final_signal == 1:  # BUY signal
                if current_allocation < max_allocation_amount:
                    # Determine order amount: for a new position, it's desired_order_amount; for adding,
                    # it’s the minimum of desired_order_amount and the difference to reach max allocation.
                    order_value = desired_order_amount if current_allocation == 0 else min(desired_order_amount, max_allocation_amount - current_allocation)
                    # Check free USDT availability.
                    if free_usdt < order_value:
                        order_value = free_usdt
                    if order_value > 0:
                        logging.info(f"Signal-based trading: Placing BUY order for {symbol} for {order_value} USDT.")
                        self.execute_buy_order(symbol, order_value)
                    else:
                        logging.info(f"Signal-based trading: Insufficient free USDT to place BUY order for {symbol}.")
                else:
                    logging.info(f"Signal-based trading: Position for {symbol} is at or above max allocation ({current_allocation} USDT).")
            elif final_signal == -1:  # SELL signal
                if current_allocation > 0:
                    sell_value_usdt = current_allocation * partial_sell_fraction
                    sell_amount_base = sell_value_usdt / current_price
                    logging.info(f"Signal-based trading: Placing SELL order for {symbol}: selling {sell_value_usdt} USDT worth (~{sell_amount_base} units).")
                    self.execute_sell_order(symbol, sell_amount_base)
                else:
                    logging.info(f"Signal-based trading: No open position for {symbol} to sell on SELL signal.")

            # Record that we executed a signal-based order for this signal.
            self.last_executed_signal_timestamp[symbol] = signal_timestamp

    def execute_buy_order(self, symbol, order_value_usdt):
        """
        Core function to execute a market BUY order using the trade_executor,
        without UI updates.
        """
        # response = self.trade_executor.place_order(
        #     symbol=symbol,
        #     order_type="market",
        #     side="buy",
        #     amount=order_value_usdt  # interpreted as cost in USDT.
        # )
        # logging.info(f"Executed BUY order for {symbol}: {response}")
        logging.info(f"Executed BUY order for {symbol}:")
        # return response

    def execute_sell_order(self, symbol, sell_amount_base):
        """
        Core function to execute a market SELL order using the trade_executor,
        without UI updates.
        """
        # response = self.trade_executor.place_order(
        #     symbol=symbol,
        #     order_type="market",
        #     side="sell",
        #     amount=sell_amount_base  # amount in base currency.
        # )
        # logging.info(f"Executed SELL order for {symbol}: {response}")
        logging.info(f"Executed SELL order for {symbol}:")
        # return response

    def execute_trade_cycle(self):
        """
        Run the risk management check (every minute) and, separately, run the
        signal-based trading cycle (every 15 minutes). This method can be called
        by separate scheduler threads or by a main loop that sleeps for the appropriate interval.
        """
        # For example, if this method is run every minute, first perform risk management:
        self.execute_risk_management()

        # Then, if it is time for signal-based trading (e.g. every 15 minutes),
        # you can check the current time:
        now = datetime.now(timezone.utc).timestamp()
        # Suppose you store the last time you executed signal-based trading:
        if not hasattr(self, "last_signal_trade_time"):
            self.last_signal_trade_time = 0

        if now - self.last_signal_trade_time >= self.signal_cycle_interval:
            self.execute_signal_based_trading()
            self.last_signal_trade_time = now

    def run(self):
        """Continuously run the trade cycle (risk management every minute, signal trading every 15 minutes)."""
        logging.info("Starting TradeBot...")
        while True:
            try:
                self.execute_trade_cycle()
            except Exception as e:
                logging.error(f"Error during trade cycle: {e}", exc_info=True)
            # Sleep 60 seconds between cycles (risk management is run every minute)
            time.sleep(self.risk_cycle_interval)


if __name__ == "__main__":
    # Run the trade bot in a separate thread (or standalone)
    trade_bot = TradeBot()
    trade_thread = threading.Thread(target=trade_bot.run, daemon=True)
    trade_thread.start()

    # Keep the main thread alive.
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("TradeBot shutting down gracefully...")
