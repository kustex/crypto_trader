from PyQt6.QtCore import QThread, pyqtSignal
from app.database import DatabaseManager
from app.controllers.signal_generator import SignalGenerator
import traceback

class SignalWorker(QThread):
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, db_manager: DatabaseManager, symbol: str, timeframe: str, parent=None):
        super().__init__(parent)
        self.db_manager = db_manager
        self.symbol = symbol
        self.timeframe = timeframe

    def run(self):
        """Run signal generation in a background thread."""
        try:
            df = self.db_manager.query_data(self.symbol, self.timeframe)
            if df is None or df.empty:
                self.error.emit(f"No data available for {self.symbol} ({self.timeframe}).")
                return

            params = self.db_manager.fetch_indicator_params(self.symbol, self.timeframe)
            if not params or len(params) < 10:
                self.error.emit(f"Invalid parameters for {self.symbol} ({self.timeframe}): {params}")
                return

            (
                keltner_upper_multiplier, keltner_lower_multiplier, keltner_period,
                rvi_15m_period, rvi_1h_period,
                rvi_15m_upper_threshold, rvi_15m_lower_threshold,
                rvi_1h_upper_threshold, rvi_1h_lower_threshold,
                include_15m_rvi_db
            ) = params

            # Here, if you want to honor the db setting, you could override include_15m_rvi:
            include_15m = bool(include_15m_rvi_db)

            keltner_params = {
                "period": keltner_period,
                "upper_multiplier": keltner_upper_multiplier,
                "lower_multiplier": keltner_lower_multiplier,
            }

            rvi_params = {
                "period": rvi_1h_period if self.timeframe == "1h" else rvi_15m_period,
                "upper_threshold": rvi_1h_upper_threshold if self.timeframe == "1h" else rvi_15m_upper_threshold,
                "lower_threshold": rvi_1h_lower_threshold if self.timeframe == "1h" else rvi_15m_lower_threshold,
            }

            signal_generator = SignalGenerator(db_manager=self.db_manager)
            signal_generator.calculate_and_store_indicators(self.symbol, self.timeframe, keltner_params, rvi_params)

            final_signals = signal_generator.generate_final_signals(self.symbol, self.timeframe, include_15m_rvi=include_15m)
            if final_signals is None or final_signals.empty:
                self.error.emit(f"Signal generation returned an empty DataFrame for {self.symbol} ({self.timeframe}).")
                return

            self.db_manager.save_signals_to_db(final_signals)

            # Remove UI updates from here. Instead, we simply emit finished.
            print(f"✅ Signals regenerated for {self.symbol} ({self.timeframe}).")
            self.finished.emit()

        except Exception as e:
            error_msg = f"❌ Error in signal generation for {self.symbol} ({self.timeframe}): {str(e)}\n{traceback.format_exc()}"
            self.error.emit(error_msg)

class SignalController:
    def __init__(self, db_manager: DatabaseManager, plot_canvas):
        self.db_manager = db_manager
        self.plot_canvas = plot_canvas
        self.workers = {}  # track workers per (symbol, timeframe)

    def regenerate_signals_and_refresh(self, symbol, timeframe):
        """Regenerate signals asynchronously while allowing multiple tickers and timeframes."""
        if not symbol or not timeframe:
            print("No ticker selected, cannot regenerate signals.")
            return

        # Avoid starting a new worker if one is already running for the same (symbol, timeframe)
        if (symbol, timeframe) in self.workers and self.workers[(symbol, timeframe)].isRunning():
            print(f"⚠️ Signal generation is already running for {symbol} ({timeframe}).")
            return  

        # Create the worker with the include_15m_rvi flag (here, for example, set to True)
        worker = SignalWorker(self.db_manager, symbol, timeframe)
        worker.finished.connect(lambda: self.on_signal_generation_complete(symbol, timeframe))
        worker.error.connect(lambda msg: self.on_signal_generation_error(symbol, timeframe, msg))

        self.workers[(symbol, timeframe)] = worker
        worker.start()

    def on_signal_generation_complete(self, symbol, timeframe):
        """Callback when signal generation is complete. Update the UI on the main thread."""
        print(f"✅ Signal generation finished successfully for {symbol} ({timeframe}).")
        # Now that the signals have been updated in the database, update the graph in the main thread.
        self.plot_canvas.plot_data(symbol, timeframe)
        if (symbol, timeframe) in self.workers:
            del self.workers[(symbol, timeframe)]

    def on_signal_generation_error(self, symbol, timeframe, message):
        """Callback when an error occurs in the worker thread."""
        print(f"❌ Signal generation error for {symbol} ({timeframe}): {message}")
        if (symbol, timeframe) in self.workers:
            del self.workers[(symbol, timeframe)]
