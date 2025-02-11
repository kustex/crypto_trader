from PyQt6.QtCore import QThread, pyqtSignal
import time

class OrderStatusChecker(QThread):
    """
    Background thread to monitor the status of an order until it is filled.
    """
    order_filled = pyqtSignal()  # Emit when order is successfully filled

    def __init__(self, trade_executor, order_id, symbol):
        super().__init__()
        self.trade_executor = trade_executor
        self.order_id = order_id
        self.symbol = symbol

    def run(self):
        """
        Periodically check if the order is filled.
        """
        max_attempts = 20  
        attempts = 0

        while attempts < max_attempts:
            status = self.trade_executor.check_order_status(self.order_id, self.symbol)

            if status == "closed":  # Order filled
                print(f"✅ Order {self.order_id} for {self.symbol} is filled.")
                self.order_filled.emit()  # Notify the UI to update portfolio
                return
            elif status == "canceled":
                print(f"❌ Order {self.order_id} was canceled.")
                return
            elif status == "error":
                print(f"⚠️ Error checking order {self.order_id}. Stopping monitoring.")
                return

            attempts += 1
            time.sleep(5)  # Wait 5 seconds before checking again

        print(f"⚠️ Order {self.order_id} is still open after {max_attempts * 5} seconds.")
