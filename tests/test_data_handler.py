import unittest
from app.data_handler import DataHandler

class TestDataHandler(unittest.TestCase):
    def test_fetch_historical_data(self):
        handler = DataHandler(exchange_name="binance", symbol="BTC/USDT", timeframe="1h", lookback_days=1)
        data = handler.fetch_historical_data()
        self.assertFalse(data.empty)
        self.assertTrue("timestamp" in data.columns)

if __name__ == "__main__":
    unittest.main()
