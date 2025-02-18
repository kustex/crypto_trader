import json
import os
import pandas as pd
import numpy as np
import optuna
from app.controllers.indicator_generator import Indicators
from app.database import DatabaseManager  
from sqlalchemy import text


class BacktestEngine:
    def __init__(self):
        self.indicators = Indicators()
        self.db_manager = DatabaseManager()
        self.ticker = "BTC/USDT"

    def calculate_indicators(self, df, df_15m, params):
        """Calculate indicators (Keltner Channels & RVI) using provided parameters."""
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
        # RVI on 1h data.
        rvi_df = self.indicators.calculate_rvi(
            df[["open", "high", "low", "close"]],
            period=params["rvi_1h_period"]
        )
        df["rvi_1h"] = rvi_df["rvi"]
        # RVI 15m (if included)
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
        """Generate trading signals based on calculated indicators."""
        if df.empty:
            return None
        if "close_x" in df.columns:
            df.rename(columns={"close_x": "close", "high_x": "high", "low_x": "low",
                               "open_x": "open", "volume_x": "volume"}, inplace=True)
        if "close" not in df.columns:
            raise KeyError(f"❌ 'close' column is missing! Available columns: {df.columns}")
        df["keltner_signal"] = 0
        df.loc[df["close"] > df["keltner_upper"], "keltner_signal"] = -1  # Sell signal.
        df.loc[df["close"] < df["keltner_lower"], "keltner_signal"] = 1   # Buy signal.
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
        """Process raw data: calculate indicators then generate signals."""
        df_ind = self.calculate_indicators(df, df_15m, params)
        if df_ind is None or df_ind.empty:
            return None
        df_signals = self.generate_signals(df_ind, params)
        return df_signals

    def run_backtest(self, df, params):
        """
        Runs a backtest simulation with trade tracking, stoploss execution,
        and partial sell execution (FIFO) with a practical exit rule.
        
        When a buy signal is generated, a new trade is opened.
        If the price drops below the entry price by the stoploss percentage, the entire trade is closed.
        On a sell signal, if the total open position is less than 0.5% of the portfolio,
        the entire position is closed; otherwise, a fraction (partial_sell_fraction) is sold,
        exiting the oldest trades first (FIFO).
        
        Returns a tuple: (df, stats) where df is the input DataFrame with added "equity" and "invested_pct" columns,
        and stats is a dictionary with overall PnL, Sharpe ratio, maximum drawdown, number of trades, and list of trade PnL.
        """
        try:
            initial_equity = 100.0
            equity = initial_equity
            open_trades = []    # Each trade is a dict: {"entry_price": float, "shares": float}
            trade_pnls = []     # Record individual trade PnL.
            equity_curve = []
            invested_pct_curve = []
            max_equity = initial_equity
            drawdowns = []
            
            for i in range(len(df)):
                price = df["close"].iloc[i]
                signal = df["final_signal"].iloc[i]
                
                # Check stoploss for each open trade.
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
                    current_investment = sum(trade["shares"] * price for trade in open_trades)
                    portfolio_value = equity + current_investment
                    max_allowed = params["max_allocation"] * portfolio_value
                    if current_investment < max_allowed:
                        invest_amount = params["position_size"] * equity
                        if current_investment + invest_amount > max_allowed:
                            invest_amount = max_allowed - current_investment
                        if invest_amount > 0:
                            open_trades.append({"entry_price": price, "shares": invest_amount / price})
                            equity -= invest_amount
                
                # Process sell signal.
                elif signal == -1 and open_trades:
                    total_trade_value = sum(trade["shares"] * price for trade in open_trades)
                    portfolio_value = equity + total_trade_value
                    # If total open position is less than 0.5% of portfolio, close all positions.
                    if total_trade_value < 0.01 * portfolio_value:
                        for trade in open_trades:
                            sell_value = trade["shares"] * price
                            pnl_trade = sell_value - (trade["shares"] * trade["entry_price"])
                            trade_pnls.append(pnl_trade)
                            equity += sell_value
                        open_trades = []
                    else:
                        # Otherwise, sell partial position FIFO.
                        target_sell_value = params["partial_sell_fraction"] * total_trade_value
                        remaining_to_sell = target_sell_value
                        while remaining_to_sell > 0 and open_trades:
                            trade = open_trades[0]  # FIFO: sell from oldest trade.
                            trade_value = trade["shares"] * price
                            if trade_value <= remaining_to_sell:
                                sell_value = trade_value
                                pnl_trade = sell_value - (trade["shares"] * trade["entry_price"])
                                trade_pnls.append(pnl_trade)
                                equity += sell_value
                                remaining_to_sell -= trade_value
                                open_trades.pop(0)
                            else:
                                shares_to_sell = remaining_to_sell / price
                                sell_value = shares_to_sell * price
                                pnl_trade = sell_value - (shares_to_sell * trade["entry_price"])
                                trade_pnls.append(pnl_trade)
                                equity += sell_value
                                trade["shares"] -= shares_to_sell
                                remaining_to_sell = 0
                        open_trades = [trade for trade in open_trades if trade["shares"] > 1e-6]
                
                # Compute portfolio value.
                current_investment = sum(trade["shares"] * price for trade in open_trades)
                portfolio_value = equity + current_investment
                equity_curve.append(portfolio_value)
                invested_pct = (current_investment / portfolio_value * 100) if portfolio_value > 0 else 0
                invested_pct_curve.append(invested_pct)
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
            df["equity"] = equity_curve
            df["invested_pct"] = invested_pct_curve
            return df, stats
        except Exception as e:
            print(f"❌ Error in run_backtest: {e}")
            return df, {"PnL": 0, "Sharpe": 0, "MaxDrawdown": 0, "Trades": 0, "TradePnL": []}

