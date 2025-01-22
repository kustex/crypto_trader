import os
import pandas as pd
import time

from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

class DatabaseManager:
    """
    Manages database operations including initialization, querying, and saving data.
    """

    def __init__(self, db_path="data/crypto_data.db"):
        """
        Initialize the DatabaseManager.

        :param db_path: Path to the SQLite database file.
        """
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            connect_args={"check_same_thread": False},
            pool_size=5,  # Allow up to 5 concurrent connections
            pool_recycle=3600,  # Recycle connections every hour
            isolation_level="SERIALIZABLE",  # Ensure consistent transactions
        )
        self.create_tickers_table()

    def initialize_database(self):
        create_historical_table_query = text("""
        CREATE TABLE IF NOT EXISTS historical_data (
            timestamp TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            PRIMARY KEY (timestamp, symbol, timeframe)
        )
        """)

        create_signals_table_query = text("""
        CREATE TABLE IF NOT EXISTS signals_data (
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            keltner_signal INTEGER,
            rvi_signal INTEGER,
            final_signal INTEGER,
            keltner_upper REAL,
            keltner_lower REAL,
            rvi REAL,
            rvi_signal_15m INTEGER,  
            PRIMARY KEY (timestamp, symbol, timeframe)
        )
        """)

        create_indicator_params_table_query = text("""
        CREATE TABLE IF NOT EXISTS indicator_params (
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            keltner_period INTEGER DEFAULT 24,
            keltner_multiplier REAL DEFAULT 2.0,
            rvi_period INTEGER DEFAULT 24,
            rvi_lower_threshold REAL DEFAULT -0.2,
            rvi_upper_threshold REAL DEFAULT 0.2,
            include_15m_rvi INTEGER DEFAULT 1,
            PRIMARY KEY (symbol, timeframe)
        )
        """)

        create_portfolio_risk_table_query = text("""
        CREATE TABLE IF NOT EXISTS portfolio_risk_parameters (
            symbol TEXT NOT NULL,
            stoploss REAL DEFAULT 0.10,  
            position_size REAL DEFAULT 0.05,  
            max_allocation REAL DEFAULT 0.20,  
            partial_sell_fraction REAL DEFAULT 0.2,  
            PRIMARY KEY (symbol)
        )
        """)

        with self.engine.connect() as connection:
            connection.execute(create_historical_table_query)
            connection.execute(create_signals_table_query)
            connection.execute(create_indicator_params_table_query)
            connection.execute(create_portfolio_risk_table_query)

        print("Database initialized.")

    def execute_with_retry(self, connection, query, params=None, max_retries=5, delay=1):
        """
        Execute a database query with retry logic for handling locked database errors.

        :param connection: The database connection object.
        :param query: The SQL query to execute.
        :param params: Optional parameters for the query.
        :param max_retries: Maximum number of retry attempts.
        :param delay: Delay (in seconds) between retries.
        """
        for attempt in range(max_retries):
            try:
                connection.execute(query, params or {})
                return
            except IntegrityError as e:
                if "database is locked" in str(e):
                    print(f"Database is locked. Retrying {attempt + 1}/{max_retries}...")
                    time.sleep(delay)
                else:
                    raise
        raise RuntimeError("Max retries exceeded for database operation.")

    def get_latest_intraday_price(self, ticker):
        """
        Fetch the latest intraday price for the selected ticker from the database.
        """
        query = text("""
            SELECT close
            FROM historical_data
            WHERE symbol = :ticker
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        with self.engine.connect() as connection:
            result = connection.execute(query, {"ticker": ticker}).fetchone()
        return result[-1] if result else None
    
    def get_prices_for_last_24h(self, ticker):
        query = text("""
            SELECT close
            FROM historical_data
            WHERE symbol = :ticker AND timestamp >= datetime('now', '-1 day')
            ORDER BY timestamp ASC
        """)
        with self.engine.connect() as connection:
            results = connection.execute(query, {"ticker": ticker}).fetchall()
        return [row[0] for row in results] if results else []

    def create_tickers_table(self):
        """
        Create the tickers table if it doesn't exist and populate it with default tickers.
        """
        query = text("""
        CREATE TABLE IF NOT EXISTS tickers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT UNIQUE NOT NULL
        )
        """)
        with self.engine.connect() as connection:
            connection.execute(query)

        # Insert default tickers if table is empty
        default_tickers = ["BTC/USDT", "ETH/USDT"]
        for ticker in default_tickers:
            self.insert_ticker(ticker)

    def insert_ticker(self, ticker):
        """
        Insert a ticker into the tickers table.
        """
        query = text("""
        INSERT OR IGNORE INTO tickers (symbol)
        VALUES (:symbol)
        """)
        with self.engine.connect() as connection:
            connection.execute(query, {"symbol": ticker})
            connection.commit()

    def fetch_tickers(self):
        """
        Fetch all tickers from the tickers table.
        """
        query = "SELECT symbol FROM tickers"
        with self.engine.connect() as connection:
            tickers = pd.read_sql(query, connection)
        return tickers

    def remove_ticker(self, symbol):
        """
        Remove a ticker from the database.
        :param symbol: The ticker symbol to remove (e.g., 'BTC/USDT').
        """
        query = text("DELETE FROM tickers WHERE symbol = :symbol")
        with self.engine.connect() as connection:
            result = connection.execute(query, {"symbol": symbol})
            connection.commit()
        if result.rowcount == 0:
            raise ValueError(f"Ticker {symbol} does not exist in the database.")

    def save_to_db(self, df: pd.DataFrame):
        if df.empty:
            print("No data to save.")
            return

        df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S.%f")
        try:
            with self.engine.begin() as connection:
                for _, row in df.iterrows():
                    query = text("""
                        INSERT OR IGNORE INTO historical_data
                        (timestamp, open, high, low, close, volume, symbol, timeframe)
                        VALUES (:timestamp, :open, :high, :low, :close, :volume, :symbol, :timeframe)
                    """)
                    self.execute_with_retry(connection, query, {
                        "timestamp": row["timestamp"],
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "volume": row["volume"],
                        "symbol": row["symbol"],
                        "timeframe": row["timeframe"],
                    })
        except Exception as e:
            print(f"Error saving data to the database: {e}")

    def save_signals_to_db(self, df: pd.DataFrame):
        """
        Save the DataFrame with signals and indicators to the signals_data table.

        :param df: DataFrame containing signals and indicators.
        """
        if df.empty:
            print("No signals to save.")
            return

        # Ensure all required columns are present
        required_columns = [
            "timestamp", "symbol", "timeframe", "keltner_signal", "rvi_signal",
            "final_signal", "keltner_upper", "keltner_lower", "rvi", "rvi_signal_15m"
        ]
        for col in required_columns:
            if col not in df.columns:
                if col == "rvi_signal_15m":
                    df[col] = 0  # Default value
                else:
                    raise ValueError(f"Missing required column: {col}")

        # Format timestamp to match database schema
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S.%f")

        try:
            with self.engine.begin() as connection:
                for _, row in df.iterrows():
                    query = text("""
                        INSERT INTO signals_data
                        (timestamp, symbol, timeframe, keltner_signal, rvi_signal, final_signal,
                        keltner_upper, keltner_lower, rvi, rvi_signal_15m)
                        VALUES (:timestamp, :symbol, :timeframe, :keltner_signal, :rvi_signal, :final_signal,
                                :keltner_upper, :keltner_lower, :rvi, :rvi_signal_15m)
                        ON CONFLICT(timestamp, symbol, timeframe) DO UPDATE SET
                            keltner_signal = excluded.keltner_signal,
                            rvi_signal = excluded.rvi_signal,
                            final_signal = excluded.final_signal,
                            keltner_upper = excluded.keltner_upper,
                            keltner_lower = excluded.keltner_lower,
                            rvi = excluded.rvi,
                            rvi_signal_15m = excluded.rvi_signal_15m
                    """)
                    self.execute_with_retry(connection, query, {
                        "timestamp": row["timestamp"],
                        "symbol": row["symbol"],
                        "timeframe": row["timeframe"],
                        "keltner_signal": row["keltner_signal"],
                        "rvi_signal": row["rvi_signal"],
                        "final_signal": row["final_signal"],
                        "keltner_upper": row["keltner_upper"],
                        "keltner_lower": row["keltner_lower"],
                        "rvi": row["rvi"],
                        "rvi_signal_15m": row["rvi_signal_15m"],
                    })
            print("Signals and indicators saved to database.")
        except Exception as e:
            print(f"Error saving signals to the database: {e}")

    def save_risk_params(self, symbol, stoploss, position_size, max_allocation, partial_sell_fraction):
        """
        Save or update portfolio risk parameters for a given symbol.
        """
        query = text("""
        INSERT INTO portfolio_risk_parameters (symbol, stoploss, position_size, max_allocation, partial_sell_fraction)
        VALUES (:symbol, :stoploss, :position_size, :max_allocation, :partial_sell_fraction)
        ON CONFLICT(symbol) DO UPDATE SET
            stoploss = :stoploss,
            position_size = :position_size,
            max_allocation = :max_allocation,
            partial_sell_fraction = :partial_sell_fraction
        """)
        print(f"Saving risk parameters for {symbol}: stoploss={stoploss}, position_size={position_size}, max_allocation={max_allocation}, partial_sell_fraction={partial_sell_fraction}")
        
        with self.engine.connect() as connection:
            connection.execute(query, {
                "symbol": symbol,
                "stoploss": stoploss,
                "position_size": position_size,
                "max_allocation": max_allocation,
                "partial_sell_fraction": partial_sell_fraction
            })
            connection.commit()
        print(f"Risk parameters saved for {symbol}.")

    def fetch_risk_params(self, symbol):
        """
        Fetch portfolio risk parameters for a given symbol.
        If no parameters exist, save default parameters and return them.
        """
        query = text("""
        SELECT stoploss, position_size, max_allocation, partial_sell_fraction
        FROM portfolio_risk_parameters
        WHERE symbol = :symbol
        """)
        with self.engine.connect() as connection:
            result = connection.execute(query, {"symbol": symbol}).fetchone()

        if result:
            return result
        else:
            # Save default parameters if none exist
            default_params = {
                "symbol": symbol,
                "stoploss": 0.10,  
                "position_size": 0.05,  
                "max_allocation": 0.20,  
                "partial_sell_fraction": 0.2,  
            }
            print(f"Inserting default risk parameters for {symbol}.")
            self.save_risk_params(
                default_params["symbol"],
                default_params["stoploss"],
                default_params["position_size"],
                default_params["max_allocation"],
                default_params["partial_sell_fraction"]
            )
            return (
                default_params["stoploss"],
                default_params["position_size"],
                default_params["max_allocation"],
                default_params["partial_sell_fraction"]
            )

    def save_indicator_params(
        self, symbol, timeframe, keltner_period, keltner_multiplier, rvi_period, rvi_lower_threshold, rvi_upper_threshold, include_15m_rvi
    ):
        """
        Save or update indicator parameters for a given symbol and timeframe.
        """
        query = text("""
        INSERT INTO indicator_params (symbol, timeframe, keltner_period, keltner_multiplier, rvi_period, rvi_lower_threshold, rvi_upper_threshold, include_15m_rvi)
        VALUES (:symbol, :timeframe, :keltner_period, :keltner_multiplier, :rvi_period, :rvi_lower_threshold, :rvi_upper_threshold, :include_15m_rvi)
        ON CONFLICT(symbol, timeframe) DO UPDATE SET
            keltner_period = :keltner_period,
            keltner_multiplier = :keltner_multiplier,
            rvi_period = :rvi_period,
            rvi_lower_threshold = :rvi_lower_threshold,
            rvi_upper_threshold = :rvi_upper_threshold,
            include_15m_rvi = :include_15m_rvi
        """)
        with self.engine.connect() as connection:
            connection.execute(query, {
                "symbol": symbol,
                "timeframe": timeframe,
                "keltner_period": keltner_period,
                "keltner_multiplier": keltner_multiplier,
                "rvi_period": rvi_period,
                "rvi_lower_threshold": rvi_lower_threshold,
                "rvi_upper_threshold": rvi_upper_threshold,
                "include_15m_rvi": include_15m_rvi
            })
            connection.commit()
        print(f"Parameters saved for {symbol} ({timeframe}).")


    def fetch_indicator_params(self, symbol, timeframe):
        """
        Fetch indicator parameters for a given symbol and timeframe.
        If no parameters exist, save default parameters and return them.
        """
        query = text("""
        SELECT keltner_period, keltner_multiplier, rvi_period, rvi_lower_threshold, rvi_upper_threshold, include_15m_rvi
        FROM indicator_params
        WHERE symbol = :symbol AND timeframe = :timeframe
        """)
        with self.engine.connect() as connection:
            result = connection.execute(query, {"symbol": symbol, "timeframe": timeframe}).fetchone()

        if result:
            return result
        else:
            # Save default parameters if none exist
            default_params = {
                "symbol": symbol,
                "timeframe": timeframe,
                "keltner_period": 24,
                "keltner_multiplier": 2.0,
                "rvi_period": 24,
                "rvi_lower_threshold": -0.2,
                "rvi_upper_threshold": 0.2,
                "include_15m_rvi": 1  
            }
            print(f"Inserting default parameters for {symbol} ({timeframe}).")
            self.save_indicator_params(
                default_params["symbol"],
                default_params["timeframe"],
                default_params["keltner_period"],
                default_params["keltner_multiplier"],
                default_params["rvi_period"],
                default_params["rvi_lower_threshold"],
                default_params["rvi_upper_threshold"],
                default_params["include_15m_rvi"]
            )
            return (
                default_params["keltner_period"],
                default_params["keltner_multiplier"],
                default_params["rvi_period"],
                default_params["rvi_lower_threshold"],
                default_params["rvi_upper_threshold"],
                default_params["include_15m_rvi"]
            )

    def fetch_include_15m_rvi(self, symbol: str, timeframe: str) -> bool:
        """
        Debug connection usage in `fetch_include_15m_rvi`.
        """
        print(f"Checking 15m RVI for {symbol} ({timeframe})...")
        query = text("""
            SELECT include_15m_rvi
            FROM indicator_params
            WHERE symbol = :symbol AND timeframe = :timeframe
        """)
        with self.engine.connect() as connection:
            print("Connection successful.")
            result = connection.execute(query, {"symbol": symbol, "timeframe": timeframe}).fetchone()

        return bool(result[0]) if result else False


    def get_last_stored_timestamp(self, symbol: str, timeframe: str) -> int:
        """
        Retrieve the most recent timestamp stored in the database for a given symbol and timeframe.

        :param symbol: Trading pair (e.g., 'BTC/USDT').
        :param timeframe: Timeframe (e.g., '1h', '1d').
        :return: Most recent timestamp in milliseconds, or None if no data exists.
        """
        query = text("""
            SELECT MAX(timestamp) as last_timestamp
            FROM historical_data
            WHERE symbol = :symbol AND timeframe = :timeframe
        """)
        with self.engine.connect() as connection:
            result = connection.execute(query, {"symbol": symbol, "timeframe": timeframe}).fetchone()
        if result and result[0]:
            try:
                timestamp_ms = int(pd.to_datetime(result[0]).timestamp() * 1000)
                return timestamp_ms
            except Exception as e:
                print(f"Error parsing timestamp {result[0]}: {e}")
        else:
            print(f"No data found for {symbol} ({timeframe}).")
        return None

    def query_data(self, symbol: str, timeframe: str, start: str = None, end: str = None) -> pd.DataFrame:
        """
        Query data from the database for a specific symbol and timeframe.
        """
        query = f"""
            SELECT * FROM historical_data
            WHERE symbol = '{symbol}' AND timeframe = '{timeframe}'
        """
        if start:
            query += f" AND timestamp >= '{start}'"
        if end:
            query += f" AND timestamp <= '{end}'"

        with self.engine.connect() as connection:
            df = pd.read_sql(query, connection)

        # Ensure the timestamp is a datetime column
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])

        return df

    def print_first_and_last_dates(self):
        """
        Print the first and last timestamp for each symbol and timeframe in the database.
        """
        try:
            query = """
                SELECT symbol, timeframe, MIN(timestamp) as first_date, MAX(timestamp) as last_date
                FROM historical_data
                GROUP BY symbol, timeframe
            """
            result = pd.read_sql(query, self.engine)
            if not result.empty:
                print("Database state (first and last dates):")
                print(result)
            else:
                print("No data available in the database.")
        except Exception as e:
            print(f"Error querying the database: {e}")

    def debug_database_content(self):
        """
        Print sample rows and table schema for debugging purposes.
        """
        try:
            query = "SELECT * FROM historical_data LIMIT 10"
            with self.engine.connect() as connection:
                result = connection.execute(query).fetchall()
            print("Sample rows from the database:")
            for row in result:
                print(row)

            schema_query = "PRAGMA table_info(historical_data)"
            with self.engine.connect() as connection:
                schema_result = connection.execute(schema_query).fetchall()
            print("Table schema:")
            for column in schema_result:
                print(column)
        except Exception as e:
            print(f"Error accessing database content: {e}")

