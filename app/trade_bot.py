#!/usr/bin/env python
import os
import time
import logging
import yfinance as yf
from sqlalchemy import text
import pandas as pd

from app.database import DatabaseManager
from app.executor import TradeExecutor

# Configure logging for the trade bot.
logging.basicConfig(
    level="INFO",
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("logs/trading_bot.log"),
              logging.StreamHandler()]
)
logger = logging.getLogger("TradeBot")


class TradeBot:
    """
    Executes trades based on risk parameters and generated signals.

    Portfolio state is stored in JSON as:
      { "SYMBOL": { "total_invested": <USDT>, "units": <number of units> }, ... }

    Core logic:
      - Risk management: For each open position, if the current price falls below 
        (avg_buy_price × (1 - stoploss)), trigger a full sell (selling all held units).
      - Signal-based trading: When a new 15m signal is available (tracked per symbol),
        if final_signal == 1 (BUY) then attempt to add to the position (subject to free USDT and max allocation),
        and if final_signal == -1 (SELL) then sell a fraction of the current units.
    """
    def __init__(self):
        self.db_manager = DatabaseManager()
        self.trade_executor = TradeExecutor(
            os.getenv("BITGET_API_KEY"),
            os.getenv("BITGET_API_SECRET"),
            os.getenv("BITGET_API_PASSPHRASE")
        )
        # For signal-based trading, track the timestamp of the last executed signal per symbol.
        self.last_executed_signal_timestamp = {}
        # The signal-based cycle is assumed to work on 15-minute signals.
        self.signal_cycle_interval = 15 * 60  # seconds

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
        Return the open position for the given symbol.
        The portfolio is stored as { symbol: { "total_invested": ..., "units": ... } }.
        The average buy price is computed as total_invested / units.
        """
        portfolio = self.trade_executor.portfolio
        if symbol in portfolio:
            pos = portfolio[symbol]
            units = pos.get("units", 0)
            total_invested = pos.get("total_invested", 0)
            avg_buy_price = total_invested / units if units > 0 else 0
            return {"symbol": symbol, "total_invested": total_invested, "units": units, "avg_price": avg_buy_price}
        return None

    def fetch_latest_signal(self, symbol, timeframe="15m"):
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
        For the given symbol, check if the current open position's stoploss condition is met.
        Compute the average buy price as total_invested / units.
        If current price < avg_buy_price × (1 - stoploss), execute a full sell.
        """
        current_price = self.trade_executor.get_current_price(symbol)
        if current_price is None:
            logger.warning(f"Risk management: Could not fetch current price for {symbol}.")
            return

        position = self.get_open_position(symbol)
        if not position:
            return

        total_invested = position['total_invested']
        avg_buy_price = position["avg_price"]
        risk_params = self.db_manager.fetch_risk_params(symbol)
        if not risk_params:
            logger.warning(f"Risk management: No risk parameters for {symbol}.")
            return

        stoploss = risk_params[0]  # e.g., 0.10 means 10% drop allowed
        stoploss_threshold = avg_buy_price * (1 - stoploss)
        logger.info(f"Risk management for {symbol}: total invested={total_invested} avg_buy_price={avg_buy_price}, threshold={stoploss_threshold:.2f}, current_price={current_price:.2f}")

        if current_price < stoploss_threshold:
            # Before placing the sell order, check the actual available balance for the asset.
            base_asset = symbol.split("/")[0]
            available_balance = self.get_available_asset_balance(symbol)
            # Our internal position holds a certain number of units.
            internal_units = position["units"]
            # We take the minimum of our internal units and the available balance.
            units_to_sell = min(internal_units, available_balance)
            if units_to_sell <= 0:
                logger.warning(f"Risk management: Available balance for {symbol} is insufficient ({available_balance} units).")
                return
            logger.info(f"Risk management: Stoploss triggered for {symbol}. Selling {units_to_sell:.4f} units (internal: {internal_units:.4f} units, available: {available_balance:.4f} units).")
            self.execute_sell_order(symbol, units_to_sell)

    def execute_signal_based_trading_for_symbol(self, symbol):
        """
        For the given symbol, check if a new 15m signal is available.
        If so, execute a BUY order (if final_signal == 1) or a partial SELL (if final_signal == -1)
        based on risk parameters.
        """
        signal = self.fetch_latest_signal(symbol, timeframe="15m")
        if signal is None:
            logger.info(f"Signal-based trading for {symbol}: No signal found.")
            return

        signal_timestamp = signal["timestamp"]
        if symbol in self.last_executed_signal_timestamp and signal_timestamp <= self.last_executed_signal_timestamp[symbol]:
            # Signal not new; do nothing.
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
        # risk_params: (stoploss, position_size_pct, max_allocation_pct, partial_sell_fraction)
        _ , position_size_pct, max_allocation_pct, partial_sell_fraction = risk_params

        desired_order_amount = total_capital * position_size_pct
        max_allocation_amount = total_capital * max_allocation_pct

        current_price = self.trade_executor.get_current_price(symbol)
        if current_price is None:
            logger.warning(f"Signal-based trading for {symbol}: Could not fetch current price.")
            return

        position = self.get_open_position(symbol)
        current_allocation = position["total_invested"] if position else 0

        if final_signal == 1:  # BUY signal
            if current_allocation < max_allocation_amount:
                order_value = desired_order_amount if current_allocation == 0 else min(desired_order_amount, max_allocation_amount - current_allocation)
                if free_usdt < order_value:
                    order_value = free_usdt
                if order_value > 0:
                    logger.info(f"Signal-based trading for {symbol}: Placing BUY order for {order_value} USDT.")
                    self.execute_buy_order(symbol, order_value)
                else:
                    logger.info(f"Signal-based trading for {symbol}: Insufficient free USDT to BUY.")
            else:
                logger.info(f"Signal-based trading for {symbol}: Position is at or above max allocation ({current_allocation} USDT).")
        elif final_signal == -1:  # SELL signal
            if position:
                # Sell a fraction of the current units.
                sell_units = position["units"] * partial_sell_fraction
                logger.info(f"Signal-based trading for {symbol}: Placing SELL order for {sell_units} units (partial sell).")
                self.execute_sell_order(symbol, sell_units)
            else:
                logger.info(f"Signal-based trading for {symbol}: No open position to SELL on signal.")

        # Record the timestamp of the signal we just acted on.
        self.last_executed_signal_timestamp[symbol] = signal_timestamp

    def execute_buy_order(self, symbol, order_value_usdt):
        """
        Execute a market BUY order for the given symbol using the specified USDT order value.
        The order value is interpreted as the USDT amount to spend.
        """
        response = self.trade_executor.place_order(
            symbol=symbol,
            order_type="market",
            side="buy",
            amount=order_value_usdt
        )
        logger.info(f"Executed BUY order for {symbol}: {response}")
        return response

    def execute_sell_order(self, symbol, sell_units):
        """
        Execute a market SELL order for the given symbol using the specified number of units.
        The amount is interpreted in base currency units.
        """
        response = self.trade_executor.place_order(
            symbol=symbol,
            order_type="market",
            side="sell",
            amount=sell_units
        )
        logger.info(f"Executed SELL order for {symbol}: {response}")
        return response

