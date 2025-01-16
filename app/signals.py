import pandas as pd
from app.indicators import Indicators
from app.database import DatabaseManager

class SignalGenerator:
    def __init__(self, db_manager=None):
        self.indicators = Indicators()
        self.db_manager = db_manager 

    def generate_signals(self, df: pd.DataFrame, symbol: str = None, timeframe: str = None, 
                        keltner_params: dict = None, rvi_params: dict = None) -> pd.DataFrame:
        if df.empty:
            raise ValueError("Input DataFrame is empty.")
        # print("Input DataFrame head:\n", df.head())  # Debug input DataFrame

        if not keltner_params or not rvi_params:
            if not symbol or not timeframe:
                raise ValueError("Either 'symbol' and 'timeframe' or both 'keltner_params' and 'rvi_params' must be provided.")
            # Fetch parameters dynamically if not provided
            params = self.db_manager.fetch_indicator_params(symbol, timeframe)
            if not params:
                raise ValueError(f"No parameters found for {symbol} ({timeframe}).")

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
        # print("Keltner parameters:", keltner_params)  # Debug Keltner parameters
        # print("RVI parameters:", rvi_params)  # Debug RVI parameters

        # Calculate indicators
        df = pd.concat([df, self.indicators.calculate_keltner_channel(df, **keltner_params)], axis=1)
        df = df.loc[:, ~df.columns.duplicated()]
        # print("After Keltner Channel calculation:\n", df[['timestamp', 'keltner_upper', 'keltner_lower']].tail())  # Debug Keltner

        df = pd.concat([df, self.indicators.calculate_rvi(df, period=rvi_params["period"])], axis=1)
        df = df.loc[:, ~df.columns.duplicated()]
        # print("After RVI calculation:\n", df[['timestamp', 'rvi']].tail())  # Debug RVI

        # Generate signals
        df = pd.concat([df, self.generate_keltner_signals(df)], axis=1)
        df = df.loc[:, ~df.columns.duplicated()]
        # print("Keltner signals:\n", df[['timestamp', 'keltner_signal']].tail())  # Debug Keltner signals

        df = pd.concat([df, self.generate_rvi_signals(df, rvi_params["thresholds"])], axis=1)
        df = df.loc[:, ~df.columns.duplicated()]
        # print("RVI signals:\n", df[['timestamp', 'rvi_signal']].tail())  # Debug RVI signals

        df = pd.concat([df, self.combine_signals(df)], axis=1)
        df = df.loc[:, ~df.columns.duplicated()]
        # print("Final signals:\n", df[['timestamp', 'final_signal']].tail())  # Debug final signals

        return df


    @staticmethod
    def generate_keltner_signals(df: pd.DataFrame) -> pd.DataFrame:
        if 'keltner_upper' not in df.columns or 'keltner_lower' not in df.columns:
            raise ValueError("Keltner Channel bands ('keltner_upper', 'keltner_lower') are missing in the DataFrame.")

        df['keltner_signal'] = 0
        df.loc[df['close'] < df['keltner_lower'], 'keltner_signal'] = 1
        df.loc[df['close'] > df['keltner_upper'], 'keltner_signal'] = -1
        return df[['keltner_signal']]

    @staticmethod
    def generate_rvi_signals(df: pd.DataFrame, thresholds: dict) -> pd.DataFrame:
        if 'rvi' not in df.columns:
            raise ValueError("RVI column is missing in the DataFrame.")

        df['rvi_signal'] = 0
        df.loc[df['rvi'] < thresholds['lower'], 'rvi_signal'] = 1
        df.loc[df['rvi'] > thresholds['upper'], 'rvi_signal'] = -1
        return df[['rvi_signal']]

    @staticmethod
    def combine_signals(df: pd.DataFrame) -> pd.DataFrame:
        if 'keltner_signal' not in df.columns or 'rvi_signal' not in df.columns:
            raise ValueError("Required signal columns ('keltner_signal', 'rvi_signal') are missing in the DataFrame.")

        df['final_signal'] = df['keltner_signal'] + df['rvi_signal']
        df['final_signal'] = df['final_signal'].apply(lambda x: 1 if x > 1 else -1 if x < -1 else 0)
        return df[['final_signal']]

if __name__ == "__main__":
    # Example usage
    data = pd.read_csv("data/raw_data/BTC_USDT_1h.csv")

    # Define indicator parameters
    keltner_params = {"period": 24, "multiplier": 2.0}
    rvi_params = {"period": 24, "thresholds": (-0.2, 0.2)}

    signal_gen = SignalGenerator()
    signals_df = signal_gen.generate_signals(data, keltner_params, rvi_params)

    print("Generated Signals:")
    print(signals_df.tail())
