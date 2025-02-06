import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

class PlotCanvas(FigureCanvas):
    def __init__(self, db_manager, parent=None, width=10, height=10, dpi=100):
        self.db_manager = db_manager
        self.fig, self.axs = plt.subplots(3, 1, figsize=(width, height), dpi=dpi)  # Three subplots
        super().__init__(self.fig)
        self.setParent(parent)

    def plot_data(self, symbol, timeframe, include_15m_rvi):
        """
        Query data and plot it dynamically based on the symbol, timeframe, and inclusion of 15m RVI.
        """
        # Query the main timeframe data
        main_df = self.db_manager.query_main_timeframe_data(symbol, timeframe)

        if main_df.empty:
            for ax in self.axs:
                ax.clear()
                ax.text(0.5, 0.5, "No Data Available", ha="center", va="center")
            self.draw()
            return

        # Convert timestamp to datetime if not already done
        main_df["timestamp"] = pd.to_datetime(main_df["timestamp"])

        # Filter main timeframe data for plotting range
        max_date = main_df["timestamp"].max()
        lookback_period = pd.Timedelta(days=30) if timeframe == "1h" else pd.Timedelta(days=180)
        min_date = max_date - lookback_period
        main_df = main_df[main_df["timestamp"] >= min_date]

        # Plot the data
        self._plot_main_timeframe(main_df, symbol, timeframe)
        self._plot_rvi(main_df)
        # Query the 15m RVI data if needed

        df_15m = self.db_manager.query_15m_rvi_data(symbol)
        df_15m["timestamp"] = pd.to_datetime(df_15m['timestamp'])
        df_15m = df_15m[df_15m['timestamp'] >= df_15m['timestamp'].max() - lookback_period]
        self._plot_15m_rvi(df_15m) 

        self.fig.tight_layout()
        self.draw()

    def _plot_main_timeframe(self, df, symbol, timeframe):
        self.axs[0].clear()
        self.axs[0].plot(df["timestamp"], df["close"], label="Price", color="blue")
        self.axs[0].plot(df["timestamp"], df["keltner_upper"], label="Keltner Upper", color="green", linestyle="--")
        self.axs[0].plot(df["timestamp"], df["keltner_lower"], label="Keltner Lower", color="red", linestyle="--")

        buy_signals = df[df["final_signal"] == 1]
        sell_signals = df[df["final_signal"] == -1]
        self.axs[0].scatter(buy_signals["timestamp"], buy_signals["close"], color="green", label="Buy Signal", marker="^")
        self.axs[0].scatter(sell_signals["timestamp"], sell_signals["close"], color="red", label="Sell Signal", marker="v")

        self.axs[0].set_title(f"{symbol} ({timeframe}) - Price and Keltner Channels")
        self.axs[0].legend()
        self.axs[0].set_ylabel("Price")

    def _plot_rvi(self, df):
        self.axs[1].clear()
        self.axs[1].plot(df["timestamp"], df["rvi"], label="RVI", color="purple")
        self.axs[1].axhline(y=0, color="black", linestyle="--", linewidth=0.8)
        self.axs[1].set_title("Relative Vigor Index (RVI)")
        self.axs[1].set_ylabel("RVI")
        self.axs[1].legend()

    def _plot_15m_rvi(self, df_15m):
        """Plot the 15-minute Relative Vigor Index (RVI) with data validation."""
        self.axs[2].clear()

        if df_15m.empty:
            self.axs[2].text(0.5, 0.5, "No 15m RVI Data Available", ha="center", va="center", fontsize=12, color="red")
            self.draw()
            return

        self.axs[2].plot(df_15m["timestamp"], df_15m["rvi"], label="15m RVI", color="orange")
        self.axs[2].axhline(y=0, color="black", linestyle="--", linewidth=0.8)
        self.axs[2].set_title("15m RVI")
        self.axs[2].set_ylabel("RVI (15m)")
        self.axs[2].legend()

