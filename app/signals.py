import pandas as pd
from app.indicators import Indicators


class SignalGenerator:
    def __init__(self, db_manager=None):
        self.indicators = Indicators()
        self.db_manager = db_manager

    def generate_signals(self, df: pd.DataFrame, keltner_params: dict, rvi_params: dict, timeframe: str, df_15m: pd.DataFrame = None) -> pd.DataFrame:
        """
        Generate signals, including 15m RVI conditions only for hourly data.
        """
        # Validate input DataFrame
        self._validate_dataframe(df, required_columns=['timestamp', 'close'])

        # Calculate indicators for the main timeframe
        df = self._calculate_main_indicators(df, keltner_params, rvi_params)

        # Include 15m RVI signals only for hourly data
        if timeframe == '1h' and df_15m is not None:
            self._validate_dataframe(df_15m, required_columns=['timestamp'])
            df = self._merge_15m_rvi(df, df_15m, rvi_params)

        # Combine all signals into the final signal
        df = self.combine_signals(df, include_15m_rvi=(timeframe == '1h' and df_15m is not None))
        return df


    def _calculate_main_indicators(self, df, keltner_params, rvi_params):
        """
        Calculate Keltner Channel and RVI indicators for the main timeframe.
        """
        df = pd.concat([df, self.indicators.calculate_keltner_channel(df, **keltner_params)], axis=1)
        df = pd.concat([df, self.indicators.calculate_rvi(df, period=rvi_params["period"])], axis=1)
        df = df.fillna(0)  
        df = self._remove_duplicated_columns(df)
        df = pd.concat([df, self.generate_keltner_signals(df)], axis=1)
        df = pd.concat([df, self.generate_rvi_signals(df, rvi_params["thresholds"])], axis=1)
        df = self._remove_duplicated_columns(df)
        return df

    def _merge_15m_rvi(self, df, df_15m, rvi_params):
        """
        Calculate RVI for the 15m data and merge the `rvi_signal_15m` into the main DataFrame.

        :param df: The main DataFrame for the selected timeframe.
        :param df_15m: The 15m OHLC data DataFrame.
        :param rvi_params: Parameters for RVI calculation (e.g., period, thresholds).
        :return: The main DataFrame with the `rvi_signal_15m` column merged.
        """
        if df_15m is None or df_15m.empty:
            print("Warning: 15m data is unavailable. Adding default rvi_signal_15m as 0.")
            df["rvi_signal_15m"] = 0
            return df

        # Calculate RVI for the 15m data
        df_15m = pd.concat([df_15m, self.indicators.calculate_rvi(df_15m, period=rvi_params["period"])], axis=1)

        # Define RVI thresholds
        thresholds = rvi_params.get("thresholds", {"lower": -0.2, "upper": 0.2})

        # Generate RVI signals based on thresholds
        df_15m["rvi_signal_15m"] = 0
        df_15m.loc[df_15m["rvi"] < thresholds["lower"], "rvi_signal_15m"] = 1
        df_15m.loc[df_15m["rvi"] > thresholds["upper"], "rvi_signal_15m"] = -1

        # Prepare 15m RVI data for merging
        df_15m = df_15m[["timestamp", "rvi_signal_15m"]]

        # Ensure both DataFrames are sorted by 'timestamp' for merge_asof
        df = df.sort_values("timestamp")
        df_15m = df_15m.sort_values("timestamp")

        # Perform asof merge to align 15m RVI signals with the main DataFrame
        df = pd.merge_asof(
            df,
            df_15m,
            on="timestamp",
            direction="backward",
            tolerance=pd.Timedelta("15m")  # Adjust tolerance as needed
        )

        # Fill any missing RVI signals with 0
        df["rvi_signal_15m"] = df["rvi_signal_15m"].fillna(0).astype(int)

        return df


    def combine_signals(self, df: pd.DataFrame, include_15m_rvi: bool = False) -> pd.DataFrame:
        """
        Combine Keltner and RVI signals into a final signal.
        Optionally include 15m RVI conditions.
        """
        # df["final_signal"] = 0

        if include_15m_rvi:
            # Include 15m RVI in final signal logic
            df.loc[
                (df["keltner_signal"] == 1) & (df["rvi_signal"] == 1) & (df["rvi_signal_15m"] == 1),
                "final_signal",
            ] = 1
            df.loc[
                (df["keltner_signal"] == -1) & (df["rvi_signal"] == -1) & (df["rvi_signal_15m"] == -1),
                "final_signal",
            ] = -1
        else:
            # Use only main timeframe signals
            df.loc[(df["keltner_signal"] == 1) & (df["rvi_signal"] == 1), "final_signal"] = 1
            df.loc[(df["keltner_signal"] == -1) & (df["rvi_signal"] == -1), "final_signal"] = -1

        return df

    @staticmethod
    def generate_keltner_signals(df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate buy/sell signals based on Keltner Channel.
        """
        if 'keltner_upper' not in df.columns or 'keltner_lower' not in df.columns:
            raise ValueError("Keltner Channel bands ('keltner_upper', 'keltner_lower') are missing in the DataFrame.")

        df['keltner_signal'] = 0
        df.loc[df['close'] < df['keltner_lower'], 'keltner_signal'] = 1
        df.loc[df['close'] > df['keltner_upper'], 'keltner_signal'] = -1
        return df[['keltner_signal']]

    @staticmethod
    def generate_rvi_signals(df: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
        """
        Generate buy/sell signals based on RVI values.
        """
        if 'rvi' not in df.columns:
            raise ValueError("RVI column is missing in the DataFrame.")

        df['rvi_signal'] = 0
        df.loc[df['rvi'] < thresholds['lower'], 'rvi_signal'] = 1
        df.loc[df['rvi'] > thresholds['upper'], 'rvi_signal'] = -1
        return df[['rvi_signal']]

    @staticmethod
    def _validate_dataframe(df: pd.DataFrame, required_columns: list):
        """
        Validate the input DataFrame for required columns.
        """
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns in DataFrame: {missing_columns}")

    @staticmethod
    def _remove_duplicated_columns(df: pd.DataFrame) -> pd.DataFrame:
        """
        Remove duplicate columns from a DataFrame and ensure unique column names.
        """
        if df.columns.duplicated().any():
            # print("Removing duplicated columns:", df.columns[df.columns.duplicated()])
            return df.loc[:, ~df.columns.duplicated()]


