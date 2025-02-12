import pandas as pd
from sqlalchemy import text
from app.controllers.indicator_generator import Indicators

class SignalGenerator:
    def __init__(self, db_manager):
        self.indicators = Indicators()
        self.db_manager = db_manager

    def calculate_and_store_indicators(self, symbol: str, timeframe: str, keltner_params: dict, rvi_params: dict):
        """
        Calculate indicators (Keltner Channels & RVI) and store them in the database.
        """
        # Fetch historical data
        query = f"""
            SELECT timestamp, open, high, low, close, volume, symbol, timeframe
            FROM historical_data
            WHERE symbol = '{symbol}' AND timeframe = '{timeframe}'
            ORDER BY timestamp ASC
        """
        with self.db_manager.engine.connect() as connection:
            df = pd.read_sql(query, connection)

        if df.empty:
            print(f"Warning: No historical data found for {symbol} ({timeframe}).")
            return None

        try:
            # Ensure required columns exist
            required_columns = {"timestamp", "open", "high", "low", "close", "volume", "symbol", "timeframe"}
            if not required_columns.issubset(df.columns):
                raise ValueError(f"Missing columns: {required_columns - set(df.columns)}")

            # Convert timestamp
            df["timestamp"] = pd.to_datetime(df["timestamp"])

            # Sort data
            df = df.sort_values("timestamp").reset_index(drop=True)

            # ✅ Step 1: Calculate Keltner Channels (using both upper & lower multipliers)
            keltner_df = self.indicators.calculate_keltner_channel(
                df[["high", "low", "close"]],
                period=keltner_params["period"],
                upper_multiplier=keltner_params["upper_multiplier"],
                lower_multiplier=keltner_params["lower_multiplier"],
            )
            df["keltner_upper"] = keltner_df["keltner_upper"]
            df["keltner_lower"] = keltner_df["keltner_lower"]

            # ✅ Step 2: Calculate RVI
            rvi_df = self.indicators.calculate_rvi(
                df[["open", "high", "low", "close"]],
                period=rvi_params["period"]
            )
            df["rvi"] = rvi_df["rvi"]

            # ✅ Step 3: Save indicators
            indicators_df = df[["timestamp", "symbol", "timeframe", "keltner_upper", "keltner_lower", "rvi"]]
            self.db_manager.save_indicators_to_db(indicators_df)

            # print(f"Indicators stored for {symbol} ({timeframe}).")
            return df  # Returning df for further processing if needed

        except Exception as e:
            print(f"Error calculating and storing indicators: {e}")
            return None

    def generate_final_signals(self, symbol, timeframe, include_15m_rvi=False):
        """
        Fetch stored indicators, merge OHLCV data, merge 15m RVI if needed, and generate final signals.
        """
        try:
            # Step 1: Fetch stored OHLCV & indicator data
            query = f"""
                SELECT h.timestamp, h.open, h.high, h.low, h.close, h.volume,
                    i.keltner_upper, i.keltner_lower, i.rvi
                FROM historical_data h
                LEFT JOIN indicator_historical_data i
                ON h.timestamp = i.timestamp 
                AND h.symbol = i.symbol 
                AND h.timeframe = i.timeframe
                WHERE h.symbol = '{symbol}' 
                AND h.timeframe = '{timeframe}'
                ORDER BY h.timestamp ASC
            """
            with self.db_manager.engine.connect() as connection:
                df = pd.read_sql(query, connection)

            if "symbol" not in df.columns:
                df["symbol"] = symbol  

            if "timeframe" not in df.columns:
                df["timeframe"] = timeframe  

            if df.empty:
                print(f"Warning: No data found for {symbol} ({timeframe}).")
                return None

            # Ensure timestamp is datetime
            df["timestamp"] = pd.to_datetime(df["timestamp"])

            # Step 2: Fetch 15m RVI if needed
            if include_15m_rvi and timeframe == "1h":
                df_15m = self._fetch_15m_rvi_data(symbol)
                df = self._merge_15m_rvi(df, df_15m)

            # Step 3: Generate trading signals
            df = self._generate_keltner_signals(df)
            df = self._generate_rvi_signals(df, symbol, timeframe)
            df = self._generate_final_signal(df, include_15m_rvi)

            # Step 4: Save signals to the database
            self.db_manager.save_signals_to_db(df)

            print(f"Final signals stored for {symbol} ({timeframe}).")
            return df

        except Exception as e:
            print(f"Error generating final signals: {e}")
            return None

    def _generate_keltner_signals(self, df):
        """Generate Keltner channel signals based on upper and lower bands."""
        df["keltner_signal"] = 0
        df.loc[df["close"] > df["keltner_upper"], "keltner_signal"] = -1  # Sell signal
        df.loc[df["close"] < df["keltner_lower"], "keltner_signal"] = 1   # Buy signal
        return df

    def _generate_rvi_signals(self, df, symbol, timeframe):
        """Generate RVI signals using thresholds from the database."""
        df["rvi_signal"] = 0

        # Fetch thresholds from the database
        params = self.db_manager.fetch_indicator_params(symbol, timeframe)
        if not params:
            print(f"Error: No indicator parameters found for {symbol} ({timeframe}). Using default RVI thresholds.")
            return df

        # Assign correct threshold based on timeframe
        _, _, _, _, _, rvi_15m_upper_threshold, rvi_15m_lower_threshold, rvi_1h_upper_threshold, rvi_1h_lower_threshold, _ = params

        rvi_upper_threshold = rvi_1h_upper_threshold if timeframe == "1h" else rvi_15m_upper_threshold
        rvi_lower_threshold = rvi_1h_lower_threshold if timeframe == "1h" else rvi_15m_lower_threshold

        # Apply thresholds dynamically
        df.loc[df["rvi"] < rvi_lower_threshold, "rvi_signal"] = 1  # Buy signal
        df.loc[df["rvi"] > rvi_upper_threshold, "rvi_signal"] = -1  # Sell signal
        return df

    def _fetch_15m_rvi_data(self, symbol):
        """Fetch pre-calculated 15m RVI data and apply dynamic thresholds."""
        query = f"""
            SELECT timestamp, rvi AS rvi_15m
            FROM indicator_historical_data
            WHERE symbol = '{symbol}' AND timeframe = '15m'
            ORDER BY timestamp ASC
        """
        with self.db_manager.engine.connect() as connection:
            df_15m = pd.read_sql(query, connection)

        if df_15m.empty:
            return None

        df_15m["timestamp"] = pd.to_datetime(df_15m["timestamp"])
        df_15m["rvi_signal_15m"] = 0

        # Fetch RVI thresholds for 15m
        params = self.db_manager.fetch_indicator_params(symbol, "15m")
        if not params:
            print(f"Error: No indicator parameters found for {symbol} (15m). Using default thresholds.")
            rvi_15m_lower_threshold, rvi_15m_upper_threshold = -0.2, 0.2
        else:
            _, _, _, _, _, rvi_15m_upper_threshold, rvi_15m_lower_threshold, _, _, _ = params

        # Apply 15m RVI thresholds dynamically
        df_15m.loc[df_15m["rvi_15m"] < rvi_15m_lower_threshold, "rvi_signal_15m"] = 1  # Buy
        df_15m.loc[df_15m["rvi_15m"] > rvi_15m_upper_threshold, "rvi_signal_15m"] = -1  # Sell
        return df_15m[["timestamp", "rvi_signal_15m"]]

    def _merge_15m_rvi(self, df, df_15m):
        """Merge 15m RVI data with the main DataFrame."""
        if df_15m is not None:
            df = pd.merge_asof(
                df.sort_values("timestamp"),
                df_15m.sort_values("timestamp"),
                on="timestamp",
                direction="backward",
                tolerance=pd.Timedelta("15m")
            )
            df["rvi_signal_15m"] = df["rvi_signal_15m"].fillna(0).astype(int)
        else:
            df["rvi_signal_15m"] = 0 
        return df

    def _generate_final_signal(self, df, include_15m_rvi):
        """Generate the final trading signal based on strict conditions."""
        
        # Ensure 'rvi_signal_15m' column exists
        if "rvi_signal_15m" not in df.columns:
            df["rvi_signal_15m"] = 0  

        # STRICT BUY CONDITION: Both Keltner & RVI must confirm a buy
        df["final_signal"] = 0
        df.loc[
            (df["keltner_signal"] == 1) & 
            (df["rvi_signal"] == 1) & 
            ((df["rvi_signal_15m"] == 1) if include_15m_rvi else True),
            "final_signal"
        ] = 1  # BUY Signal

        # STRICT SELL CONDITION: Both Keltner & RVI must confirm a sell
        df.loc[
            (df["keltner_signal"] == -1) & 
            (df["rvi_signal"] == -1) & 
            ((df["rvi_signal_15m"] == -1) if include_15m_rvi else True),
            "final_signal"
        ] = -1  # SELL Signal

        return df



