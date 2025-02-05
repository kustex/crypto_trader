import pandas as pd
from sqlalchemy import text
from app.indicators import Indicators


class SignalGenerator:
    def __init__(self, db_manager):
        self.indicators = Indicators()
        self.db_manager = db_manager

    def calculate_and_store_indicators(self, df: pd.DataFrame, keltner_params: dict, rvi_params: dict):
        """
        Calculate indicators (Keltner Channels and RVI) and store them in the PostgreSQL database.
        """
        if df.empty:
            print("Warning: DataFrame is empty. Skipping indicator calculation.")
            return

        try:
            # Ensure required columns are present
            required_columns = {"timestamp", "open", "high", "low", "close", "volume", "symbol", "timeframe"}
            if not required_columns.issubset(df.columns):
                raise ValueError(f"Missing required columns: {required_columns - set(df.columns)}")

            # Sort the data by timestamp
            df = df.sort_values("timestamp").reset_index(drop=True)

            # Step 1: Calculate Keltner Channels
            keltner_df = self.indicators.calculate_keltner_channel(
                df[["high", "low", "close"]], **keltner_params
            )
            df["keltner_upper"] = keltner_df["keltner_upper"]
            df["keltner_lower"] = keltner_df["keltner_lower"]

            # Step 2: Calculate RVI
            rvi_df = self.indicators.calculate_rvi(
                df[["open", "high", "low", "close"]], period=rvi_params["period"]
            )
            df["rvi"] = rvi_df["rvi"]

            # Step 3: Prepare DataFrame for storage
            indicators_df = df[["timestamp", "symbol", "timeframe", "keltner_upper", "keltner_lower", "rvi"]].copy()

            # Step 4: Ensure proper numeric types (avoid NoneType issues)
            indicators_df["keltner_upper"] = indicators_df["keltner_upper"].fillna(0.0)
            indicators_df["keltner_lower"] = indicators_df["keltner_lower"].fillna(0.0)
            indicators_df["rvi"] = indicators_df["rvi"].fillna(0.0)

            # Step 5: Save to PostgreSQL
            self.db_manager.save_indicators_to_db(indicators_df)

            print(f"Indicators stored for {indicators_df['symbol'].iloc[0]} ({indicators_df['timeframe'].iloc[0]}).")

        except Exception as e:
            print(f"Error calculating and storing indicators: {e}")

    def generate_signals(self, symbol, timeframe, include_15m_rvi=False):
        try:
            # Fetch the main data from PostgreSQL
            query = f"""
                SELECT h.timestamp, h.open, h.high, h.low, h.close, h.volume,
                    i.keltner_upper, i.keltner_lower, i.rvi,
                    h.symbol AS symbol
                FROM historical_data h
                LEFT JOIN indicator_historical_data i
                ON h.timestamp = i.timestamp AND h.symbol = i.symbol AND h.timeframe = i.timeframe
                WHERE h.symbol = '{symbol}' AND h.timeframe = '{timeframe}'
                ORDER BY h.timestamp ASC
            """
            with self.db_manager.engine.connect() as connection:
                df = pd.read_sql(query, connection)

            if df.empty:
                print(f"Warning: No data found for {symbol} ({timeframe}).")
                return None

            # Ensure timestamp is in datetime format
            df["timestamp"] = pd.to_datetime(df["timestamp"])

            # Handle missing 'timeframe' column
            if "timeframe" not in df.columns:
                df["timeframe"] = timeframe  

            # Convert columns to numeric to avoid FutureWarnings
            numeric_columns = ["open", "high", "low", "close", "volume", "keltner_upper", "keltner_lower", "rvi"]
            for col in numeric_columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

            # Generate signals
            df = self._generate_keltner_signals(df)
            df = self._generate_rvi_signals(df)

            if include_15m_rvi and timeframe == "1h":
                df_15m = self._fetch_15m_rvi_data(symbol)
                df = self._merge_15m_rvi(df, df_15m)
            
            df = self._generate_final_signal(df, include_15m_rvi)

            return df

        except Exception as e:
            print(f"Error generating signals: {e}")
            return None

    def _generate_keltner_signals(self, df):
        """
        Generate Keltner channel signals based on upper and lower bands.
        """
        df["keltner_signal"] = 0
        df.loc[df["close"] > df["keltner_upper"], "keltner_signal"] = -1  # Sell signal
        df.loc[df["close"] < df["keltner_lower"], "keltner_signal"] = 1   # Buy signal
        return df

    def _generate_rvi_signals(self, df):
        """
        Generate RVI signals based on thresholds.
        """
        df["rvi_signal"] = 0
        rvi_lower_threshold = -0.2
        rvi_upper_threshold = 0.2
        df.loc[df["rvi"] < rvi_lower_threshold, "rvi_signal"] = 1  # Buy signal
        df.loc[df["rvi"] > rvi_upper_threshold, "rvi_signal"] = -1  # Sell signal
        return df

    def _fetch_15m_rvi_data(self, symbol):
        """
        Fetch pre-calculated 15m RVI signals from the database.
        """
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
        df_15m = df_15m.sort_values("timestamp")

        # Generate 15m RVI signals
        rvi_lower_threshold = -0.2
        rvi_upper_threshold = 0.2
        df_15m["rvi_signal_15m"] = 0
        df_15m.loc[df_15m["rvi_15m"] < rvi_lower_threshold, "rvi_signal_15m"] = 1
        df_15m.loc[df_15m["rvi_15m"] > rvi_upper_threshold, "rvi_signal_15m"] = -1

        return df_15m[["timestamp", "rvi_signal_15m"]]

    def _merge_15m_rvi(self, df, df_15m):
        """
        Merge 15m RVI signals into the main DataFrame.
        """
        if df_15m is not None:
            df = pd.merge_asof(
                df.sort_values("timestamp"),
                df_15m.sort_values("timestamp"),
                on="timestamp",
                direction="backward",
            )
            df["rvi_signal_15m"] = df["rvi_signal_15m"].fillna(0).astype(int)
        else:
            df["rvi_signal_15m"] = 0  # Default if no 15m RVI data is available
        return df

    def _generate_final_signal(self, df, include_15m_rvi):
        df["final_signal"] = df["keltner_signal"] + df["rvi_signal"]

        # Ensure rvi_signal_15m is always present
        if "rvi_signal_15m" not in df.columns:
            df["rvi_signal_15m"] = 0  

        if include_15m_rvi:
            df["final_signal"] += df["rvi_signal_15m"]

        # Normalize signals to -1, 0, or 1
        df["final_signal"] = df["final_signal"].clip(-1, 1)
        return df

