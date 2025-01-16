import unittest
import pandas as pd
from app.indicators import Indicators

class TestIndicators(unittest.TestCase):
    def setUp(self):
        # Sample data
        self.data = pd.DataFrame({
            "open": [1, 2, 3, 4, 5],
            "high": [2, 3, 4, 5, 6],
            "low": [0.5, 1, 2, 3, 4],
            "close": [1.5, 2.5, 3.5, 4.5, 5.5],
        })

    def test_keltner_channel(self):
        result = Indicators.calculate_keltner_channel(self.data, period=2, multiplier=1.5)
        self.assertIn('keltner_upper', result.columns)
        self.assertIn('keltner_lower', result.columns)
        self.assertIn('keltner_mid', result.columns)

    def test_rvi(self):
        result = Indicators.calculate_rvi(self.data, period=2)
        self.assertIn('rvi', result.columns)

if __name__ == "__main__":
    unittest.main()
