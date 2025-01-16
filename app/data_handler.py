import ccxt
import pandas as pd
import schedule
import time
import os
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
from app.database import DatabaseManager
from app.signals import SignalGenerator


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
        self.exchange = getattr(ccxt, exchange_name)()
        self.db_manager = DatabaseManager(db_path="data/crypto_data.db")
        self.db_manager.initialize_database()

    def setup_database(self, symbols, timeframes: list):
        """
        Set up the database with historical data for multiple tickers and timeframes.

        :param timeframes: List of timeframes (e.g., ['1h', '1d']).
        """
        # Fetch tickers dynamically from the database
        # symbols = self.db_manager.fetch_tickers()["symbol"].tolist()

        if not symbols:
            print("No tickers found in the database. Exiting database setup.")
            return

        for symbol in symbols:
            print(f'-----------------------{symbol}---------------------------')
            for timeframe in timeframes:
                self.fetch_and_store_incremental(symbol, timeframe)

    def fetch_and_store_incremental(self, symbol: str, timeframe: str) -> bool:
        """
        Fetch and store incremental data for the specified symbol and timeframe.
        :param symbol: Trading pair (e.g., 'BTC/USDT').
        :param timeframe: Timeframe (e.g., '1h', '1d').
        :return: True if new data was fetched and saved; False otherwise.
        """
        last_timestamp = self.db_manager.get_last_stored_timestamp(symbol, timeframe)
        since = last_timestamp + 1 if last_timestamp else int((datetime.now() - timedelta(days=self.lookback_days)).timestamp() * 1000)

        df = self.fetch_historical_data(symbol, timeframe, since)

        if df.empty:
            print(f"No new data fetched for {symbol} ({timeframe}).")
            return False

        try:
            self.db_manager.save_to_db(df)
            print(f"New data saved for {symbol} ({timeframe}): {len(df)} rows.")
            return True
        except Exception as e:
            print(f"Unexpected error while saving data for {symbol} ({timeframe}): {e}")
            return False


    def fetch_historical_data(self, symbol: str, timeframe: str, since: int) -> pd.DataFrame:
        """
        Fetch historical data for the specified symbol and timeframe.

        :param symbol: Trading pair (e.g., 'BTC/USDT').
        :param timeframe: Candlestick timeframe (e.g., '1h', '1d').
        :param since: Timestamp (in milliseconds) from which to fetch data.
        :return: DataFrame containing the historical OHLCV data.
        """
        all_data = []
        limit = 1000  # Binance's typical limit for one request
        current_since = since

        while True:
            try:
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=current_since, limit=limit)
                if not ohlcv:
                    break  # No more data returned

                df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                df["symbol"] = symbol
                df["timeframe"] = timeframe

                all_data.append(df)

                # Move the current_since forward to the last timestamp in the batch
                current_since = int(df["timestamp"].iloc[-1].timestamp() * 1000) + 1

                # Break if we've hit the current time
                if current_since >= int(datetime.now().timestamp() * 1000):
                    break
            except ccxt.NetworkError as e:
                print(f"Network error: {e}")
                break
            except Exception as e:
                print(f"Unexpected error: {e}")
                break

        # Combine all batches into a single DataFrame
        if all_data:
            return pd.concat(all_data, ignore_index=True)
        return pd.DataFrame()

class DataUpdater:
    def __init__(self, timeframes):
        self.timeframes = timeframes
        self.data_handler = DataHandler(exchange_name="binance", lookback_days=365)
        self.signal_generator = SignalGenerator(db_manager=self.data_handler.db_manager)  # Pass DatabaseManager instance

    def get_symbols(self):
        """
        Fetch tickers dynamically from the database.
        """
        return self.data_handler.db_manager.fetch_tickers()["symbol"].tolist()

    def run_update(self, full_update=False):
        """
        Update the database and generate signals.
        :param full_update: If True, fetch data for all timeframes regardless of the current time.
        """
        now = datetime.now()
        print(f"Starting update at {now}...")

        symbols = self.get_symbols()
        if not symbols:
            print("No tickers found in the database. Exiting update.")
            return

        fetch_15m = full_update or now.minute % 60 != 0  # Fetch 15m on startup or when not at the top of the hour
        fetch_1h = full_update or now.minute == 0       # Fetch 1h on startup or at the top of the hour
        fetch_1d = full_update or (now.hour == 0 and now.minute == 0)  # Fetch 1d on startup or at midnight UTC

        # Track timeframes that require signal recalculation
        timeframes_with_new_data = {symbol: {"15m": False, "1h": False, "1d": False} for symbol in symbols}

        for symbol in symbols:
            if fetch_15m:
                if self.data_handler.fetch_and_store_incremental(symbol, "15m"):
                    timeframes_with_new_data[symbol]["15m"] = True

            if fetch_1h:
                if self.data_handler.fetch_and_store_incremental(symbol, "1h"):
                    timeframes_with_new_data[symbol]["1h"] = True

            if fetch_1d:
                if self.data_handler.fetch_and_store_incremental(symbol, "1d"):
                    timeframes_with_new_data[symbol]["1d"] = True

        print("Database update complete.")

        # Generate signals only for timeframes with new data
        print("Starting signal calculation...")
        for symbol, timeframes in timeframes_with_new_data.items():
            for timeframe, has_new_data in timeframes.items():
                if has_new_data:
                    print(f"Generating signals for {symbol} ({timeframe})...")
                    df = self.data_handler.db_manager.query_data(symbol, timeframe)
                    if df.empty:
                        print(f"No data available for {symbol} ({timeframe}). Skipping.")
                        continue

                    # Fetch indicator parameters
                    params = self.data_handler.db_manager.fetch_indicator_params(symbol, timeframe)
                    if not params:
                        print(f"No indicator parameters found for {symbol} ({timeframe}). Skipping.")
                        continue

                    # Map parameters to required dictionaries
                    keltner_params = {
                        "period": params[0],
                        "multiplier": params[1],
                    }
                    rvi_params = {
                        "period": params[2],
                        "thresholds": {
                            "lower": params[3],
                            "upper": params[4],
                        },
                    }

                    # Generate signals
                    final_signals = self.signal_generator.generate_signals(df, keltner_params=keltner_params, rvi_params=rvi_params)

                    # Save signals and indicators to the database
                    self.data_handler.db_manager.save_signals_to_db(final_signals)

        print("Signal calculation complete.")

    def start_scheduler(self):
        """
        Start the scheduler, ensuring it syncs with the next quarter-hour.
        """
        print("Starting initial full update...")
        self.run_update(full_update=True)  # Perform a full update on startup

        # Calculate delay until the next quarter-hour
        now = datetime.now()
        next_quarter = (now + timedelta(minutes=15 - (now.minute % 15))).replace(second=0, microsecond=0)
        delay = (next_quarter - now).total_seconds()

        print(f"Syncing to the next quarter-hour. Next update in {delay:.2f} seconds...")
        time.sleep(delay)  # Wait until the next quarter-hour

        # Schedule updates every 15 minutes
        schedule.every(15).minutes.do(self.run_update, full_update=False)
        print("Scheduler started. Updates will occur every 15 minutes.")

        # Run the scheduler
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nScheduler stopped manually. Exiting...")



if __name__ == "__main__":
    updater = DataUpdater(
        timeframes=["15m", "1h", "1d"],  # Timeframes to process
    )
    updater.run_update()  # Run an initial update
    updater.start_scheduler()  # Start the scheduler




