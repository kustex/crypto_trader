class TradeExecutor:
    def __init__(self, api_key, api_secret, passphrase, testnet=False):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.testnet = testnet

    def place_order(self, symbol, order_type, side, amount, price=None):
        order_data = {
            "symbol": symbol,
            "order_type": order_type,
            "side": side,
            "amount": amount
        }
        if price:
            order_data["price"] = price
        
        return {"success": True, "message": "Order placed", "data": order_data}
