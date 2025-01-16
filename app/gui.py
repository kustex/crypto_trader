import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QPushButton, QLabel, QTableWidget, QTableWidgetItem

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Crypto Trading App")

        # Layout
        layout = QVBoxLayout()

        # Components
        self.status_label = QLabel("Status: Stopped")
        self.start_button = QPushButton("Start Trading")
        self.stop_button = QPushButton("Stop Trading")
        self.trades_table = QTableWidget(0, 4)
        self.trades_table.setHorizontalHeaderLabels(["Time", "Action", "Amount", "Price"])

        # Actions
        self.start_button.clicked.connect(self.start_trading)
        self.stop_button.clicked.connect(self.stop_trading)

        # Add Components
        layout.addWidget(self.status_label)
        layout.addWidget(self.start_button)
        layout.addWidget(self.stop_button)
        layout.addWidget(self.trades_table)

        # Central Widget
        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

    def start_trading(self):
        self.status_label.setText("Status: Running")

    def stop_trading(self):
        self.status_label.setText("Status: Stopped")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
