from app.database import DatabaseManager
from app.controllers.signal_generator import SignalGenerator 
from PyQt6.QtCore import QDateTime

class SignalController:
    def __init__(self, db_manager: DatabaseManager, plot_canvas):
        self.db_manager = db_manager
        self.plot_canvas = plot_canvas  

    def regenerate_signals_and_refresh(self, symbol, timeframe):
        """
        Regenerate signals using the updated parameters and refresh the graph.
        """
        if not symbol or not timeframe:
            print("No ticker selected, cannot regenerate signals.")
            return

        try:
            # Step 1: Query historical data
            df = self.db_manager.query_data(symbol, timeframe)
            if df is None or df.empty:
                print(f"No data available for {symbol} ({timeframe}).")
                return None

            params = self.db_manager.fetch_indicator_params(symbol, timeframe)

            keltner_params = {"period": params[0], "multiplier": params[1]}
            rvi_params = {"period": params[2], "thresholds": {"lower": params[3], "upper": params[4]}}
            include_15m_rvi = bool(params[5])

            # Step 3: Calculate and store indicators
            signal_generator = SignalGenerator(db_manager=self.db_manager)
            signal_generator.calculate_and_store_indicators(df, timeframe, keltner_params, rvi_params)  

            # Step 4: Generate signals
            final_signals = signal_generator.generate_final_signals(symbol, timeframe, include_15m_rvi=include_15m_rvi)

            if final_signals is None or final_signals.empty:
                print("Signal generation returned an empty DataFrame.")
                return None

            # Step 5: Save signals to the database
            self.db_manager.save_signals_to_db(final_signals)

            # Step 6: Update the graph
            self.plot_canvas.plot_data(
                symbol=symbol,
                timeframe=timeframe,
                include_15m_rvi=include_15m_rvi
            )
            print(f"Signals regenerated and graph updated for {symbol} ({timeframe}).")

        except Exception as e:
            print(f"Error in signal generation: {e}")

