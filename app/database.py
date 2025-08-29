import os
import pandas as pd
import time
import psycopg2

from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


class DatabaseManager:
    def __init__(self):
        # Instead of this:
        # self.POSTGRES_HOST = "127.0.0.1"

        # Use environment variables so we can override them at runtime
        import os
        self.POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
        self.POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
        self.POSTGRES_DBNAME = os.getenv("POSTGRES_DB", "crypto_data")
        # self.POSTGRES_HOST = os.getenv("POSTGRES_HOST", "db")
        self.POSTGRES_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
        self.POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

        # Then your create_engine call can use these variables
        self._create_database_if_not_exists()

        self.engine = create_engine(
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DBNAME}",
            pool_size=10,
            max_overflow=5,
            isolation_level="READ COMMITTED",
        )
        self.create_tickers_table()


    def _create_database_if_not_exists(self):
        """
        Checks if the database exists and creates it if necessary.
        """
        try:
            # Connect to the PostgreSQL server (not a specific database)
            conn = psycopg2.connect(
                dbname="postgres", user=self.POSTGRES_USER, password=self.POSTGRES_PASSWORD, host=self.POSTGRES_HOST, port=self.POSTGRES_PORT
            )
            conn.autocommit = True
            cursor = conn.cursor()

            # Check if database exists
            cursor.execute(f"SELECT 1 FROM pg_database WHERE datname = '{self.POSTGRES_DBNAME}'")
            exists = cursor.fetchone()

            if not exists:
                print(f"Database '{self.POSTGRES_DBNAME}' does not exist. Creating it now...")
                cursor.execute(f"CREATE DATABASE {self.POSTGRES_DBNAME}")
                print(f"Database '{self.POSTGRES_DBNAME}' created successfully.")
            else:
                print(f"Database '{self.POSTGRES_DBNAME}' already exists.")

            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Error while checking/creating database: {e}")

    def initialize_database(self):
        """Creates all necessary tables if they do not exist."""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS historical_data (
                timestamp TIMESTAMP NOT NULL,
                open DOUBLE PRECISION,
                high DOUBLE PRECISION,
                low DOUBLE PRECISION,
                close DOUBLE PRECISION,
                volume DOUBLE PRECISION,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                PRIMARY KEY (timestamp, symbol, timeframe)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS indicator_historical_data (
                timestamp TIMESTAMP NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                keltner_upper DOUBLE PRECISION,
                keltner_lower DOUBLE PRECISION,
                rvi DOUBLE PRECISION,
                PRIMARY KEY (timestamp, symbol, timeframe)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS signals_data (
                timestamp TIMESTAMP NOT NULL,
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                keltner_signal INTEGER,
                rvi_signal INTEGER,
                rvi_signal_15m INTEGER DEFAULT 0,
                final_signal INTEGER,
                PRIMARY KEY (timestamp, symbol, timeframe)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS indicator_params (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                keltner_upper_multiplier DOUBLE PRECISION DEFAULT 3.0,
                keltner_lower_multiplier DOUBLE PRECISION DEFAULT 3.0,
                keltner_period INTEGER DEFAULT 24,
                rvi_15m_period INTEGER DEFAULT 10,
                rvi_1h_period INTEGER DEFAULT 10,
                rvi_15m_upper_threshold DOUBLE PRECISION DEFAULT 0.2,
                rvi_15m_lower_threshold DOUBLE PRECISION DEFAULT -0.2,
                rvi_1h_upper_threshold DOUBLE PRECISION DEFAULT 0.2,
                rvi_1h_lower_threshold DOUBLE PRECISION DEFAULT -0.2,
                include_15m_rvi INTEGER DEFAULT 1,  -- ✅ Added this column
                PRIMARY KEY (symbol, timeframe)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS portfolio_risk_parameters (
                symbol TEXT NOT NULL,
                stoploss DOUBLE PRECISION DEFAULT 0.10,
                position_size DOUBLE PRECISION DEFAULT 0.05,
                max_allocation DOUBLE PRECISION DEFAULT 0.20,
                partial_sell_fraction DOUBLE PRECISION DEFAULT 0.2,
                PRIMARY KEY (symbol)
            )
            """
        ]

        with self.engine.connect() as connection:
            for query in queries:
                connection.execute(text(query))
            connection.commit()

        # print("Database initialized with all tables.")

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
        """
        Fetches closing prices for the last 24 hours for the given ticker.
        """
        query = text("""
            SELECT close
            FROM historical_data
            WHERE symbol = :ticker 
            AND timestamp >= NOW() - INTERVAL '1 day'
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
            id SERIAL PRIMARY KEY,
            symbol TEXT UNIQUE NOT NULL
        )
        """)

        with self.engine.connect() as connection:
            connection.execute(query)
            connection.commit()  


        # Insert default tickers if the table is empty
        default_tickers = ["BTC/USDT", "ETH/USDT"]
        for ticker in default_tickers:
            self.insert_ticker(ticker)

    def insert_ticker(self, ticker):
        """
        Insert a ticker into the tickers table, ignoring duplicates.
        """
        query = text("""
            INSERT INTO tickers (symbol)
            VALUES (:symbol)
            ON CONFLICT(symbol) DO NOTHING
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
        """
        Save historical data to PostgreSQL.
        """
        if df.empty:
            print("No data to save.")
            return

        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S.%f")
        
        try:
            with self.engine.begin() as connection:
                for _, row in df.iterrows():
                    query = text("""
                        INSERT INTO historical_data (timestamp, open, high, low, close, volume, symbol, timeframe)
                        VALUES (:timestamp, :open, :high, :low, :close, :volume, :symbol, :timeframe)
                        ON CONFLICT (timestamp, symbol, timeframe) DO NOTHING
                    """)
                    connection.execute(query, {
                        "timestamp": row["timestamp"],
                        "open": row["open"],
                        "high": row["high"],
                        "low": row["low"],
                        "close": row["close"],
                        "volume": row["volume"],
                        "symbol": row["symbol"],
                        "timeframe": row["timeframe"],
                    })
            
            print(f"Saved {len(df)} rows to historical_data.")

        except Exception as e:
            print(f"Error saving data to the database: {e}")

    def save_signals_to_db(self, df: pd.DataFrame):
        """
        Save the DataFrame with signals to the signals_data table.
        """
        if df.empty:
            print("No signals to save.")
            return

        required_columns = {"timestamp", "symbol", "timeframe", "keltner_signal", "rvi_signal", "rvi_signal_15m", "final_signal"}
        missing_columns = required_columns - set(df.columns)
        
        if missing_columns:
            print(f"Error: Missing required columns in DataFrame: {missing_columns}")
            return

        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S.%f")

        try:
            with self.engine.begin() as connection:
                for _, row in df.iterrows():
                    query = text("""
                        INSERT INTO signals_data (timestamp, symbol, timeframe, keltner_signal, rvi_signal, rvi_signal_15m, final_signal)
                        VALUES (:timestamp, :symbol, :timeframe, :keltner_signal, :rvi_signal, :rvi_signal_15m, :final_signal)
                        ON CONFLICT (timestamp, symbol, timeframe) DO UPDATE 
                        SET keltner_signal = EXCLUDED.keltner_signal,
                            rvi_signal = EXCLUDED.rvi_signal,
                            rvi_signal_15m = EXCLUDED.rvi_signal_15m,
                            final_signal = EXCLUDED.final_signal
                    """)
                    connection.execute(query, {
                        "timestamp": row["timestamp"],
                        "symbol": row["symbol"],
                        "timeframe": row["timeframe"],
                        "keltner_signal": row["keltner_signal"],
                        "rvi_signal": row["rvi_signal"],
                        "rvi_signal_15m": row["rvi_signal_15m"],
                        "final_signal": row["final_signal"],
                    })

            # print(f"Signals saved to database ({len(df)} rows).")

        except Exception as e:
            print(f"Error saving signals to the database: {e}")


    def save_indicators_to_db(self, df: pd.DataFrame):
        """
        Save indicator data into the indicator_historical_data table.
        """
        if df.empty:
            print("No indicators to save.")
            return

        df = df.copy()  # ✅ Ensure df is a full copy before modifying
        df["timestamp"] = pd.to_datetime(df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M:%S.%f")

        try:
            with self.engine.begin() as connection:
                for _, row in df.iterrows():
                    query = text("""
                        INSERT INTO indicator_historical_data (timestamp, symbol, timeframe, keltner_upper, keltner_lower, rvi)
                        VALUES (:timestamp, :symbol, :timeframe, :keltner_upper, :keltner_lower, :rvi)
                        ON CONFLICT (timestamp, symbol, timeframe) DO UPDATE 
                        SET keltner_upper = EXCLUDED.keltner_upper,
                            keltner_lower = EXCLUDED.keltner_lower,
                            rvi = EXCLUDED.rvi
                    """)
                    connection.execute(query, {
                        "timestamp": row["timestamp"],
                        "symbol": row["symbol"],
                        "timeframe": row["timeframe"],
                        "keltner_upper": row["keltner_upper"],
                        "keltner_lower": row["keltner_lower"],
                        "rvi": row["rvi"],
                    })

            # print("Indicators saved to database.")

        except Exception as e:
            print(f"Error saving indicators to the database: {e}")

    def save_risk_params(self, symbol, stoploss, position_size, max_allocation, partial_sell_fraction):
        query = text("""
            INSERT INTO portfolio_risk_parameters (symbol, stoploss, position_size, max_allocation, partial_sell_fraction)
            VALUES (:symbol, :stoploss, :position_size, :max_allocation, :partial_sell_fraction)
            ON CONFLICT(symbol) DO UPDATE 
            SET stoploss = EXCLUDED.stoploss,
                position_size = EXCLUDED.position_size,
                max_allocation = EXCLUDED.max_allocation,
                partial_sell_fraction = EXCLUDED.partial_sell_fraction
        """)
        with self.engine.connect() as connection:
            connection.execute(query, {
                "symbol": symbol,
                "stoploss": stoploss,
                "position_size": position_size,
                "max_allocation": max_allocation,
                "partial_sell_fraction": partial_sell_fraction
            })
            connection.commit()

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

    def save_indicator_params(self, symbol, timeframe,
                            keltner_upper_multiplier, keltner_lower_multiplier, keltner_period,
                            rvi_15m_period, rvi_1h_period,
                            rvi_15m_upper_threshold, rvi_15m_lower_threshold,
                            rvi_1h_upper_threshold, rvi_1h_lower_threshold,
                            include_15m_rvi=1):  
        """
        Save or update indicator parameters for a given symbol and timeframe.
        """
        query = text("""
            INSERT INTO indicator_params (symbol, timeframe, 
                                        keltner_upper_multiplier, keltner_lower_multiplier, keltner_period,
                                        rvi_15m_period, rvi_1h_period,
                                        rvi_15m_upper_threshold, rvi_15m_lower_threshold,
                                        rvi_1h_upper_threshold, rvi_1h_lower_threshold,
                                        include_15m_rvi)
            VALUES (:symbol, :timeframe, 
                    :keltner_upper_multiplier, :keltner_lower_multiplier, :keltner_period,
                    :rvi_15m_period, :rvi_1h_period,
                    :rvi_15m_upper_threshold, :rvi_15m_lower_threshold,
                    :rvi_1h_upper_threshold, :rvi_1h_lower_threshold,
                    :include_15m_rvi)
            ON CONFLICT(symbol, timeframe) DO UPDATE SET
                keltner_upper_multiplier = EXCLUDED.keltner_upper_multiplier,
                keltner_lower_multiplier = EXCLUDED.keltner_lower_multiplier,
                keltner_period = EXCLUDED.keltner_period,
                rvi_15m_period = EXCLUDED.rvi_15m_period,
                rvi_1h_period = EXCLUDED.rvi_1h_period,
                rvi_15m_upper_threshold = EXCLUDED.rvi_15m_upper_threshold,
                rvi_15m_lower_threshold = EXCLUDED.rvi_15m_lower_threshold,
                rvi_1h_upper_threshold = EXCLUDED.rvi_1h_upper_threshold,
                rvi_1h_lower_threshold = EXCLUDED.rvi_1h_lower_threshold,
                include_15m_rvi = EXCLUDED.include_15m_rvi;
        """)

        with self.engine.begin() as connection:
            connection.execute(query, {
                "symbol": symbol,
                "timeframe": timeframe,
                "keltner_upper_multiplier": keltner_upper_multiplier,
                "keltner_lower_multiplier": keltner_lower_multiplier,
                "keltner_period": keltner_period,
                "rvi_15m_period": rvi_15m_period,
                "rvi_1h_period": rvi_1h_period,
                "rvi_15m_upper_threshold": rvi_15m_upper_threshold,
                "rvi_15m_lower_threshold": rvi_15m_lower_threshold,
                "rvi_1h_upper_threshold": rvi_1h_upper_threshold,
                "rvi_1h_lower_threshold": rvi_1h_lower_threshold,
                "include_15m_rvi": include_15m_rvi  
            })

    def fetch_indicator_params(self, symbol, timeframe):
        """
        Fetch indicator parameters for a given symbol and timeframe.
        If no parameters exist, save default parameters and return them.
        """
        query = text("""
            SELECT keltner_upper_multiplier, keltner_lower_multiplier, keltner_period,
                rvi_15m_period, rvi_1h_period,
                rvi_15m_upper_threshold, rvi_15m_lower_threshold,
                rvi_1h_upper_threshold, rvi_1h_lower_threshold,
                COALESCE(include_15m_rvi, 1) 
            FROM indicator_params
            WHERE symbol = :symbol AND timeframe = :timeframe
        """)

        with self.engine.connect() as connection:
            result = connection.execute(query, {"symbol": symbol, "timeframe": timeframe}).fetchone()

        if result:
            return list(result)  # ✅ Ensure 10 values are always returned

        else:
            # ✅ Insert default parameters if they don’t exist
            default_params = {
                "symbol": symbol,
                "timeframe": timeframe,
                "keltner_upper_multiplier": 3.0,
                "keltner_lower_multiplier": 3.0,
                "keltner_period": 24,
                "rvi_15m_period": 10,
                "rvi_1h_period": 10,
                "rvi_15m_upper_threshold": 0.2,
                "rvi_15m_lower_threshold": -0.2,
                "rvi_1h_upper_threshold": 0.2,
                "rvi_1h_lower_threshold": -0.2,
                "include_15m_rvi": 1  
            }

            # print(f"Inserting default parameters for {symbol} ({timeframe}).")
            self.save_indicator_params(**default_params)
            
            # ✅ Ensure we return exactly 10 values
            return list(default_params.values())[2:]  # Skip `symbol` and `timeframe`


    def fetch_include_15m_rvi(self, symbol: str, timeframe: str) -> bool:
        """
        Fetch the 15m RVI flag from indicator_params.
        """
        query = text("""
            SELECT include_15m_rvi
            FROM indicator_params
            WHERE symbol = :symbol AND timeframe = :timeframe
        """)
        
        with self.engine.connect() as connection:
            result = connection.execute(query, {"symbol": symbol, "timeframe": timeframe}).fetchone()

        return bool(result[0]) if result else False


    def get_last_stored_timestamp(self, symbol: str, timeframe: str) -> int:
        """
        Retrieve the most recent timestamp stored in the database for a given symbol and timeframe.
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

    def query_main_timeframe_data(self, symbol, timeframe, start_date=None):
        """
        Query the main timeframe data and its indicators, with an optional start_date for lookback filtering.

        :param symbol: The trading pair symbol.
        :param timeframe: The timeframe (e.g., "1h", "15m").
        :param start_date: The earliest timestamp to include in the query (ISO format).
        :return: Pandas DataFrame containing the queried data.
        """
        query = """
            SELECT h.timestamp, h.open, h.high, h.low, h.close, h.volume,
                i.keltner_upper, i.keltner_lower, i.rvi,
                s.keltner_signal, s.rvi_signal, s.final_signal
            FROM historical_data h
            LEFT JOIN indicator_historical_data i
            ON h.timestamp = i.timestamp AND h.symbol = i.symbol AND h.timeframe = i.timeframe
            LEFT JOIN signals_data s
            ON h.timestamp = s.timestamp AND h.symbol = s.symbol AND h.timeframe = s.timeframe
            WHERE h.symbol = %(symbol)s AND h.timeframe = %(timeframe)s
        """
        params = {"symbol": symbol, "timeframe": timeframe}

        if start_date:
            query += " AND h.timestamp >= %(start_date)s"
            params["start_date"] = start_date

        query += " ORDER BY h.timestamp ASC"

        with self.engine.connect() as connection:
            return pd.read_sql(query, connection, params=params)

    def query_15m_rvi_data(self, symbol, start_date=None):
        """
        Query the 15m RVI data for a given symbol with an optional start_date filter.
        
        :param symbol: The trading pair symbol.
        :param start_date: The earliest timestamp to include in the query (ISO format).
        :return: Pandas DataFrame containing the queried RVI data.
        """
        query = """
            SELECT timestamp, rvi 
            FROM indicator_historical_data
            WHERE symbol = %(symbol)s AND timeframe = '15m'
        """
        params = {"symbol": symbol}

        if start_date:
            query += " AND timestamp >= %(start_date)s"
            params["start_date"] = start_date

        query += " ORDER BY timestamp ASC"

        with self.engine.connect() as connection:
            return pd.read_sql(query, connection, params=params)

    def get_historical_data(self, ticker, timeframe="1h"):
        query = text(f"""
            SELECT timestamp, open, high, low, close, volume
            FROM historical_data
            WHERE symbol = '{ticker}' AND timeframe = '{timeframe}'
            ORDER BY timestamp ASC
        """)
        with self.engine.connect() as conn:
            result = conn.execute(query)
            df = pd.DataFrame(result.fetchall(), columns=[col.lower().strip() for col in result.keys()])
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df