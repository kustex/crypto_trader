import unittest
from unittest.mock import MagicMock
from app.portfolio import PortfolioManager
from app.executor import TradeExecutor

class TestPortfolioManager(unittest.TestCase):
    def setUp(self):
        """
        Setup mock TradeExecutor and PortfolioManager for testing.
        """
        # Mock the TradeExecutor
        self.mock_executor = MagicMock(spec=TradeExecutor)

        # Mock balance fetching
        self.mock_executor.fetch_balance.return_value = {
            'total': {
                'USDT': 1000
            }
        }

        # Mock order placement
        self.mock_executor.place_order.return_value = {
            'id': '12345',
            'status': 'open',
            'price': 50000,
        }

        # Initialize PortfolioManager
        self.portfolio_manager = PortfolioManager(trade_executor=self.mock_executor, risk_per_trade=0.01)

    def test_fetch_portfolio_balance(self):
        """
        Test fetching the portfolio balance.
        """
        balance = self.portfolio_manager.fetch_portfolio_balance()
        self.assertEqual(balance, 1000)
        self.mock_executor.fetch_balance.assert_called_once()

    def test_calculate_position_size(self):
        """
        Test position size calculation.
        """
        position_size = self.portfolio_manager.calculate_position_size(stop_loss_pct=0.02)
        self.assertEqual(position_size, 500)  # 1000 * 0.01 / 0.02

    def test_open_position(self):
        """
        Test opening a position.
        """
        symbol = "BTC/USDT"
        stop_loss_pct = 0.02
        side = "buy"
        order = self.portfolio_manager.open_position(symbol, side, stop_loss_pct)

        # Check that the order was placed
        self.assertIn(symbol, self.portfolio_manager.positions)
        self.assertEqual(order['id'], '12345')
        self.mock_executor.place_order.assert_called_once_with(
            symbol, "market", side, 500.0, price=None
        )

    def test_close_position(self):
        """
        Test closing a position.
        """
        symbol = "BTC/USDT"
        self.portfolio_manager.positions[symbol] = {
            "side": "buy",
            "size": 500,
            "entry_price": 50000,
            "stop_loss_pct": 0.02
        }

        # Mock the close order response
        self.mock_executor.place_order.return_value = {
            'id': '54321',
            'status': 'closed',
        }

        order = self.portfolio_manager.close_position(symbol)

        # Check that the position was closed
        self.assertNotIn(symbol, self.portfolio_manager.positions)
        self.assertEqual(order['id'], '54321')
        self.mock_executor.place_order.assert_called_once_with(
            symbol, "market", "sell", 500
        )

    def test_monitor_positions(self):
        """
        Test monitoring open positions.
        """
        symbol = "BTC/USDT"
        self.portfolio_manager.positions[symbol] = {
            "side": "buy",
            "size": 1,
            "entry_price": 50000,
            "stop_loss_pct": 0.02
        }

        # Mock ticker data
        self.mock_executor.exchange.fetch_ticker.return_value = {
            'last': 51000
        }

        # Call monitor_positions
        self.portfolio_manager.monitor_positions()

        # Verify that P&L was calculated (check logs manually if needed)
        self.mock_executor.exchange.fetch_ticker.assert_called_once_with(symbol)

if __name__ == "__main__":
    unittest.main()
