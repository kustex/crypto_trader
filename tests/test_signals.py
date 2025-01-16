import unittest
import pandas as pd
from app.signals import SignalGenerator

class TestSignalGenerator(unittest.TestCase):
    def setUp(self):
        # Sample data
        self.data = pd.DataFrame({
            "close": [1, 2, 3, 4, 5],
            "keltner_upper": [2, 3, 4, 5, 6],
            "keltner_lower": [0.5, 1, 2, 3, 4],
            "rvi": [-0.5, 0.1, -0.2, 0.4, 0.9]
        })

    def test_keltner_signals(self):
        result = SignalGenerator.generate_keltner_signals(self.data)
        self.assertIn('keltner_signal', result.columns)

    def test_rvi_signals(self):
        result = SignalGenerator.generate_rvi_signals(self.data)
        self.assertIn('rvi_signal', result.columns)

    def test_combined_signals(self):
        self.data['keltner_signal'] = [1, 0, -1, 1, -1]
        self.data['rvi_signal'] = [1, -1, 0, 1, -1]
        result = SignalGenerator.combine_signals(self.data)
        self.assertIn('final_signal', result.columns)

if __name__ == "__main__":
    unittest.main()
