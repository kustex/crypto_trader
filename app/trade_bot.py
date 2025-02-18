#!/usr/bin/env python
import json
import os
import logging
import yfinance as yf
from sqlalchemy import text
import pandas as pd

from app.database import DatabaseManager
from app.executor import TradeExecutor
from app.ui.api_credentials import load_api_credentials 

# Configure logging for the trade bot.
logging.basicConfig(
    level="INFO",
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("logs/trading_bot.log"),
              logging.StreamHandler()]
)
logger = logging.getLogger("TradeBot")

ALGORITHM_CONFIG_FILE = os.path.join("data", "algorithm_config.json")
API_KEY, API_SECRET, API_PASSPHRASE = load_api_credentials()

def load_algorithm_config():
    if os.path.exists(ALGORITHM_CONFIG_FILE):
        with open(ALGORITHM_CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

class TradeBot:
    """
    Executes trades based on risk parameters and generated signals.

    ----
    FIFO Implementation:
      The portfolio is stored as:
        self.trade_executor.portfolio[symbol] = [
            { "entry_price": <float>, "units": <float> },
            { "entry_price": <float>, "units": <float> },
            ...
        ]
      Each BUY creates a new "trade layer". SELL orders remove units FIFO.
      Stoploss is checked individually per trade, so only those below threshold are closed.
    """

    def __init__(self):
        self.db_manager = DatabaseManager()
        self.trade_executor = TradeExecutor(API_KEY, API_SECRET, API_PASSPHRASE)

        # For signal-based trading, track the timestamp of the last executed signal per symbol.
        self.last_executed_signal_timestamp = {}
        # The signal-based cycle is assumed to work on 15-minute signals.
        self.signal_cycle_interval = 60 * 60  # seconds

    def get_total_capital(self):
        """
        Return a tuple (total_capital, free_usdt) where:
          - total_capital is the sum (in USDT) of every asset's value.
          - free_usdt is the available USDT balance.
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
                try:
                    ticker_yf = yf.Ticker("EURUSD=X")
                    data = ticker_yf.history(period="1d", interval="1m")
                    if data.empty:
                        raise Exception("No data available for EUR/USD")
                    eur_usd_rate = data['Close'].iloc[-1]
                    total_capital += balance * eur_usd_rate
                except Exception as e:
                    logger.error(f"Error fetching EUR/USD rate: {e}")
            else:
                pair = f"{symbol}/USDT"
                try:
                    price = self.trade_executor.get_current_price(pair)
                    if price is None:
                        raise Exception("Price not available")
                    total_capital += balance * price
                except Exception as e:
                    logger.error(f"Error fetching price for {pair}: {e}")
        return total_capital, free_usdt

    def fetch_active_symbols(self):
        """Return a list of active ticker symbols from the database."""
        tickers_df = self.db_manager.fetch_tickers()
        if tickers_df is not None and not tickers_df.empty:
            return tickers_df["symbol"].tolist()
        return []

    def get_open_position(self, symbol):
        """
        Aggregates all trade layers for this symbol, returning a dict:
          { "symbol": str, "total_invested": float, "units": float, "avg_price": float }
        If no trades are open, returns None.
        """
        trades_list = self.trade_executor.portfolio.get(symbol, [])
        if not trades_list:
            return None

        total_invested = 0.0
        total_units = 0.0
        for trade in trades_list:
            total_invested += trade["entry_price"] * trade["units"]
            total_units += trade["units"]

        if total_units <= 0:
            return None

        avg_buy_price = total_invested / total_units
        return {
            "symbol": symbol,
            "total_invested": total_invested,
            "units": total_units,
            "avg_price": avg_buy_price
        }

    def fetch_latest_signal(self, symbol, timeframe="1h"):
        """
        Fetch the latest signal for a given symbol and timeframe from the signals_data table.
        Returns a dictionary with keys: timestamp, symbol, timeframe, keltner_signal,
        rvi_signal, rvi_signal_15m, final_signal.
        """
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
            keys = ["timestamp", "symbol", "timeframe", "keltner_signal", "rvi_signal", "rvi_signal_15m", "final_signal"]
            result = dict(zip(keys, result))
        return result

    def get_available_asset_balance(self, symbol):
        """
        Fetch the available balance for the given base asset from the exchange.
        The symbol is assumed to be in the form 'DOGE/USDT', so this returns the available DOGE.
        """
        try:
            balance_data = self.trade_executor.get_account_balance()
            # Look for the base asset (e.g., "DOGE") in the balance data.
            for asset in balance_data:
                if asset["symbol"].upper() == symbol.split("/")[0]:
                    return asset["available"]
            return 0.0
        except Exception as e:
            logger.error(f"Error fetching available balance for {symbol}: {e}")
            return 0.0

    def execute_risk_management_for_symbol(self, symbol):
        """
        Check if any trade layer has price < entry_price * (1 - stoploss).
        If so, that entire layer is closed (FIFO concept is simply that each layer is handled individually).
        """
        current_price = self.trade_executor.get_current_price(symbol)
        if current_price is None:
            logger.warning(f"Risk management: Could not fetch current price for {symbol}.")
            return

        trades_list = self.trade_executor.portfolio.get(symbol, [])
        if not trades_list:
            return

        risk_params = self.db_manager.fetch_risk_params(symbol)
        if not risk_params:
            logger.warning(f"Risk management: No risk parameters for {symbol}.")
            return

        stoploss = risk_params[0]  # e.g., 0.10 means 10% drop

        # Evaluate each trade for stoploss
        indexes_to_sell = []
        for i, trade in enumerate(trades_list):
            stoploss_threshold = trade["entry_price"] * (1 - stoploss)
            if current_price < stoploss_threshold:
                indexes_to_sell.append(i)

        # Sell each trade that breaks the stoploss threshold
        # in descending order (to not break indexing)
        for i in sorted(indexes_to_sell, reverse=True):
            units_to_sell = trades_list[i]["units"]
            if units_to_sell > 0:
                logger.info(
                    f"Risk management for {symbol}: Trade layer at entry={trades_list[i]['entry_price']:.4f} "
                    f"triggered stoploss. Selling {units_to_sell:.4f} units."
                )
                self.execute_sell_order(symbol, units_to_sell)

    def execute_signal_based_trading_for_symbol(self, symbol):
        """
        For the given symbol, check if a new 15m signal is available.
        If so, handle BUY or SELL based on final_signal.
        Only trade if the algorithm is enabled for this symbol in the config.
        """
        config = load_algorithm_config()
        if not config.get(symbol, False):
            logger.info(f"Algorithm disabled for {symbol}. Skipping signal-based trading.")
            return

        signal = self.fetch_latest_signal(symbol, timeframe="1h")
        if signal is None:
            logger.info(f"Signal-based trading for {symbol}: No signal found.")
            return

        signal_timestamp = signal["timestamp"]
        if symbol in self.last_executed_signal_timestamp and signal_timestamp <= self.last_executed_signal_timestamp[symbol]:
            return

        final_signal = signal["final_signal"]
        logger.info(f"Signal-based trading for {symbol}: New signal received with final_signal = {final_signal}")

        total_capital, free_usdt = self.get_total_capital()
        if total_capital is None:
            logger.warning("Signal-based trading: Total capital not available.")
            return

        risk_params = self.db_manager.fetch_risk_params(symbol)
        if not risk_params:
            logger.warning(f"Signal-based trading: No risk parameters for {symbol}.")
            return
        stoploss, position_size_pct, max_allocation_pct, partial_sell_fraction = risk_params

        current_price = self.trade_executor.get_current_price(symbol)
        if current_price is None:
            logger.warning(f"Signal-based trading for {symbol}: Could not fetch current price.")
            return

        # Summarize open position for this symbol (if any)
        position = self.get_open_position(symbol)
        current_allocation = position["total_invested"] if position else 0

        max_allocation_amount = total_capital * max_allocation_pct
        desired_order_amount = total_capital * position_size_pct

        if final_signal == 1:  # BUY
            if current_allocation < max_allocation_amount:
                order_value = desired_order_amount
                # If partially allocated, be sure not to exceed the maximum
                if (current_allocation + order_value) > max_allocation_amount:
                    order_value = max_allocation_amount - current_allocation
                # Also ensure we don't exceed free_usdt
                if order_value > free_usdt:
                    order_value = free_usdt

                if order_value > 0:
                    logger.info(f"Signal-based trading for {symbol}: Placing BUY for {order_value:.2f} USDT.")
                    self.execute_buy_order(symbol, order_value)
                else:
                    logger.info(f"Signal-based trading for {symbol}: Insufficient free USDT to BUY.")
            else:
                logger.info(f"Signal-based trading for {symbol}: Position at or above max allocation.")
        elif final_signal == -1:  # SELL
            trades_list = self.trade_executor.portfolio.get(symbol, [])
            total_units = sum(t["units"] for t in trades_list)
            if total_units > 0:
                # We do partial sells with FIFO
                units_to_sell = total_units * partial_sell_fraction
                logger.info(f"Signal-based trading for {symbol}: SELL signal => partial sell of {units_to_sell:.4f} units.")
                self.execute_sell_order(symbol, units_to_sell)
            else:
                logger.info(f"Signal-based trading for {symbol}: No open position to SELL on signal.")

        self.last_executed_signal_timestamp[symbol] = signal_timestamp

    def execute_buy_order(self, symbol, order_value_usdt):
        """
        Execute a market BUY order for the given symbol using the specified USDT order value.
        Adds a new 'trade layer' (FIFO entry).
        """
        current_price = self.trade_executor.get_current_price(symbol)
        if current_price is None:
            logger.warning(f"execute_buy_order: Could not fetch price for {symbol}.")
            return None

        if order_value_usdt <= 0:
            logger.warning("execute_buy_order: order_value_usdt <= 0.")
            return None

        purchased_units = order_value_usdt / current_price

        # Place the actual market order on the exchange
        response = self.trade_executor.place_order(
            symbol=symbol,
            order_type="market",
            side="buy",
            amount=order_value_usdt
        )
        logger.info(f"Executed BUY order for {symbol}: {response}")

        # Store the new trade in FIFO style
        if symbol not in self.trade_executor.portfolio:
            self.trade_executor.portfolio[symbol] = []
        self.trade_executor.portfolio[symbol].append({
            "entry_price": current_price,
            "units": purchased_units
        })

        return response

    def execute_sell_order(self, symbol, sell_units):
        """
        Execute a market SELL order for 'sell_units' of base asset in FIFO order.
        Decrements or removes trades from the oldest to newest.
        """
        current_price = self.trade_executor.get_current_price(symbol)
        if current_price is None:
            logger.warning(f"execute_sell_order: Could not fetch price for {symbol}.")
            return None

        if sell_units <= 0:
            logger.warning("execute_sell_order: sell_units <= 0.")
            return None

        # Place the actual market order
        response = self.trade_executor.place_order(
            symbol=symbol,
            order_type="market",
            side="sell",
            amount=sell_units
        )
        logger.info(f"Executed SELL order for {symbol}: {response}")

        trades_list = self.trade_executor.portfolio.get(symbol, [])
        if not trades_list:
            return response

        remaining_to_sell = sell_units

        # FIFO: reduce from the oldest trades
        for i in range(len(trades_list)):
            if remaining_to_sell <= 0:
                break
            trade = trades_list[i]
            if trade["units"] <= remaining_to_sell:
                # Sell all units of this layer
                remaining_to_sell -= trade["units"]
                trade["units"] = 0
            else:
                # Sell only partial
                trade["units"] -= remaining_to_sell
                remaining_to_sell = 0

        # Remove empty layers
        trades_list = [t for t in trades_list if t["units"] > 1e-8]
        self.trade_executor.portfolio[symbol] = trades_list

        return response
