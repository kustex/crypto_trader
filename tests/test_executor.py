from app.executor import TradeExecutor

# Initialize the TradeExecutor for Bitget
executor = TradeExecutor(
    api_key="bg_83ea3f4dd51fd5a983ffe1fadfb309b2",
    api_secret="dd5df6bebc7d464164532e5b4e44fcb0e01a37eded9d95fc9972be8f6d9ff60e",
    api_passphrase="1598756364",
    test_mode=True  # Set to False for live trading
)

# Example: Execute a trade based on a buy signal
symbol = 'SBTCSUSDT'
signal = 1  # Buy
quantity = 0.0015  # Trade size

response = executor.execute_trade(symbol, signal, quantity)
print(response)

# Fetch account balance
balance = executor.fetch_balance()
print(balance)
