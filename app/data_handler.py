#!/usr/bin/env python
import sys
import ccxt
import logging
import pandas as pd
import schedule
import time
import threading
import os
from typing import List, Optional, Tuple
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta, timezone
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from concurrent.futures import ThreadPoolExecutor, as_completed

# Define your local timezone (UTC+1)
LOCAL_TZ = timezone(timedelta(hours=1))

# Import your DatabaseManager and SignalGenerator from your project.
from app.database import DatabaseManager
from app.controllers.signal_generator import SignalGenerator
from app.trade_bot import TradeBot

# Configure logging for the data handler and updater
LOG_LEVEL = "INFO"
LOG_FILE = "logs/crypto_bot.log"
logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE),
              logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

class DataHandler:
    """Handles fetching, validation, and storage of historical crypto data."""
    EXCHANGE_NAME = "binance"
    API_TIMEOUT = 30000  # 30 seconds
    API_RATE_LIMIT = 1200  # Requests per minute
    MAX_RETRIES = 5
    LOOKBACK_DAYS = 365
    MAX_WORKERS = 10
    
    def __init__(self, exchange_name: str = EXCHANGE_NAME, lookback_days: int = LOOKBACK_DAYS):
        self.exchange_name = exchange_name
        self.lookback_days = lookback_days
        self.exchange = self._initialize_exchange()
        self.db_manager = DatabaseManager()
        self.db_manager.initialize_database()

    def _initialize_exchange(self) -> ccxt.Exchange:
        """Initialize and configure the exchange instance."""
        exchange_class = getattr(ccxt, self.exchange_name)
        return exchange_class({
            "enableRateLimit": True,
            "timeout": self.API_TIMEOUT,
            "rateLimit": self.API_RATE_LIMIT
        })

    @retry(
        stop=stop_after_attempt(MAX_RETRIES),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ccxt.NetworkError, ccxt.RequestTimeout)),
        before_sleep=lambda retry_state: logger.warning(
            f"Retry attempt {retry_state.attempt_number} due to {retry_state.outcome.exception()}"
        )
    )
    def fetch_ohlcv(self, symbol: str, timeframe: str, since: int, limit: int = 1000) -> List[list]:
        """Fetch OHLCV data with retry logic."""
        return self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)


    def fetch_and_store_incremental(self, symbol: str, timeframe: str) -> bool:
        """Fetch and store only fully completed OHLCV candles for different timeframes."""
        try:
            last_timestamp = self.db_manager.get_last_stored_timestamp(symbol, timeframe)

            if last_timestamp is None:
                initial_date = datetime.now(timezone.utc) - timedelta(days=self.lookback_days)
                since = int(initial_date.timestamp() * 1000)
                logger.info(f"Performing initial fetch for {symbol} {timeframe}")
            else:
                since = last_timestamp + 1  # Avoid duplicate data

            now_utc = datetime.now(timezone.utc)

            if timeframe == "15m":
                last_completed_candle = now_utc.replace(minute=(now_utc.minute // 15) * 15, second=0, microsecond=0) - timedelta(minutes=15)
            elif timeframe == "1h":
                last_completed_candle = now_utc.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
            elif timeframe == "1d":
                last_completed_candle = now_utc.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
            elif timeframe == "1w":
                last_completed_candle = now_utc.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(weeks=1)
            elif timeframe == "1M":  
                last_completed_candle = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now_utc.day)

            else:
                last_completed_candle = now_utc  

            end_timestamp = int(last_completed_candle.timestamp() * 1000) 
            logger.info(f"Fetching data for {symbol} {timeframe} up to {last_completed_candle} (UTC)")
            df = self.fetch_historical_data(symbol, timeframe, since)
            df = df[df["timestamp"] <= pd.to_datetime(end_timestamp, unit="ms", utc=True)]

            if not self._validate_data(df):
                logger.warning(f"Validation failed for {symbol} {timeframe}")
                return False

            if not df.empty:
                self.db_manager.save_to_db(df)
                logger.info(f"Inserted {len(df)} records for {symbol} {timeframe}")
                return True

            return False
        except Exception as e:
            logger.error(f"Error in fetch_and_store_incremental: {e}", exc_info=True)
            return False

    def fetch_historical_data(self, symbol: str, timeframe: str, since: int) -> pd.DataFrame:
        """Fetch historical data with pagination and validation."""
        all_data = []
        current_since = since
        end_timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        
        while current_since < end_timestamp:
            try:
                ohlcv = self.fetch_ohlcv(symbol, timeframe, current_since)
                if not ohlcv:
                    break

                df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                df["symbol"] = symbol
                df["timeframe"] = timeframe
                
                if self._validate_data(df):
                    all_data.append(df)
                    current_since = int(df["timestamp"].iloc[-1].timestamp() * 1000) + 1
                else:
                    logger.warning(f"Invalid data chunk received for {symbol} {timeframe}")
                    break
            except ccxt.ExchangeError as e:
                logger.error(f"Exchange error: {e}")
                break

        return pd.concat(all_data, ignore_index=True) if all_data else pd.DataFrame()


    def _validate_data(self, df: pd.DataFrame) -> bool:
        """Perform comprehensive data validation."""
        if df.empty:
            return True
        required_columns = ["timestamp", "open", "high", "low", "close", "volume"]
        if not all(col in df.columns for col in required_columns):
            return False
        if df.duplicated(subset=["timestamp", "symbol", "timeframe"]).any():
            logger.warning("Duplicate data detected")
            return False
        if (df["volume"] < 0).any():
            logger.warning("Negative volume values detected")
            return False
        return True

class DataUpdater:
    """Manages scheduled data updates, signal generation, and triggers trade execution."""
    TIMEFRAME_CONFIG = {
        "15m": {"signal_lookback": 96},
        "1h": {"signal_lookback": 168},
        "1d": {"signal_lookback": 90}
    }

    def __init__(self):
        self.data_handler = DataHandler()
        self.signal_generator = SignalGenerator(self.data_handler.db_manager)
        self.lock = threading.Lock()
        self.first_run = True 
        self.trade_bot = TradeBot()

    def _get_active_symbols(self) -> List[str]:
        """Fetch tickers dynamically from the database."""
        tickers_df = self.data_handler.db_manager.fetch_tickers()
        if tickers_df is not None and not tickers_df.empty:
            return tickers_df["symbol"].tolist()
        return []

    def run_update(self):
        """Execute update cycle with resource locking."""
        if not self.lock.acquire(blocking=False):
            logger.warning("Previous update still running. Skipping...")
            return
        try:
            start_time = datetime.now(LOCAL_TZ)
            logger.info(f"Starting update cycle at {start_time}")
            symbols = self._get_active_symbols()
            if not symbols:
                logger.warning("No active symbols found.")
                return

            self._execute_parallel_updates(symbols)
            self._update_signals(symbols)

            elapsed = datetime.now(LOCAL_TZ) - start_time
            logger.info(f"Update cycle completed in {elapsed}")

            # Trigger trade logic immediately after data and signal updates.
            self.trigger_trade_bot_if_needed(symbols)
        except Exception as e:
            logger.error(f"Critical error in update cycle: {e}", exc_info=True)
        finally:
            self.lock.release()

    def _execute_parallel_updates(self, symbols: List[str]):
        """Execute parallel data updates using thread pooling."""
        with ThreadPoolExecutor(max_workers=self.data_handler.MAX_WORKERS) as executor:
            futures = [
                executor.submit(self.data_handler.fetch_and_store_incremental, symbol, timeframe)
                for symbol in symbols
                for timeframe in self.TIMEFRAME_CONFIG
            ]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Update failed: {e}")

    def _update_signals(self, symbols: List[str]):
        """Update signals for all timeframes using parallel processing."""
        with ThreadPoolExecutor(max_workers=self.data_handler.MAX_WORKERS) as executor:
            futures = [
                executor.submit(self._generate_and_save_signals, symbol, timeframe)
                for symbol in symbols
                for timeframe in self.TIMEFRAME_CONFIG
            ]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"Signal update failed: {e}")

    def _generate_and_save_signals(self, symbol, timeframe):
        """Fetch parameters, generate indicators, and store signals dynamically."""
        try:
            # Step 1: Fetch indicator parameters dynamically
            params = self.data_handler.db_manager.fetch_indicator_params(symbol, timeframe)
            if not params:
                logger.warning(f"No parameters found for {symbol} ({timeframe}), inserting defaults.")
                self.data_handler.db_manager.fetch_indicator_params(symbol, timeframe)  
                params = self.data_handler.db_manager.fetch_indicator_params(symbol, timeframe)  
            
            (
                keltner_upper_multiplier, keltner_lower_multiplier, keltner_period,
                rvi_15m_period, rvi_1h_period,
                rvi_15m_upper_threshold, rvi_15m_lower_threshold,
                rvi_1h_upper_threshold, rvi_1h_lower_threshold,
                include_15m_rvi  
            ) = params

            # Step 2: Prepare parameters for calculation
            keltner_params = {
                "period": keltner_period,
                "upper_multiplier": keltner_upper_multiplier,  
                "lower_multiplier": keltner_lower_multiplier,  
            }
            rvi_params = {
                "period": rvi_1h_period if timeframe == "1h" else rvi_15m_period,
            }

            # Step 3: Calculate and store indicators
            indicator_df = self.signal_generator.calculate_and_store_indicators(
                symbol, timeframe, keltner_params, rvi_params
            )

            if indicator_df is None or indicator_df.empty:
                logger.warning(f"No indicators generated for {symbol} ({timeframe}). Skipping signal generation.")
                return
            
            # Step 4: Generate final signals using the DB value for include_15m_rvi
            signal_df = self.signal_generator.generate_final_signals(
                symbol, timeframe, bool(include_15m_rvi) 
            )

            if signal_df is not None and not signal_df.empty:
                self.data_handler.db_manager.save_signals_to_db(signal_df)
            else:
                logger.warning(f"No signals generated for {symbol} ({timeframe}).")

        except Exception as e:
            logger.error(f"Signal update failed for {symbol} ({timeframe}): {e}")

    def trigger_trade_bot_if_needed(self, symbols: List[str]):
        """
        Trigger trade logic for each active symbol by calling risk management
        and signal-based trading functions on the TradeBot instance.
        Fetches EUR/USD rate once to avoid rate limiting.
        """
        if not symbols:
            return
            
        eur_usd_rate = None
        try:
            import yfinance as yf
            ticker_yf = yf.Ticker("EURUSD=X")
            data = ticker_yf.history(period="1d", interval="1h")
            if not data.empty:
                eur_usd_rate = data['Close'].iloc[-1]
                logger.debug(f"Pre-fetched EUR/USD rate: {eur_usd_rate}")
        except Exception as e:
            logger.warning(f"Could not pre-fetch EUR/USD rate: {e}")
            eur_usd_rate = 1.09  # Default fallback value
            
        # Process each symbol with the cached rate
        for symbol in symbols:
            self.trade_bot.execute_signal_based_trading_for_symbol(symbol, cached_eur_usd_rate=eur_usd_rate)

class Scheduler:
    """Manages the scheduling of update tasks."""
    def __init__(self, updater):
        self.updater = updater
        self._configure_schedules()

    def _configure_schedules(self):
        """Schedule updates at exact quarter-hour marks."""
        schedule.every().hour.at(":00").do(self._run_update)
        schedule.every().hour.at(":15").do(self._run_update)
        schedule.every().hour.at(":30").do(self._run_update)
        schedule.every().hour.at(":45").do(self._run_update)

    def _run_update(self):
        """Runs an update on a separate thread to avoid blocking the scheduler."""
        logger.info(f"Starting scheduled update at {datetime.now(LOCAL_TZ)}")
        update_thread = threading.Thread(target=self.updater.run_update, daemon=True)
        update_thread.start()

    def _calculate_delay_to_next_quarter(self):
        """Calculates seconds until the next quarter-hour (xx:00, xx:15, xx:30, xx:45)."""
        now = datetime.now(LOCAL_TZ)
        minutes = now.minute
        next_quarter = ((minutes // 15) + 1) * 15
        if next_quarter >= 60:
            next_quarter = 0
            next_run = (now + timedelta(hours=1)).replace(minute=next_quarter, second=1, microsecond=0)
        else:
            next_run = now.replace(minute=next_quarter, second=1, microsecond=0)
        delay = (next_run - now).total_seconds()
        return max(0, delay)

    def run(self):
        """Runs the scheduler main loop after syncing to the next quarter-hour."""
        logger.info("Starting scheduler...")
        self._run_update()
        delay = self._calculate_delay_to_next_quarter()
        logger.info(f"Sleeping for {int(delay)} seconds to sync with next quarter-hour.")
        time.sleep(delay)
        while True:
            schedule.run_pending()
            time.sleep(1)


if __name__ == "__main__":
    try:
        updater = DataUpdater()
        scheduler = Scheduler(updater)
        scheduler_thread = threading.Thread(target=scheduler.run, daemon=True)
        scheduler_thread.start()

        def risk_management_loop(trade_bot_instance):
            while True:
                try:
                    symbols_df = trade_bot_instance.db_manager.fetch_tickers()
                    if symbols_df is not None and not symbols_df.empty:
                        symbols = symbols_df["symbol"].tolist()
                        for sym in symbols:
                            trade_bot_instance.execute_risk_management_for_symbol(sym)
                    else:
                        logger.warning("No active symbols found for risk management loop.")
                except Exception as e:
                    logger.error(f"Error in risk management loop: {e}", exc_info=True)
                time.sleep(60*2)

        trade_bot_instance = TradeBot()
        risk_thread = threading.Thread(target=risk_management_loop, args=(trade_bot_instance,), daemon=True)
        risk_thread.start()

        # The DataUpdater now updates data, signals, and then triggers trade logic.
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down gracefully...")
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
