from PyQt6.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QGridLayout, QLabel
from app.ui.plot_canvas import PlotCanvas
from app.ui.orders_panel import OrdersPanel
from app.ui.tickers_panel import TickersPanel
from app.ui.risk_parameters import RiskManagementPanel
from app.database import DatabaseManager
from app.controllers.signal_controller import SignalController

class TickerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ticker Viewer")
        self.resize(1400, 800)

        # Initialize database manager
        self.db_manager = DatabaseManager()

        # Initialize UI components
        self.plot_canvas = PlotCanvas(self.db_manager)
        self.signal_controller = SignalController(self.db_manager, self.plot_canvas)
        self.risk_management = RiskManagementPanel(self.db_manager, self.signal_controller)
        self.orders_panel = OrdersPanel(self.db_manager)
        self.tickers_panel = TickersPanel(self.db_manager, self.plot_canvas, self.risk_management, self.orders_panel)

        # Create central widget and layout
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QGridLayout(central_widget)
        main_layout.addLayout(self.tickers_panel.layout, 0, 0)
        main_layout.addLayout(self.risk_management.layout, 1, 0)
        main_layout.addLayout(self.orders_panel.layout, 0, 1)
        main_layout.addWidget(self.plot_canvas, 0, 2, 2, 1)

        # Status Label
        self.status_label = QLabel("System Status: Idle | Last Updated: Not Yet Updated")
        self.status_label.setStyleSheet("font-weight: bold; color: green;")
        main_layout.addWidget(self.status_label, 2, 0, 1, 3)

        # Load tickers on startup
        self.initialize_tickers()

    def initialize_tickers(self):
        """
        Load tickers at application startup and display the first ticker's graph.
        """
        self.tickers_panel.load_tickers()

        # Automatically display the first ticker's graph
        if self.tickers_panel.current_symbol:
            self.tickers_panel.display_graph_with_timeframe("1h")  
