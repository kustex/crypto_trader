#!/usr/bin/env python
import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import optuna
from app.controllers.indicator_generator import Indicators
from datetime import timedelta
from sqlalchemy import create_engine, text

# --- Database Manager ---
class DatabaseManager:
    """
    Manages database operations.
    """
    def __init__(self, connection_string):
        self.engine = create_engine(connection_string)

    def get_historical_data(self, ticker, timeframe="1h"):
        query = text(f"""
            SELECT timestamp, open, high, low, close, volume
            FROM historical_data
            WHERE symbol = '{ticker}' AND timeframe = '{timeframe}'
            ORDER BY timestamp ASC
        """)
        with self.engine.connect() as conn:
            result = conn.execute(query)
            df = pd.DataFrame(result.fetchall(), columns=[col.lower().strip() for col in result.keys()])
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df

# --- Backtest Engine ---
class BacktestEngine:
    def __init__(self):
        # Assume that an instance of Indicators is available.
        # The Indicators class should provide methods calculate_keltner_channel and calculate_rvi.
        # For this example, we'll assume those methods are available as static methods.
        self.indicators = Indicators()  

    def calculate_indicators(self, df, df_15m, params):
        if df.empty:
            return None
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp").reset_index(drop=True)
        # Calculate Keltner Channels using the provided parameters.
        keltner_df = self.indicators.calculate_keltner_channel(
            df[["high", "low", "close"]],
            period=params["keltner_period"],
            upper_multiplier=params["keltner_upper_multiplier"],
            lower_multiplier=params["keltner_lower_multiplier"],
        )
        df["keltner_upper"] = keltner_df["keltner_upper"]
        df["keltner_lower"] = keltner_df["keltner_lower"]
        # Calculate RVI on 1h data.
        rvi_df = self.indicators.calculate_rvi(
            df[["open", "high", "low", "close"]],
            period=params["rvi_1h_period"]
        )
        df["rvi_1h"] = rvi_df["rvi"]
        # Optionally merge 15m RVI if enabled.
        if params["include_15m_rvi"] and df_15m is not None:
            df_15m["timestamp"] = pd.to_datetime(df_15m["timestamp"])
            df_15m = df_15m.sort_values("timestamp").reset_index(drop=True)
            rvi_15m_df = self.indicators.calculate_rvi(
                df_15m[["open", "high", "low", "close"]],
                period=params["rvi_15m_period"]
            )
            df_15m["rvi_15m"] = rvi_15m_df["rvi"]
            df = pd.merge_asof(
                df.sort_values("timestamp"),
                df_15m.sort_values("timestamp"),
                on="timestamp",
                direction="backward",
                tolerance=pd.Timedelta("15m")
            )
            df.rename(columns={"close_x": "close", "high_x": "high", "low_x": "low",
                               "open_x": "open", "volume_x": "volume"}, inplace=True)
        return df

    def generate_signals(self, df, params):
        if df is None or df.empty:
            return None
        if "close_x" in df.columns:
            df.rename(columns={"close_x": "close", "high_x": "high", "low_x": "low",
                               "open_x": "open", "volume_x": "volume"}, inplace=True)
        if "close" not in df.columns:
            raise KeyError(f"❌ 'close' column is missing! Available columns: {df.columns}")
        df["keltner_signal"] = 0
        df.loc[df["close"] > df["keltner_upper"], "keltner_signal"] = -1
        df.loc[df["close"] < df["keltner_lower"], "keltner_signal"] = 1
        df["rvi_signal_1h"] = 0
        df.loc[df["rvi_1h"] < params["rvi_1h_lower_threshold"], "rvi_signal_1h"] = 1
        df.loc[df["rvi_1h"] > params["rvi_1h_upper_threshold"], "rvi_signal_1h"] = -1
        df["rvi_signal_15m"] = 0
        if params["include_15m_rvi"] and "rvi_15m" in df.columns:
            df.loc[df["rvi_15m"] < params["rvi_15m_lower_threshold"], "rvi_signal_15m"] = 1
            df.loc[df["rvi_15m"] > params["rvi_15m_upper_threshold"], "rvi_signal_15m"] = -1
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

    def process_data(self, df, df_15m, params):
        """
        Data processing pipeline: given raw OHLCV data (and optionally 15m data) and parameters,
        calculate indicators and then generate signals.
        """
        df_ind = self.calculate_indicators(df, df_15m, params)
        if df_ind is None or df_ind.empty:
            return None
        df_signals = self.generate_signals(df_ind, params)
        return df_signals

    def run_backtest(self, df, params):
        """
        Runs a backtest simulation with trade tracking, stoploss execution,
        partial sell execution (FIFO), and max allocation constraint.
        
        When a buy signal is generated, invest a fixed fraction of available equity,
        but ensure the total invested does not exceed the max allocation (a fraction of total portfolio).
        If the price drops below the entry price by the stoploss percentage, exit the entire trade.
        On a sell signal, sell a fraction (partial_sell_fraction) of the total open position’s value,
        exiting the oldest trades first (FIFO).
        
        Returns a dictionary with overall PnL, Sharpe ratio, maximum drawdown,
        number of trades, and a list of individual trade PnL.
        """
        try:
            initial_equity = 10000.0
            equity = initial_equity
            open_trades = []    # List of dicts, each with "entry_price" and "shares"
            trade_pnls = []     # List to record individual trade PnL
            equity_curve = []
            max_equity = initial_equity
            drawdowns = []
            
            for i in range(len(df)):
                price = df["close"].iloc[i]
                signal = df["final_signal"].iloc[i]
                
                # Check stoploss for each open trade.
                # Exit entire trade if current price falls below entry_price*(1 - stoploss)
                trades_to_close = []
                for idx, trade in enumerate(open_trades):
                    if price < trade["entry_price"] * (1 - params["stoploss"]):
                        trades_to_close.append(idx)
                for idx in sorted(trades_to_close, reverse=True):
                    trade = open_trades.pop(idx)
                    exit_value = trade["shares"] * price
                    pnl_trade = exit_value - (trade["shares"] * trade["entry_price"])
                    trade_pnls.append(pnl_trade)
                    equity += exit_value
                
                # Process buy signal.
                if signal == 1:
                    # Enforce max allocation: total invested must not exceed max_allocation fraction.
                    current_investment = sum(trade["shares"] * price for trade in open_trades)
                    portfolio_value = equity + current_investment
                    max_allowed = params["max_allocation"] * portfolio_value
                    if current_investment < max_allowed:
                        invest_amount = params["position_size"] * equity
                        if current_investment + invest_amount > max_allowed:
                            invest_amount = max_allowed - current_investment
                        if invest_amount > 0:
                            # Open a new trade.
                            new_shares = invest_amount / price
                            open_trades.append({"entry_price": price, "shares": new_shares})
                            equity -= invest_amount
                
                # Process sell signal.
                elif signal == -1 and open_trades:
                    # Determine total invested value and target sell value.
                    total_trade_value = sum(trade["shares"] * price for trade in open_trades)
                    target_sell_value = params["partial_sell_fraction"] * total_trade_value
                    remaining_to_sell = target_sell_value
                    # Sell from trades in FIFO order.
                    while remaining_to_sell > 0 and open_trades:
                        trade = open_trades[0]
                        trade_value = trade["shares"] * price
                        if trade_value <= remaining_to_sell:
                            # Sell entire trade.
                            sell_value = trade_value
                            pnl_trade = sell_value - (trade["shares"] * trade["entry_price"])
                            trade_pnls.append(pnl_trade)
                            equity += sell_value
                            remaining_to_sell -= trade_value
                            open_trades.pop(0)
                        else:
                            # Sell only part of the trade.
                            shares_to_sell = remaining_to_sell / price
                            sell_value = shares_to_sell * price  # equals remaining_to_sell
                            pnl_trade = sell_value - (shares_to_sell * trade["entry_price"])
                            trade_pnls.append(pnl_trade)
                            equity += sell_value
                            trade["shares"] -= shares_to_sell
                            remaining_to_sell = 0
                    # If after partial selling, some trades have nearly zero shares, remove them.
                    open_trades = [trade for trade in open_trades if trade["shares"] > 1e-6]
                
                # Compute portfolio value.
                current_investment = sum(trade["shares"] * price for trade in open_trades)
                portfolio_value = equity + current_investment
                equity_curve.append(portfolio_value)
                if portfolio_value > max_equity:
                    max_equity = portfolio_value
                drawdown = (max_equity - portfolio_value) / max_equity * 100
                drawdowns.append(drawdown)
            
            pnl = equity_curve[-1] - initial_equity
            returns = np.diff(equity_curve) / np.array(equity_curve[:-1])
            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252) if np.std(returns) > 0 else 0.0
            max_drawdown = max(drawdowns) if drawdowns else 0.0
            
            stats = {
                "PnL": pnl,
                "Sharpe": sharpe,
                "MaxDrawdown": max_drawdown,
                "Trades": len(trade_pnls),
                "TradePnL": trade_pnls
            }
            return stats
        except Exception as e:
            print(f"❌ Error in run_backtest: {e}")
            return {"PnL": 0, "Sharpe": 0, "MaxDrawdown": 0, "Trades": 0, "TradePnL": []}


# --- Backtest Optimizer with Walk-Forward Optimization ---
class BacktestOptimizer:
    def __init__(self, ticker, db_manager, engine):
        self.ticker = ticker
        self.db_manager = db_manager
        self.engine = engine  # An instance of BacktestEngine
        self.df = self.db_manager.get_historical_data(ticker, "1h")
        if self.df.empty:
            raise ValueError(f"No historical data returned for ticker {ticker}.")

    def objective(self, trial, df_data):
        """
        Objective function that uses the processing pipeline.
        Returns: PnL - lambda*(MaxDrawdown)
        """
        params = {
            "keltner_upper_multiplier": trial.suggest_float("keltner_upper_multiplier", 1.0, 4.0),
            "keltner_lower_multiplier": trial.suggest_float("keltner_lower_multiplier", 1.0, 4.0),
            "keltner_period": trial.suggest_int("keltner_period", 10, 50),
            "position_size": trial.suggest_float("position_size", 0.01, 0.2),
            "stoploss": trial.suggest_float("stoploss", 0.01, 0.2),
            "max_allocation": trial.suggest_float("max_allocation", 0.1, 0.5),
            "partial_sell_fraction": trial.suggest_float("partial_sell_fraction", 0.1, 0.5),
            "rvi_1h_period": trial.suggest_int("rvi_1h_period", 5, 20),
            "rvi_1h_upper_threshold": trial.suggest_float("rvi_1h_upper_threshold", 0.1, 0.5),
            "rvi_1h_lower_threshold": trial.suggest_float("rvi_1h_lower_threshold", -0.5, -0.1),
            "include_15m_rvi": trial.suggest_categorical("include_15m_rvi", [0, 1]),
            "rvi_15m_period": trial.suggest_int("rvi_15m_period", 5, 20),
            "rvi_15m_upper_threshold": trial.suggest_float("rvi_15m_upper_threshold", 0.1, 0.5),
            "rvi_15m_lower_threshold": trial.suggest_float("rvi_15m_lower_threshold", -0.5, -0.1),
        }
        df_local = df_data.copy()
        df_processed = self.engine.process_data(df_local, None, params)
        if df_processed is None or df_processed.empty:
            return -1e6
        stats = self.engine.run_backtest(df_processed, params)
        lambda_penalty = 0.01  # Adjust penalty weight as desired.
        objective_value = stats["PnL"] - lambda_penalty * stats["MaxDrawdown"]
        print(f"Trial {trial.number}: Params: {params} | PnL: {stats['PnL']:.2f} | Drawdown: {stats['MaxDrawdown']:.2f} | Obj: {objective_value:.2f}")
        return objective_value

    def optimize_parameters_on_data(self, df_train, n_trials=50):
        study = optuna.create_study(direction="maximize")
        study.optimize(lambda trial: self.objective(trial, df_train), n_trials=n_trials)
        return study.best_params

    def walk_forward_optimization(self, train_period_days, test_period_days, n_trials=50, start_date=None, end_date=None):
        """
        Performs walk-forward optimization over the historical data.
        If start_date or end_date are not provided, they are derived from the data.
        Splits the data into rolling training and testing windows.
        Returns a list of results for each window.
        """
        df_full = self.db_manager.get_historical_data(self.ticker, "1h")
        if df_full.empty:
            raise ValueError("No data available for walk-forward optimization.")
        # Determine available date range.
        earliest_date = df_full["timestamp"].min()
        latest_date = df_full["timestamp"].max()
        if start_date is None:
            start_date = earliest_date
        else:
            start_date = pd.to_datetime(start_date)
        if end_date is None:
            end_date = latest_date
        else:
            end_date = pd.to_datetime(end_date)
        # Filter data to desired range.
        df_full = df_full[(df_full["timestamp"] >= start_date) & (df_full["timestamp"] <= end_date)]
        current_start = start_date
        results = []
        while current_start + timedelta(days=train_period_days + test_period_days) <= end_date:
            train_start = current_start
            train_end = current_start + timedelta(days=train_period_days)
            test_end = train_end + timedelta(days=test_period_days)
            df_train = df_full[(df_full["timestamp"] >= train_start) & (df_full["timestamp"] < train_end)]
            df_test = df_full[(df_full["timestamp"] >= train_end) & (df_full["timestamp"] < test_end)]
            if df_train.empty or df_test.empty:
                print(f"Empty training or test window from {train_start} to {test_end}. Skipping.")
                current_start = train_end
                continue
            best_params = self.optimize_parameters_on_data(df_train, n_trials=n_trials)
            df_test_proc = self.engine.process_data(df_test.copy(), None, best_params)
            if df_test_proc is None or df_test_proc.empty:
                print(f"Warning: Processed test window {train_end} to {test_end} is empty. Skipping window.")
                current_start = train_end
                continue
            stats = self.engine.run_backtest(df_test_proc, best_params)
            results.append({
                "train_start": train_start,
                "train_end": train_end,
                "test_end": test_end,
                "best_params": best_params,
                "test_stats": stats
            })
            print(f"Window {train_start.date()} to {test_end.date()}: Sharpe={stats['Sharpe']:.4f}, Drawdown={stats['MaxDrawdown']:.2f}")
            current_start = train_end  # Roll forward by the training period.
        return results

def plot_top_parameters(study, n_top=10):
    """
    Extracts the top n_top trials from an Optuna study and plots
    the distribution of each parameter across these trials.
    """
    # Filter out complete trials and sort them by objective value (highest first)
    completed_trials = [t for t in study.trials if t.state.name == 'COMPLETE']
    if not completed_trials:
        print("No completed trials available.")
        return

    sorted_trials = sorted(completed_trials, key=lambda t: t.value, reverse=True)
    top_trials = sorted_trials[:n_top]
    
    # Get the list of parameter names (assumes all trials share the same keys)
    param_names = list(top_trials[0].params.keys())
    
    n_params = len(param_names)
    n_cols = 3
    n_rows = (n_params + n_cols - 1) // n_cols
    
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(n_cols*4, n_rows*3))
    axes = axes.flatten()
    
    for idx, param in enumerate(param_names):
        # Collect the values for this parameter across the top trials.
        values = [trial.params[param] for trial in top_trials]
        axes[idx].hist(values, bins=10, edgecolor='black')
        axes[idx].set_title(param)
        axes[idx].set_xlabel("Value")
        axes[idx].set_ylabel("Frequency")
    
    # Hide any unused subplots.
    for j in range(idx + 1, len(axes)):
        axes[j].axis("off")
    
    plt.tight_layout()
    plt.show()


# --- Main Script ---
if __name__ == "__main__":
    # Set up your PostgreSQL connection string.
    DB_CONNECTION_STRING = "postgresql+psycopg2://postgres:7aGpc4Uj@127.0.0.1:5432/crypto_data"
    db_manager = DatabaseManager(DB_CONNECTION_STRING)
    
    # Specify the ticker.
    ticker = "BTC/USDT"
    
    # Create instances of the engine and optimizer.
    engine = BacktestEngine()
    optimizer = BacktestOptimizer(ticker, db_manager, engine)
    
    # Walk-forward optimization parameters.
    train_period_days = 60  
    test_period_days = 12   
    n_trials = 50 
    
    results = optimizer.walk_forward_optimization(train_period_days, test_period_days, n_trials=n_trials)
    
    print("\nWalk-Forward Optimization Results:")
    for window in results:
        print(f"Train: {window['train_start'].date()} to {window['train_end'].date()}, Test until: {window['test_end'].date()}")
        print(f"Best Params: {window['best_params']}")
        print(f"Test Stats: {window['test_stats']}")
        print("------")
