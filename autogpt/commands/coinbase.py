"""
A module that allows you to interact with the Coinbase API.
"""
from os.path import join
from typing import Dict, List

from autogpt import coinbase
from autogpt.agents.agent import Agent
from autogpt.command_decorator import command
from regex import regex
from requests import Request
import time

from autogpt.config import Config

BASE_URL = "https://api.coinbase.com/api/v3/brokerage"
ENABLE_MSG = "Enable coinbase in config and disable sandbox"

def _enable_command(config: Config) -> bool:
    return config.coinbase_enabled

@command(
    "get_products",
    "Get a list of the available currency pairs for trading.",
    {},
    _enable_command,
    ENABLE_MSG,
)
def get_products(agent: Agent) -> str:
    request = Request('GET', join(BASE_URL, 'products'))
    resp = coinbase.make_request(request)

    if not resp.ok:
        return f"Error getting available products: {resp.text}"

    products = []
    for details in resp.json()["products"]:

        if details["product_id"].endswith("GBP") or details["product_id"].endswith("BTC"):
            products.append(details["product_id"])

    return f"Available products: {','.join(products)}"


@command(
    "get_product_info",
    "Get cryptocurrency product info including its price",
    {
        "product_id": {
            "type": "string",
            "description": "The product id to get info for",
            "required": True,
        }
    },
    _enable_command,
    ENABLE_MSG,
)
def get_product_info(product_id: str, agent: Agent) -> str:
    if regex.match(r"^[A-Z]{3,4}-[A-Z]{3,4}$", product_id) is None:
        return f"Invalid product id: {product_id}"

    request = Request('GET', join(BASE_URL, 'products', product_id))
    request.data = ''
    resp = coinbase.make_request(request)

    if not resp.ok:
        return f"Error getting product info: {resp.text}"

    wanted_keys = [
        "product_id",
        "price",
        "price_percentage_change_24h",
        "volume_24h",
        "volume_percentage_change_24h",
        "quote_min_size",
        "base_min_size",
        "product_type",
        "mid_market_price"
    ]

    resp_json: dict = resp.json()
    info = dict((k, resp_json[k]) for k in wanted_keys if k in resp_json)

    # reduce precision of some values to save tokens
    info["volume_24h"] = coinbase.to_sig_digits(info["volume_24h"], 4)
    info["price_percentage_change_24h"] = coinbase.to_sig_digits(info["price_percentage_change_24h"], 4)
    info["volume_percentage_change_24h"] = coinbase.to_sig_digits(info["volume_percentage_change_24h"], 4)

    return f"Product information: {info}"


@command(
    "create_buy_order",
    "Buy a cryptocurrency",
    {
        "product_id": {
            "type": "string",
            "description": "The product id to get info for",
            "required": True,
        },
        "quote_size": {
            "type": "string",
            "description": "The amount of quote currency to spend",
            "required": True,
        },
        "reason": {
            "type": "string",
            "description": "The reason for making this trade",
            "required": True,
        },
    },
    _enable_command,
    ENABLE_MSG,
)
def create_buy_order(product_id: str, quote_size: str, reason: str, agent: Agent) -> str:
    return coinbase.create_order("BUY", product_id, quote_size, reason)


@command(
    "create_sell_order",
    "Sell a cryptocurrency",
    {
        "product_id": {
            "type": "string",
            "description": "The product id to get info for",
            "required": True,
        },
        "base_size": {
            "type": "string",
            "description": "The amount of base currency to sell",
            "required": True,
        },
        "reason": {
            "type": "string",
            "description": "The reason for making this trade",
            "required": True,
        },
    },
    _enable_command,
    ENABLE_MSG,
)
def create_sell_order(product_id: str, base_size: str, reason: str, agent: Agent) -> str:
    return coinbase.create_order("SELL", product_id, base_size, reason)


@command(
    "no_action",
    "Choose not to take any actions or make any trades for up to 120 minutes",
    {
        "minutes": {
            "type": "string",
            "description": "The number of minutes to wait",
            "required": True,
        },
        "reason": {
            "type": "string",
            "description": "The reason for waiting",
            "required": True,
        },
    },
    _enable_command,
    ENABLE_MSG,
)
def no_action(minutes: str, reason: str, agent: Agent) -> str:
    if not minutes.isnumeric():
        return "Invalid number of minutes to wait. Must be an integer"

    minutes = int(minutes)
    if minutes < 1 or minutes > 120:
        return "Invalid number of minutes to wait. Must be in range [1, 120]"

    print(f"sleeping for {minutes} minutes. Reason: '{reason}'.")
    time.sleep(minutes * 60)
    print("Waking up again")

    coinbase.update_state()
    return f"Finished waiting for {minutes} minutes"


@command(
    "get_last_10_trades_for_product",
    "Get last 10 trades you have made for a given product",
    {
        "product_id": {
            "type": "string",
            "description": "The product id to get info for",
            "required": True,
        }
    },
    _enable_command,
    ENABLE_MSG,
)
def get_last_10_trades_for_product(product_id: str, agent: Agent) -> str:
    return f"Last 10 trades for this product: {coinbase.get_last_filled_orders(product_id)}"


@command(
    "get_price_history",
    "Get price info for last 3 days for a product",
    {
        "product_id": {
            "type": "string",
            "description": "The product id to get info for",
            "required": True,
        }
    },
    _enable_command,
    ENABLE_MSG,
)
def get_price_history(product_id: str, agent: Agent) -> str:
    return f"Price info for last 3 days for {product_id}: {coinbase.get_candles(product_id)}"


# WIP
def average_price(filled_orders: List[str]) -> Dict[str, float]:
    buy_price_sum = {}  # A dictionary to store the sum of prices for each product.
    buy_count = {}  # A dictionary to store the buy_count of transactions for each product.

    sell_price_sum = {}  # A dictionary to store the sum of prices for each product.
    sell_count = {}  # A dictionary to store the buy_count of transactions for each product.

    for order in filled_orders:
        order_info = order.split()  # Split the order string to extract information.
        side = order_info[1]  # The side is at index 1.
        product_id = order_info[3]  # The product ID is at index 3.
        price = float(order_info[5])  # The price is at index 5.

        if side == "SELL":
            if product_id not in sell_price_sum:
                sell_price_sum[product_id] = 0
                sell_count[product_id] = 0

            sell_price_sum[product_id] += price
            sell_count[product_id] += 1
            continue

        if side == "BUY":
            if product_id not in buy_price_sum:
                buy_price_sum[product_id] = 0
                buy_count[product_id] = 0

            buy_price_sum[product_id] += price
            buy_count[product_id] += 1

    # Calculate the average price for each product.
    # TODO: do buy/sell
    average_prices_buy = {product_id: buy_price_sum[product_id] / buy_count[product_id] for product_id in buy_price_sum}
    average_prices_sell = {product_id: sell_price_sum[product_id] / sell_count[product_id] for product_id in sell_price_sum}

    return average_prices_buy, average_prices_sell


# WIP
def get_trade_price_data() -> None:
    # Get the last 10 filled orders.
    filled_orders = coinbase.get_last_filled_orders(limit=50)

    # Calculate the average prices.
    average_prices = average_price(filled_orders)

    # Print the average prices.
    for product_id, avg_price in average_prices.items():
        print(f"The average price of {product_id} is {avg_price}")


# testing
if __name__ == '__main__':
    print(get_product_info('BTC-GBP'))
    print(get_products())
    # print(create_order('buy', 'BTC-GBP', '0.1'))

    # get_trade_price_data()
    # TODO: add some tests finally