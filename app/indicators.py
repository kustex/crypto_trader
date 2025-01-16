import pandas as pd

class Indicators:
    """
    Provides methods to calculate various trading indicators.
    """

    @staticmethod
    def calculate_keltner_channel(df: pd.DataFrame, period: int = 24, multiplier: float = 2.0):
        """
        Calculate the Keltner Channel (upper, lower, and mid bands).

        :param df: DataFrame containing OHLCV data.
        :param period: Lookback period for the moving average and ATR.
        :param multiplier: Multiplier for the ATR to calculate channel bands.
        :return: DataFrame with 'keltner_upper', 'keltner_lower', and 'keltner_mid' columns.
        """
        if len(df) < period:
            raise ValueError(f"Not enough data to calculate the indicator. Minimum {period} rows required.")

        # Calculate typical price
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3

        # Calculate Exponential Moving Average (EMA) of the typical price
        df['keltner_mid'] = df['typical_price'].ewm(span=period, adjust=False).mean()

        # Calculate the Average True Range (ATR)
        df['true_range'] = df[['high', 'low', 'close']].apply(
            lambda x: max(x['high'] - x['low'], abs(x['high'] - x['close']), abs(x['low'] - x['close'])), axis=1
        )
        df['atr'] = df['true_range'].ewm(span=period, adjust=False).mean()

        # Calculate upper and lower bands
        df['keltner_upper'] = df['keltner_mid'] + (multiplier * df['atr'])
        df['keltner_lower'] = df['keltner_mid'] - (multiplier * df['atr'])

        return df[['keltner_upper', 'keltner_lower', 'keltner_mid']]

    @staticmethod
    def calculate_rvi(df: pd.DataFrame, period: int = 24):
        """
        Calculate the Relative Vigor Index (RVI).

        :param df: DataFrame containing OHLCV data.
        :param period: Lookback period for the RVI calculation.
        :return: DataFrame with 'rvi' column.
        """
        if len(df) < period:
            raise ValueError(f"Not enough data to calculate the indicator. Minimum {period} rows required.")


        # Calculate numerator and denominator
        df['numerator'] = (df['close'] - df['open'] + 2 * (df['close'].shift(1) - df['open'].shift(1)) +
                           (df['close'].shift(2) - df['open'].shift(2))) / 6
        df['denominator'] = (df['high'] - df['low'] + 2 * (df['high'].shift(1) - df['low'].shift(1)) +
                             (df['high'].shift(2) - df['low'].shift(2))) / 6

        # Calculate RVI
        df['rvi'] = df['numerator'].rolling(window=period).sum() / df['denominator'].rolling(window=period).sum()

        return df[['rvi']]

if __name__ == "__main__":
    # Example usage
    # Load a sample dataset
    data = pd.read_csv("data/raw_data/BTC_USDT_1h.csv")

    # Calculate indicators
    indicators = Indicators()
    keltner = indicators.calculate_keltner_channel(data)
    rvi = indicators.calculate_rvi(data)

    # Merge and display results
    result = pd.concat([data, keltner, rvi], axis=1)
    print(result.tail())
