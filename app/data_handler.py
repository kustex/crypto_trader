import sys
import ccxt
import logging
import pandas as pd
import schedule
import time
import os
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta, timezone
from app.database import DatabaseManager
from app.signals import SignalGenerator
from concurrent.futures import ThreadPoolExecutor, as_completed


class DataHandler:
    """
    Handles fetching and preprocessing of historical crypto data.
    """

    def __init__(self, exchange_name: str, lookback_days: int = 365):
        """
        Initialize the DataHandler with exchange details.

        :param exchange_name: Name of the exchange (e.g., 'binance')
        :param lookback_days: Number of days to fetch historical data for initial setup.
        """
        self.exchange_name = exchange_name
        self.lookback_days = lookback_days
        self.exchange = getattr(ccxt, exchange_name)({"enableRateLimit": True})
        self.db_manager = DatabaseManager(db_path="data/crypto_data.db")
        self.db_manager.initialize_database()

        # Set up logging
        os.makedirs("logs", exist_ok=True)
        logging.basicConfig(
            filename="logs/data_handler.log",
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s"
        )

    def setup_database(self, symbols: list, timeframes: list):
        """
        Set up the database with historical data for multiple tickers and timeframes.

        :param symbols: List of symbols (e.g., ['BTC/USDT']).
        :param timeframes: List of timeframes (e.g., ['1h', '1d']).
        """
        if not symbols:
            logging.warning("No symbols provided for setup. Exiting.")
            return

        for symbol in symbols:
            logging.info(f"Setting up {symbol} for timeframes: {timeframes}")
            for timeframe in timeframes:
                self.fetch_and_store_incremental(symbol, timeframe)

    def fetch_and_store_incremental(self, symbol: str, timeframe: str) -> bool:
        """
        Fetch and store incremental data for the specified symbol and timeframe.
        """
        try:
            last_timestamp = self.db_manager.get_last_stored_timestamp(symbol, timeframe)
            if last_timestamp is None:
                logging.info(f"No data found for {symbol} ({timeframe}). Performing full fetch.")
                last_timestamp = int((datetime.now() - timedelta(days=self.lookback_days)).timestamp() * 1000)

            since = last_timestamp + 1
            logging.info(f"Fetching {symbol} ({timeframe}) data since {datetime.fromtimestamp(since / 1000, timezone.utc)}")

            df = self.fetch_historical_data(symbol, timeframe, since)
            if df.empty:
                logging.info(f"No new data fetched for {symbol} ({timeframe}).")
                return False

            logging.info(f"Fetched {len(df)} rows for {symbol} ({timeframe}). Saving to database.")
            self.db_manager.save_to_db(df)
            logging.info(f"Data saved successfully for {symbol} ({timeframe}).")
            return True
        except Exception as e:
            logging.error(f"Error fetching or saving data for {symbol} ({timeframe}): {e}")
            return False

    def fetch_historical_data(self, symbol: str, timeframe: str, since: int, end: int = None) -> pd.DataFrame:
        """
        Fetch historical data for the specified symbol and timeframe.

        :param symbol: Trading pair (e.g., 'BTC/USDT').
        :param timeframe: Candlestick timeframe (e.g., '1h', '1d').
        :param since: Timestamp (in milliseconds) from which to fetch data.
        :param end: Optional end timestamp (in milliseconds).
        :return: DataFrame containing the historical OHLCV data.
        """
        all_data = []
        limit = 1000
        current_since = since
        max_iterations = 100

        for _ in range(max_iterations):
            try:
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=current_since, limit=limit)
                if not ohlcv:
                    break

                df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
                df["symbol"] = symbol
                df["timeframe"] = timeframe
                all_data.append(df)

                current_since = int(df["timestamp"].iloc[-1].timestamp() * 1000) + 1
                if current_since >= int(datetime.now().timestamp() * 1000):
                    break
            except ccxt.NetworkError as e:
                logging.warning(f"Network error fetching {symbol} ({timeframe}): {e}. Retrying...")
                time.sleep(5)
                continue
            except Exception as e:
                logging.error(f"Unexpected error fetching {symbol} ({timeframe}): {e}")
                break

        if all_data:
            return pd.concat(all_data, ignore_index=True)
        return pd.DataFrame()


class DataUpdater:
    """
    Manages periodic data updates and signal recalculations.
    """

    def __init__(self, timeframes: list):
        self.timeframes = timeframes
        self.data_handler = DataHandler(exchange_name="binance", lookback_days=365)
        self.signal_generator = SignalGenerator(db_manager=self.data_handler.db_manager)

    def get_symbols(self) -> list:
        """
        Fetch tickers dynamically from the database.
        """
        return self.data_handler.db_manager.fetch_tickers()["symbol"].tolist()

    def run_update(self, full_update: bool = False):
        """
        Update the database and generate signals.
        """
        now = datetime.now()
        logging.info(f"Running update at {now}")

        symbols = self.get_symbols()
        if not symbols:
            logging.warning("No symbols found in the database. Skipping update.")
            return

        # Determine which timeframes need updates
        timeframes_with_new_data = self._determine_timeframes_to_update(symbols, full_update)
        self._fetch_and_process_data(timeframes_with_new_data)

        # Recalculate signals
        self.recalculate_signals(timeframes_with_new_data)

    def _determine_timeframes_to_update(self, symbols: list, full_update: bool) -> dict:
        """
        Determine which timeframes require updates.
        """
        now = datetime.now()
        fetch_15m = full_update or now.minute % 15 == 0
        fetch_1h = full_update or now.minute == 0
        fetch_1d = full_update or (now.hour == 0 and now.minute == 0)

        timeframes_with_new_data = {
            symbol: {"15m": fetch_15m, "1h": fetch_1h, "1d": fetch_1d} for symbol in symbols
        }
        return timeframes_with_new_data

    def _fetch_and_process_data(self, timeframes_with_new_data: dict):
        """
        Fetch and process data for symbols and timeframes with new data.
        """
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_to_symbol_timeframe = {
                executor.submit(self.data_handler.fetch_and_store_incremental, symbol, timeframe): (symbol, timeframe)
                for symbol, timeframes in timeframes_with_new_data.items()
                for timeframe, should_fetch in timeframes.items()
                if should_fetch
            }

            for future in as_completed(future_to_symbol_timeframe):
                symbol, timeframe = future_to_symbol_timeframe[future]
                try:
                    result = future.result()
                    logging.info(f"Fetch result for {symbol} ({timeframe}): {result}")
                except Exception as e:
                    logging.error(f"Error during fetch for {symbol} ({timeframe}): {e}")

    def recalculate_signals(self, timeframes_with_new_data: dict):
        """
        Recalculate signals for timeframes with new data, including 15m RVI conditions only for hourly data.
        """
        logging.info("Starting signal recalculation...")

        # Check if there's any new data
        has_new_data = any(
            any(timeframes.values()) for timeframes in timeframes_with_new_data.values()
        )

        if not has_new_data:
            logging.info("No new data available for recalculating signals. Skipping.")
            return

        for symbol, timeframes in timeframes_with_new_data.items():
            for timeframe, has_new_data in timeframes.items():
                if not has_new_data:
                    continue

                logging.info(f"Recalculating signals for {symbol} ({timeframe})...")

                # Query the data for the symbol and timeframe
                df = self.data_handler.db_manager.query_data(symbol, timeframe)
                if df.empty:
                    logging.warning(f"No data available for {symbol} ({timeframe}). Skipping.")
                    continue

                # Fetch indicator parameters
                params = self.data_handler.db_manager.fetch_indicator_params(symbol, timeframe)
                if not params:
                    logging.warning(f"No indicator parameters found for {symbol} ({timeframe}). Skipping.")
                    continue

                # Map parameters to dictionaries
                include_15m_rvi = params[5] if len(params) > 5 else 0
                keltner_params = {"period": params[0], "multiplier": params[1]}
                rvi_params = {"period": params[2], "thresholds": {"lower": params[3], "upper": params[4]}}

                # Fetch 15m data only for hourly timeframe
                df_15m = None
                if timeframe == '1h' and include_15m_rvi:
                    df_15m = self.data_handler.db_manager.query_data(symbol, "15m")
                    if df_15m.empty:
                        logging.warning(f"No 15m data available for {symbol}. Skipping 15m RVI condition.")
                        df_15m = None

                # Generate signals
                final_signals = self.signal_generator.generate_signals(
                    df,
                    keltner_params=keltner_params,
                    rvi_params=rvi_params,
                    timeframe=timeframe,
                    df_15m=df_15m,
                )

                # Save signals to the database
                self.data_handler.db_manager.save_signals_to_db(final_signals)

        logging.info("Signal recalculation complete.")



    def start_scheduler(self):
        """
        Start the scheduler for periodic updates, resynced to quarter-hour intervals.
        """
        def calculate_next_quarter_delay():
            """
            Calculate the delay in seconds until the next quarter-hour mark.
            """
            now = datetime.now()
            next_quarter = (now + timedelta(minutes=15)).replace(minute=(now.minute // 15 + 1) * 15 % 60, second=0, microsecond=0)
            if next_quarter.minute == 0:  # If it's the top of the hour
                next_quarter = next_quarter.replace(hour=(now.hour + 1) % 24)
            return (next_quarter - now).total_seconds()

        def update_and_resync():
            """
            Run the update process and calculate the delay to the next quarter.
            """
            print(f"Starting update and resync at {datetime.now()}")
            self.run_update(full_update=False)

        logging.info("Starting scheduler...")
        self.run_update(full_update=True)

        while True:
            update_and_resync()
            delay = calculate_next_quarter_delay()
            print(f"Next update scheduled in {delay:.2f} seconds at {datetime.now() + timedelta(seconds=delay)}")
            time.sleep(delay)

if __name__ == "__main__":
    updater = DataUpdater(timeframes=["15m", "1h", "1d"])
    updater.start_scheduler()




