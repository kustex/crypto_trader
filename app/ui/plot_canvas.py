import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from datetime import datetime, timedelta, timezone

# Define your local timezone (UTC+1)
LOCAL_TZ = timezone(timedelta(hours=1))

def to_local(ts):
    """
    Convert a UTC timestamp (as a pandas Timestamp) to local time (UTC+1).
    Assumes ts is timezone-naive or in UTC.
    """
    if ts.tzinfo is None:
        ts = ts.tz_localize('UTC')
    return ts.tz_convert(LOCAL_TZ)

def adjust_for_candle_close(ts, timeframe):
    """
    Given a candle's start time (as a pandas Timestamp in local time),
    add the candle duration so that the display time is the candle's close.
    """
    if timeframe.endswith("m"):
        minutes = int(timeframe[:-1])
        return ts + pd.Timedelta(minutes=minutes)
    elif timeframe.endswith("h"):
        hours = int(timeframe[:-1])
        return ts + pd.Timedelta(hours=hours)
    elif timeframe.endswith("d"):
        days = int(timeframe[:-1])
        return ts + pd.Timedelta(days=days)
    else:
        return ts

class PlotCanvas(FigureCanvas):
    def __init__(self, db_manager, parent=None, width=10, height=10, dpi=100):
        self.db_manager = db_manager
        # Create three subplots (main timeframe, RVI, 15m RVI)
        self.fig, self.axs = plt.subplots(3, 1, figsize=(width, height), dpi=dpi)
        super().__init__(self.fig)
        self.setParent(parent)

    def plot_data(self, symbol, timeframe, include_15m_rvi):
        """
        Query data and plot it based on the symbol, timeframe, and whether to include 15m RVI.
        """
        # Query the main timeframe data (assumed stored in UTC)
        main_df = self.db_manager.query_main_timeframe_data(symbol, timeframe)
        if main_df.empty:
            for ax in self.axs:
                ax.clear()
                ax.text(0.5, 0.5, "No Data Available", ha="center", va="center")
            self.draw()
            return

        # Convert the stored UTC timestamps to local time (UTC+1)
        main_df["timestamp"] = pd.to_datetime(main_df["timestamp"]).dt.tz_localize('UTC').dt.tz_convert(LOCAL_TZ)
        # Create a display column that shows the candle closing time
        main_df["display_timestamp"] = main_df["timestamp"].apply(lambda ts: adjust_for_candle_close(ts, timeframe))

        # Filter data for plotting range
        max_date = main_df["display_timestamp"].max()
        lookback_period = pd.Timedelta(days=30) if timeframe == "1h" else pd.Timedelta(days=180)
        min_date = max_date - lookback_period
        main_df = main_df[main_df["display_timestamp"] >= min_date]

        self._plot_main_timeframe(main_df, symbol, timeframe)
        self._plot_rvi(main_df, timeframe)

        # Query 15m RVI data if needed
        df_15m = self.db_manager.query_15m_rvi_data(symbol)
        if not df_15m.empty:
            df_15m["timestamp"] = pd.to_datetime(df_15m["timestamp"]).dt.tz_localize('UTC').dt.tz_convert(LOCAL_TZ)
            df_15m["display_timestamp"] = df_15m["timestamp"].apply(lambda ts: adjust_for_candle_close(ts, "15m"))
            df_15m = df_15m[df_15m["display_timestamp"] >= df_15m["display_timestamp"].max() - lookback_period]
        self._plot_15m_rvi(df_15m)
        
        self.fig.tight_layout()
        self.draw()

    def _plot_main_timeframe(self, df, symbol, timeframe):
        self.axs[0].clear()
        self.axs[0].plot(df["display_timestamp"], df["close"], label="Price", color="blue")
        self.axs[0].plot(df["display_timestamp"], df["keltner_upper"], label="Keltner Upper", color="green", linestyle="--")
        self.axs[0].plot(df["display_timestamp"], df["keltner_lower"], label="Keltner Lower", color="red", linestyle="--")

        buy_signals = df[df["final_signal"] == 1]
        sell_signals = df[df["final_signal"] == -1]
        self.axs[0].scatter(buy_signals["display_timestamp"], buy_signals["close"], color="green", label="Buy Signal", marker="^")
        self.axs[0].scatter(sell_signals["display_timestamp"], sell_signals["close"], color="red", label="Sell Signal", marker="v")

        if not df.empty:
            last_time = df["display_timestamp"].iloc[-1]
            last_close = df["close"].iloc[-1]
            self.axs[0].annotate(f"{last_close:.2f}", 
                                 xy=(last_time, last_close), 
                                 xytext=(5, 0), 
                                 textcoords="offset points", 
                                 color="blue", fontsize=8, va="center")

        self.axs[0].set_title(f"{symbol} ({timeframe}) - as of {df['display_timestamp'].iloc[-1]}")
        self.axs[0].legend()
        self.axs[0].set_ylabel("Price")

    def _plot_rvi(self, df, timeframe):
        self.axs[1].clear()
        self.axs[1].plot(df["display_timestamp"], df["rvi"], color="purple", label="RVI 1h")
        self.axs[1].axhline(y=0, color="black", linestyle="--", linewidth=0.8)
        if not df.empty:
            last_time = df["display_timestamp"].iloc[-1]
            last_rvi = df["rvi"].iloc[-1]
            self.axs[1].annotate(f"{last_rvi:.2f}", 
                                 xy=(last_time, last_rvi), 
                                 xytext=(5, 0), 
                                 textcoords="offset points", 
                                 color="purple", fontsize=8, va="center")
        self.axs[1].set_title(f"RVI 1h - as of {df['display_timestamp'].iloc[-1]}")
        self.axs[1].set_ylabel("RVI 1h")
        self.axs[1].legend()

    def _plot_15m_rvi(self, df_15m):
        self.axs[2].clear()
        if df_15m.empty:
            self.axs[2].text(0.5, 0.5, "No 15m RVI Data Available", ha="center", va="center", fontsize=12, color="red")
            self.draw()
            return
        self.axs[2].plot(df_15m["display_timestamp"], df_15m["rvi"], color="orange", label="RVI 15m")
        self.axs[2].axhline(y=0, color="black", linestyle="--", linewidth=0.8)
        if not df_15m.empty:
            last_time = df_15m["display_timestamp"].iloc[-1]
            last_rvi = df_15m["rvi"].iloc[-1]
            self.axs[2].annotate(f"{last_rvi:.2f}", 
                                 xy=(last_time, last_rvi), 
                                 xytext=(5, 0), 
                                 textcoords="offset points", 
                                 color="orange", fontsize=8, va="center")
        self.axs[2].set_title(f"RVI 15m - as of {df_15m['display_timestamp'].iloc[-1]}")
        self.axs[2].set_ylabel("RVI 15m")
        self.axs[2].legend()
