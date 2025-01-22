BITGET_QSS = """
QWidget {
    background-color: #141A2F;  /* Dark background */
    color: #F5F6FA;  /* Light text */
    font-family: "Arial", sans-serif;
}

QLabel {
    color: #F5F6FA;  /* Light text for labels */
    font-size: 14px;
}

QTableWidget {
    background-color: #1E253A;  /* Slightly lighter dark for tables */
    alternate-background-color: #262D45;
    color: #F5F6FA;  /* Light text for table */
    gridline-color: #2F374F;
    border: 1px solid #2F374F;
}

QTableWidget::item {
    background-color: #1E253A;
    color: #F5F6FA;
    selection-background-color: #2B6AF2;  /* Blue selection */
    selection-color: #F5F6FA;  /* Text color for selected */
}

QPushButton {
    background-color: #2B6AF2;  /* Primary blue */
    color: #F5F6FA;  /* White text */
    border: 1px solid #2B6AF2;
    border-radius: 4px;
    padding: 5px 10px;
}

QPushButton:hover {
    background-color: #3C79F5;  /* Lighter blue on hover */
}

QPushButton:pressed {
    background-color: #1F57D1;  /* Darker blue on press */
}

QLineEdit {
    background-color: #1E253A;
    color: #F5F6FA;
    border: 1px solid #2F374F;
    border-radius: 4px;
    padding: 5px;
}

QComboBox {
    background-color: #1E253A;
    color: #F5F6FA;
    border: 1px solid #2F374F;
    border-radius: 4px;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border-left: 1px solid #2F374F;
}

QHeaderView::section {
    background-color: #262D45;  /* Header background */
    color: #F5F6FA;
    padding: 5px;
    border: 1px solid #2F374F;
}

QScrollBar:vertical {
    background-color: #141A2F;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background-color: #2B6AF2;
    border-radius: 5px;
}

QScrollBar:horizontal {
    background-color: #141A2F;
    height: 10px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background-color: #2B6AF2;
    border-radius: 5px;
}
"""
