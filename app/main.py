import sys
from PyQt6.QtWidgets import QApplication
from app.ui.main_window import TickerApp  # Import only the UI class

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = TickerApp()
    window.show()
    sys.exit(app.exec())
