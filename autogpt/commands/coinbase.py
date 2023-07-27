"""
A module that allows you to interact with the Coinbase API.
"""
import os
from os.path import join
from typing import Union

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
    "wait",
    "Choose to wait and not to take any actions or make any trades for up to 6 hours",
    {
        "hours": {
            "type": "float",
            "description": "The number of hours to wait [0,6]",
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
def wait(hours: float, reason: str, agent: Agent) -> str:
    if hours < 0 or hours > 6:
        return "Invalid number of minutes to wait. Must be in range [0" \
               ", 6]"

    print(f"sleeping for {hours} hours. Reason: '{reason}'.")
    time.sleep(hours * 60 * 60)
    print("Waking up again")

    coinbase.update_state()
    return f"Finished waiting for {hours} hours"


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
        },
        "look_back_days": {
            "type": "int",
            "description": "The number of days to look back [1,12]",
            "required": True,
        }
    },
    _enable_command,
    ENABLE_MSG,
)
def get_price_history(product_id: str, look_back_days: Union[int, str], agent: Agent) -> str:
    if type(look_back_days) != int:
        if not look_back_days.isnumeric():
            return f"Invalid look_back_days ({look_back_days}). Must be an integer"
        look_back_days = int(look_back_days)

    if look_back_days < 1 or look_back_days > 12:
        return f"Invalid number of days to look back ({look_back_days}). Must be in range [1, 12]"

    return f"Price info for for {product_id}: {coinbase.get_candles(product_id, look_back_days=look_back_days)}"


@command(
    "get_ema_for_product",
    "Get the exponential moving average for a product (in 1 hour intervals)",
    {
        "product_id": {
            "type": "string",
            "description": "The product id to get info for",
            "required": True,
        },
        "look_back_days": {
            "type": "int",
            "description": "The number of days to look back [5,50]",
            "required": True,
        },
        "ema_period": {
            "type": "int",
            "description": "The time period of the EMA value (in hours) [20,800]",
            "required": True,
        }
    },
    _enable_command,
    ENABLE_MSG,
)
def get_ema_for_product(product_id: str, look_back_days: Union[int, str], ema_period: Union[int, str], agent: Agent) -> str:
    if type(look_back_days) != int:
        if not look_back_days.isnumeric():
            return f"Invalid look_back_days ({look_back_days}). Must be an integer"
        look_back_days = int(look_back_days)

    if type(ema_period) != int:
        if not ema_period.isnumeric():
            return f"Invalid ema_period ({ema_period}). Must be an integer"
        ema_period = int(ema_period)

    if look_back_days < 5 or look_back_days > 50:
        return f"Invalid number of days to look back ({look_back_days}). Must be in range [5, 50]"

    if ema_period < 20 or ema_period > 800:
        return f"Invalid EMA period ({ema_period}). Must be in range [20, 800]"

    ema = coinbase.get_ema(product_id, look_back_days=look_back_days, ema_period=ema_period)
    return f"{ema_period}EMA over the last {look_back_days} days for {product_id}: {ema}"


# testing
if __name__ == '__main__':
    coinbase.CFG.coinbase_api_key = os.getenv("COINBASE_API_KEY")
    coinbase.CFG.coinbase_api_secret = os.getenv("COINBASE_API_SECRET")

    print(get_product_info('BTC-GBP', None))
    print(get_products(None))
    print(get_ema_for_product('BTC-GBP', 5, 20, None))

    print(get_price_history('BTC-GBP', 5, None))

    # TODO: add some tests finally