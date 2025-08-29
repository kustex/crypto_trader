import pandas as pd
import numpy as np
import numba

# ------------------------
# Numba helper functions
# ------------------------

@numba.njit
def compute_true_range(high, low, close):
    n = high.shape[0]
    true_range = np.empty(n)
    for i in range(n):
        diff1 = high[i] - low[i]
        diff2 = np.abs(high[i] - close[i])
        diff3 = np.abs(low[i] - close[i])
        # Manually compute max since Python's max() may not be supported in nopython mode
        if diff1 >= diff2 and diff1 >= diff3:
            true_range[i] = diff1
        elif diff2 >= diff3:
            true_range[i] = diff2
        else:
            true_range[i] = diff3
    return true_range

@numba.njit
def compute_ema(data, span):
    n = data.shape[0]
    ema = np.empty(n)
    alpha = 2.0 / (span + 1)
    ema[0] = data[0]
    for i in range(1, n):
        ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]
    return ema

@numba.njit
def rolling_mean(data, window):
    n = data.shape[0]
    result = np.empty(n)
    for i in range(n):
        if i < window - 1:
            result[i] = np.nan
        else:
            s = 0.0
            for j in range(i - window + 1, i + 1):
                s += data[j]
            result[i] = s / window
    return result

@numba.njit
def compute_rvi(close, open_, high, low, period):
    n = close.shape[0]
    numerator = np.empty(n)
    denominator = np.empty(n)
    # For the first few indices, we set values to NaN since there is insufficient history.
    for i in range(n):
        if i < 3:
            numerator[i] = np.nan
            denominator[i] = np.nan
        else:
            numerator[i] = ((close[i] - open_[i]) +
                            2 * (close[i - 1] - open_[i - 1]) +
                            2 * (close[i - 2] - open_[i - 2]) +
                            (close[i - 3] - open_[i - 3])) / 6.0
            denominator[i] = ((high[i] - low[i]) +
                              2 * (high[i - 1] - low[i - 1]) +
                              2 * (high[i - 2] - low[i - 2]) +
                              (high[i - 3] - low[i - 3])) / 6.0
    num_mean = rolling_mean(numerator, period)
    den_mean = rolling_mean(denominator, period)
    rvi = np.empty(n)
    for i in range(n):
        if np.isnan(num_mean[i]) or np.isnan(den_mean[i]) or den_mean[i] == 0.0:
            rvi[i] = np.nan
        else:
            rvi[i] = num_mean[i] / den_mean[i]
    return rvi

# ------------------------
# Indicators class
# ------------------------

class Indicators:
    """
    Provides methods to calculate various trading indicators with Numba acceleration.
    """

    @staticmethod
    def calculate_keltner_channel(df: pd.DataFrame, period: int, upper_multiplier: float, lower_multiplier: float):
        """
        Calculate the Keltner Channels for the given DataFrame using Numba-accelerated computations.

        :param df: DataFrame containing OHLC data (must include 'high', 'low', 'close' columns).
        :param period: The period for computing the moving average and ATR.
        :param upper_multiplier: Multiplier for ATR to calculate the upper band.
        :param lower_multiplier: Multiplier for ATR to calculate the lower band.
        :return: DataFrame with columns 'keltner_upper', 'keltner_lower', and 'keltner_mid'.
        """
        # Work on a copy to avoid modifying the original data
        df = df.copy()
        
        # Convert required columns to NumPy arrays
        high = df['high'].to_numpy(dtype=np.float64)
        low = df['low'].to_numpy(dtype=np.float64)
        close = df['close'].to_numpy(dtype=np.float64)
        
        # Step 1: Compute typical price
        typical_price = (high + low + close) / 3.0
        
        # Step 2: Calculate the EMA of the typical price (the channel's midline)
        keltner_mid = compute_ema(typical_price, period)
        
        # Step 3: Calculate the true range and then the ATR (using EMA of the true range)
        true_range = compute_true_range(high, low, close)
        atr = compute_ema(true_range, period)
        
        # Step 4: Calculate the upper and lower bands
        keltner_upper = keltner_mid + upper_multiplier * atr
        keltner_lower = keltner_mid - lower_multiplier * atr
        
        # Build a new DataFrame with the results; preserve the original index
        result = pd.DataFrame({
            'keltner_upper': keltner_upper,
            'keltner_lower': keltner_lower,
            'keltner_mid': keltner_mid
        }, index=df.index)
        return result

    @staticmethod
    def calculate_rvi(df: pd.DataFrame, period: int):
        """
        Calculate the Relative Vigor Index (RVI) for the given DataFrame using Numba acceleration.

        :param df: DataFrame containing OHLC data (must include 'open', 'high', 'low', 'close' columns).
        :param period: The period for the rolling mean used in RVI calculation.
        :return: DataFrame with a single column 'rvi'.
        """
        df = df.copy()
        
        # Convert necessary columns to NumPy arrays
        close = df['close'].to_numpy(dtype=np.float64)
        open_ = df['open'].to_numpy(dtype=np.float64)
        high = df['high'].to_numpy(dtype=np.float64)
        low = df['low'].to_numpy(dtype=np.float64)
        
        # Compute the RVI using the numba-accelerated function
        rvi = compute_rvi(close, open_, high, low, period)
        
        # Return the result as a DataFrame with the original index
        result = pd.DataFrame({'rvi': rvi}, index=df.index)
        return result
