import json
import os
import pandas as pd
import numpy as np
import optuna
from app.controllers.indicator_generator import Indicators
from app.database import DatabaseManager  
from sqlalchemy import text

# JSON filenames for storing optimal parameters for all tickers.
SIGNAL_PARAMS_FILE = "optimal_signal_params.json"
RISK_PARAMS_FILE = "optimal_risk_params.json"

class BacktestEngine:
    def __init__(self):
        self.indicators = Indicators()
        self.db_manager = DatabaseManager()
        # Default ticker; this should be updated externally (e.g. via the backtest panel)
        self.ticker = "BTC/USDT"

    def save_parameters(self, params):
        """
        Save optimized **signal & risk** parameters to separate JSON files,
        storing each ticker's parameters under its own key.
        """
        # Define keys for signal and risk parameters.
        signal_keys = [
            "keltner_upper_multiplier", "keltner_lower_multiplier", "keltner_period",
            "rvi_15m_period", "rvi_1h_period",
            "rvi_15m_upper_threshold", "rvi_15m_lower_threshold",
            "rvi_1h_upper_threshold", "rvi_1h_lower_threshold",
            "include_15m_rvi"
        ]
        risk_keys = [
            "stoploss", "position_size", "max_allocation", "partial_sell_fraction"
        ]

        # Extract the respective parameter dictionaries.
        signal_params = {key: params[key] for key in signal_keys if key in params}
        risk_params = {key: params[key] for key in risk_keys if key in params}

        # Use the current ticker as key.
        ticker = self.ticker

        # --- Save Signal Parameters ---
        all_signal_params = {}
        if os.path.exists(SIGNAL_PARAMS_FILE):
            try:
                with open(SIGNAL_PARAMS_FILE, "r") as f:
                    all_signal_params = json.load(f)
            except Exception as e:
                print(f"❌ Error reading {SIGNAL_PARAMS_FILE}: {e}")
        all_signal_params[ticker] = signal_params
        try:
            with open(SIGNAL_PARAMS_FILE, "w") as f:
                json.dump(all_signal_params, f, indent=4)
            print(f"✅ Signal parameters for {ticker} saved to {SIGNAL_PARAMS_FILE}")
        except Exception as e:
            print(f"❌ Error saving signal parameters: {e}")

        # --- Save Risk Parameters ---
        all_risk_params = {}
        if os.path.exists(RISK_PARAMS_FILE):
            try:
                with open(RISK_PARAMS_FILE, "r") as f:
                    all_risk_params = json.load(f)
            except Exception as e:
                print(f"❌ Error reading {RISK_PARAMS_FILE}: {e}")
        all_risk_params[ticker] = risk_params
        try:
            with open(RISK_PARAMS_FILE, "w") as f:
                json.dump(all_risk_params, f, indent=4)
            print(f"✅ Risk parameters for {ticker} saved to {RISK_PARAMS_FILE}")
        except Exception as e:
            print(f"❌ Error saving risk parameters: {e}")

    def load_signal_parameters(self):
        """Load optimized signal parameters for the current ticker from the saved JSON file."""
        ticker = self.ticker
        if os.path.exists(SIGNAL_PARAMS_FILE):
            try:
                with open(SIGNAL_PARAMS_FILE, "r") as f:
                    all_signal_params = json.load(f)
                if ticker in all_signal_params:
                    print(f"✅ Loaded signal parameters for {ticker}: {all_signal_params[ticker]}")
                    return all_signal_params[ticker]
                else:
                    print(f"⚠️ No saved signal parameters for ticker {ticker}!")
                    return None
            except Exception as e:
                print(f"❌ Error loading signal parameters: {e}")
                return None
        else:
            print("⚠️ No saved signal parameters found!")
            return None

    def load_risk_parameters(self):
        """Load optimized risk parameters for the current ticker from the saved JSON file."""
        ticker = self.ticker
        if os.path.exists(RISK_PARAMS_FILE):
            try:
                with open(RISK_PARAMS_FILE, "r") as f:
                    all_risk_params = json.load(f)
                if ticker in all_risk_params:
                    print(f"✅ Loaded risk parameters for {ticker}: {all_risk_params[ticker]}")
                    return all_risk_params[ticker]
                else:
                    print(f"⚠️ No saved risk parameters for ticker {ticker}!")
                    return None
            except Exception as e:
                print(f"❌ Error loading risk parameters: {e}")
                return None
        else:
            print("⚠️ No saved risk parameters found!")
            return None

    def calculate_indicators(self, df, df_15m, params):
        """
        Calculate indicators (Keltner Channels & RVI) using provided parameters.
        """
        if df.empty:
            return None

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)

        # Keltner Channels.
        keltner_df = self.indicators.calculate_keltner_channel(
            df[["high", "low", "close"]],
            period=params["keltner_period"],
            upper_multiplier=params["keltner_upper_multiplier"],
            lower_multiplier=params["keltner_lower_multiplier"],
        )
        df["keltner_upper"] = keltner_df["keltner_upper"]
        df["keltner_lower"] = keltner_df["keltner_lower"]

        # RVI 1h.
        rvi_df = self.indicators.calculate_rvi(
            df[["open", "high", "low", "close"]],
            period=params["rvi_1h_period"]
        )
        df["rvi_1h"] = rvi_df["rvi"]

        # RVI 15m (if included).
        if params["include_15m_rvi"] and df_15m is not None:
            df_15m["timestamp"] = pd.to_datetime(df_15m["timestamp"])
            df_15m = df_15m.sort_values("timestamp").reset_index(drop=True)

            rvi_15m_df = self.indicators.calculate_rvi(
                df_15m[["open", "high", "low", "close"]],
                period=params["rvi_15m_period"]
            )
            df_15m["rvi_15m"] = rvi_15m_df["rvi"]

            # Merge 15m RVI with 1h data.
            df = pd.merge_asof(
                df.sort_values("timestamp"),
                df_15m.sort_values("timestamp"),
                on="timestamp",
                direction="backward",
                tolerance=pd.Timedelta("15m")
            )
            # Rename columns to avoid suffixes.
            df.rename(columns={"close_x": "close", "high_x": "high", "low_x": "low",
                               "open_x": "open", "volume_x": "volume"}, inplace=True)

        return df

    def generate_signals(self, df, params):
        """
        Generate trading signals based on calculated indicators.
        """
        if df.empty:
            return None

        # Rename columns if merged.
        if "close_x" in df.columns:
            df.rename(columns={"close_x": "close", "high_x": "high", "low_x": "low",
                               "open_x": "open", "volume_x": "volume"}, inplace=True)

        # Ensure 'close' exists.
        if "close" not in df.columns:
            raise KeyError(f"❌ 'close' column is missing! Available columns: {df.columns}")

        # Generate Keltner Channel signals.
        df["keltner_signal"] = 0
        df.loc[df["close"] > df["keltner_upper"], "keltner_signal"] = -1  # Sell
        df.loc[df["close"] < df["keltner_lower"], "keltner_signal"] = 1   # Buy

        # Generate RVI 1h signals.
        df["rvi_signal_1h"] = 0
        df.loc[df["rvi_1h"] < params["rvi_1h_lower_threshold"], "rvi_signal_1h"] = 1  # Buy
        df.loc[df["rvi_1h"] > params["rvi_1h_upper_threshold"], "rvi_signal_1h"] = -1  # Sell

        # Generate RVI 15m signals if enabled.
        df["rvi_signal_15m"] = 0
        if params["include_15m_rvi"] and "rvi_15m" in df.columns:
            df.loc[df["rvi_15m"] < params["rvi_15m_lower_threshold"], "rvi_signal_15m"] = 1  # Buy
            df.loc[df["rvi_15m"] > params["rvi_15m_upper_threshold"], "rvi_signal_15m"] = -1  # Sell

        # Generate final trading signal.
        if params["include_15m_rvi"]:
            df["final_signal"] = np.where(
                (df["keltner_signal"] == 1) & (df["rvi_signal_1h"] == 1) & (df["rvi_signal_15m"] == 1),
                1,
                np.where(
                    (df["keltner_signal"] == -1) & (df["rvi_signal_1h"] == -1) & (df["rvi_signal_15m"] == -1),
                    -1,
                    0
                )
            )
        else:
            df["final_signal"] = np.where(
                (df["keltner_signal"] == 1) & (df["rvi_signal_1h"] == 1),
                1,
                np.where(
                    (df["keltner_signal"] == -1) & (df["rvi_signal_1h"] == -1),
                    -1,
                    0
                )
            )

        return df

    def run_backtest(self, df, params):
        """
        Simulate a trading strategy using generated signals and risk management parameters.
        Calculates both the equity curve and the invested capital percentage.
        """
        try:
            initial_equity = 10000
            equity = initial_equity
            position = 0
            max_allocation = params["max_allocation"] * equity
            position_size = params["position_size"] * equity
            stoploss_threshold = params["stoploss"]
            partial_sell_fraction = params["partial_sell_fraction"]

            equity_curve = []
            invested_pct_curve = []
            max_equity = initial_equity
            drawdowns = []

            # Process each row (starting from index 1).
            for i in range(1, len(df)):
                price = df["close"].iloc[i]
                signal = df["final_signal"].iloc[i]

                if signal == 1:  # Buy
                    if equity > position_size and (position * price) < max_allocation:
                        position += position_size / price
                        equity -= position_size

                elif signal == -1 and position > 0:  # Sell
                    sell_value = position * price
                    if partial_sell_fraction > 0:
                        equity += sell_value * partial_sell_fraction
                        position -= position * partial_sell_fraction
                    else:
                        equity += sell_value
                        position = 0

                # Apply stop-loss
                if position > 0 and (position * price) < (1 - stoploss_threshold) * position_size:
                    equity += position * price
                    position = 0

                current_total = equity + (position * price)
                invested_pct = (position * price / current_total * 100) if current_total > 0 else 0

                equity_curve.append(current_total)
                invested_pct_curve.append(invested_pct)

                if current_total > max_equity:
                    max_equity = current_total
                drawdowns.append((current_total / max_equity) - 1)

            # Ensure the curves match the DataFrame length.
            if len(equity_curve) < len(df):
                equity_curve.insert(0, initial_equity)
            elif len(equity_curve) > len(df):
                equity_curve = equity_curve[:len(df)]
                
            if len(invested_pct_curve) < len(df):
                invested_pct_curve.insert(0, 0)
            elif len(invested_pct_curve) > len(df):
                invested_pct_curve = invested_pct_curve[:len(df)]
                
            df["equity"] = equity_curve
            df["invested_pct"] = invested_pct_curve

            pnl = df["equity"].iloc[-1] - initial_equity
            returns = df["equity"].pct_change().dropna()
            sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0
            sortino_ratio = np.mean(returns) / np.std(returns[returns < 0]) * np.sqrt(252) if np.std(returns[returns < 0]) > 0 else 0
            max_drawdown = min(drawdowns) * 100
            num_trades = len(df[df["final_signal"] != 0])

            stats = {
                "PnL": pnl,
                "Sharpe Ratio": sharpe_ratio,
                "Sortino Ratio": sortino_ratio,
                "Max Drawdown": max_drawdown,
                "Trades": num_trades,
            }

            return df, stats

        except Exception as e:
            print(f"❌ Error in run_backtest: {e}")
            return df, {"PnL": 0, "Sharpe Ratio": 0, "Sortino Ratio": 0, "Max Drawdown": 0, "Trades": 0}

    def objective(self, trial):
        """
        Objective function for Optuna Bayesian Optimization.
        Maximizes Profit (PnL) while staying within risk constraints.
        """
        params = {
            "keltner_upper_multiplier": trial.suggest_float("keltner_upper_multiplier", 1.0, 4.0),
            "keltner_lower_multiplier": trial.suggest_float("keltner_lower_multiplier", 1.0, 4.0),
            "keltner_period": trial.suggest_int("keltner_period", 10, 50),
            "rvi_15m_period": trial.suggest_int("rvi_15m_period", 5, 20),
            "rvi_1h_period": trial.suggest_int("rvi_1h_period", 5, 20),
            "rvi_15m_upper_threshold": trial.suggest_float("rvi_15m_upper_threshold", 0.1, 0.5),
            "rvi_15m_lower_threshold": trial.suggest_float("rvi_15m_lower_threshold", -0.5, -0.1),
            "rvi_1h_upper_threshold": trial.suggest_float("rvi_1h_upper_threshold", 0.1, 0.5),
            "rvi_1h_lower_threshold": trial.suggest_float("rvi_1h_lower_threshold", -0.5, -0.1),
            "include_15m_rvi": trial.suggest_categorical("include_15m_rvi", [0, 1]),
            "stoploss": trial.suggest_float("stoploss", 0.05, 0.2),
            "position_size": trial.suggest_float("position_size", 0.01, 0.1),
            "max_allocation": trial.suggest_float("max_allocation", 0.1, 0.5),
            "partial_sell_fraction": trial.suggest_float("partial_sell_fraction", 0.1, 0.5),
        }

        # Fetch historical data.
        df = self.get_historical_data("1h")
        df_15m = self.get_historical_data("15m") if params["include_15m_rvi"] else None

        if df is None or df.empty:
            return -1e6  # Penalty for invalid data

        df = self.calculate_indicators(df, df_15m, params)
        df = self.generate_signals(df, params)
        df, stats = self.run_backtest(df, params)

        pnl = stats["PnL"]
        print(f"✅ PnL for this run: {pnl}")
        return pnl

    def optimize_parameters(self, max_evals=1000):
        """
        Uses Optuna Bayesian Optimization to find the best trading parameters.
        """
        print("🚀 Starting Optuna Bayesian Optimization for strategy parameters!")
        study = optuna.create_study(direction="maximize")
        study.optimize(self.objective, n_trials=max_evals)
        best_params = study.best_params
        print("✅ Best Parameters Found:", best_params)
        self.save_parameters(best_params)
        return best_params

    def get_historical_data(self, timeframe="1h"):
        """
        Fetch historical market data for the given timeframe.
        """
        # Use the current ticker (set externally) or default to 'BTC/USDT'
        ticker = getattr(self, "ticker", "BTC/USDT")
        query = text(f"""
            SELECT timestamp, open, high, low, close, volume
            FROM historical_data
            WHERE symbol = '{ticker}' AND timeframe = '{timeframe}'
            ORDER BY timestamp ASC
        """)
        with self.db_manager.engine.connect() as connection:
            result = connection.execute(query)
            df = pd.DataFrame(result.fetchall(), columns=[col.lower().strip() for col in result.keys()])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df
