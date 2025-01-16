from app.data_handler import DataHandler
from datetime import datetime

if __name__ == "__main__":
    # Initialize the DataHandler
    handler = DataHandler(exchange_name="binance", lookback_days=365)

    # Fetch symbols dynamically from the database
    symbols = handler.db_manager.fetch_tickers()["symbol"].tolist()

    # Define timeframes
    timeframes = ["1h", "1d"]

    if not symbols:
        print(f"[{datetime.now()}] No tickers found in the database. Exiting...")
    else:
        print(f"[{datetime.now()}] Starting database update for symbols: {symbols} and timeframes: {timeframes}...")
        handler.setup_database(timeframes)  # Use dynamic symbols
        print(f"[{datetime.now()}] Database updated successfully.")

