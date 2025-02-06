import pandas as pd


class Indicators:
    """
    Provides methods to calculate various trading indicators.
    """

    @staticmethod
    def calculate_keltner_channel(df: pd.DataFrame, period: int, multiplier: float):
        """
        Calculate the Keltner Channels for the given DataFrame.

        :param df: DataFrame containing OHLC data (must have 'high', 'low', 'close' columns).
        :param period: The period for calculating the moving average and ATR.
        :param multiplier: The multiplier for the ATR to calculate upper and lower bands.
        :return: DataFrame with 'keltner_upper', 'keltner_lower', and 'keltner_mid' columns.
        """
        df = df.copy()  # Avoid modifying the original DataFrame
        
        # Step 1: Calculate the typical price
        df.loc[:, 'typical_price'] = (df['high'] + df['low'] + df['close']) / 3

        # Step 2: Calculate the exponential moving average (EMA) of the typical price
        df.loc[:, 'keltner_mid'] = df['typical_price'].ewm(span=period, adjust=False).mean()

        # Step 3: Calculate the true range and average true range (ATR)
        df.loc[:, 'true_range'] = df[['high', 'low', 'close']].apply(
            lambda x: max(x['high'] - x['low'], abs(x['high'] - x['close']), abs(x['low'] - x['close'])),
            axis=1
        )
        df.loc[:, 'atr'] = df['true_range'].ewm(span=period, adjust=False).mean()

        # Step 4: Calculate the upper and lower bands
        df.loc[:, 'keltner_upper'] = df['keltner_mid'] + (multiplier * df['atr'])
        df.loc[:, 'keltner_lower'] = df['keltner_mid'] - (multiplier * df['atr'])

        # Return only the relevant columns
        return df[['keltner_upper', 'keltner_lower', 'keltner_mid']]


    @staticmethod
    def calculate_rvi(df: pd.DataFrame, period: int):
        """
        Calculate the Relative Vigor Index (RVI) for the given DataFrame.

        :param df: DataFrame containing OHLC data (must have 'open', 'high', 'low', 'close' columns).
        :param period: The period for calculating the RVI.
        :return: DataFrame with the 'rvi' column.
        """
        df = df.copy()  # Avoid modifying the original DataFrame

        # Step 1: Calculate numerator and denominator for RVI
        df.loc[:, 'numerator'] = (
            (df['close'] - df['open']) +
            2 * ((df['close'].shift(1) - df['open'].shift(1))) +
            2 * ((df['close'].shift(2) - df['open'].shift(2))) +
            (df['close'].shift(3) - df['open'].shift(3))
        ) / 6

        df.loc[:, 'denominator'] = (
            (df['high'] - df['low']) +
            2 * ((df['high'].shift(1) - df['low'].shift(1))) +
            2 * ((df['high'].shift(2) - df['low'].shift(2))) +
            (df['high'].shift(3) - df['low'].shift(3))
        ) / 6

        # Step 2: Calculate RVI
        df.loc[:, 'rvi'] = df['numerator'].rolling(window=period).mean() / df['denominator'].rolling(window=period).mean()

        # Return only the 'rvi' column
        return df[['rvi']]
