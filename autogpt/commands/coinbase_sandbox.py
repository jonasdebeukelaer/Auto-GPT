"""
A module that allows you to interact with the Coinbase API.
"""

from autogpt.commands.command import command
from regex import regex

from autogpt.config import Config

CFG = Config()

fake_wallet = {
    "GBP": 100.0,
    "BTC": 0.0,
}


@command(
    "get_wallet_balances",
    "Get available balances in coinbase wallet",
    "",
    CFG.enable_coinbase and CFG.coinbase_is_sandbox,
    "enable coinbase and coinbase sandbox in config",
)
def get_all_wallets() -> str:
    return f"All wallets information: {fake_wallet}"


@command(
    "get_wallet_balance",
    "Get available balance in coinbase wallet for given cryptocurrency",
    '"ticker": "<ticker>"',
    CFG.enable_coinbase and CFG.coinbase_is_sandbox,
    "enable coinbase and coinbase sandbox in config",
)
def get_wallet_for(ticker: str) -> str:
    if regex.match(r"^[A-Z]{3}$", ticker) is None:
        return f"Invalid ticker: {ticker}"

    return f"{ticker} wallet information: {fake_wallet[ticker.upper()]}"


@command(
    "get_product_info",
    "Get cryptocurrency product info including price in GBP",
    '"product_id": "<product_id>"',
    CFG.enable_coinbase and CFG.coinbase_is_sandbox,
    "enable coinbase and coinbase sandbox in config",
)
def get_product_info(product_id: str) -> str:
    if regex.match(r"^[A-Z]{3}-[A-Z]{3}$", product_id) is None:
        return f"Invalid product id: {product_id}"

    return "Product information: {'BTC-GBP': '23000.2'}"


@command(
    "create_order",
    "Create a buy or sell order",
    '"side": "<side>", "product_id": "<product_id>", "quote_size": <quote_size>',
    CFG.enable_coinbase and CFG.coinbase_is_sandbox,
    "enable coinbase and coinbase sandbox in config",
)
def create_order(side: str, product_id: str, quote_size: float) -> str:
    if regex.match(r"^[A-Z]{3}-[A-Z]{3}$", product_id) is None:
        return f"Invalid product id: {product_id}. Should have form 'XXX-GBP'"

    side = side.upper()
    if side not in ["BUY", "SELL"]:
        return f"Invalid side: {side} should be one of [BUY, SELL]"

    if not (type(quote_size) == int or type(quote_size) == float):
        return f"Invalid quote size, should be an int or float: {quote_size}"

    # TEMP SAFETY CHECK
    if quote_size > 20:
        return f"Trade blocked! Quote size too large: £{quote_size}, only orders up to £20 are allowed"

    # don't actually execute the order
    fake_wallet["GBP"] -= quote_size
    fake_wallet["BTC"] += quote_size / 1000

    with open("trades.csv", "a") as f:
        f.write(f"{side},{product_id},{quote_size}\n")

    return f"Order created: {side} {quote_size} {product_id}"


# testing
if __name__ == '__main__':
    print(get_wallet_for('GBP'))
    print(get_product_info('BTC-USD'))
    print(create_order('buy', 'BTC-GBP', 0.001))
