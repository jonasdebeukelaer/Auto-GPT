"""
A module that allows you to interact with the Coinbase API.
"""

from os.path import join
from typing import Dict, List, Any
from urllib.parse import urlparse

from autogpt.commands.command import command
from regex import regex
from requests import Session, Request, Response
import json
import hmac
import hashlib
import time

from autogpt.config import Config
from autogpt.logs import logger

CFG = Config()
BASE_URL = "https://api.coinbase.com/api/v3/brokerage"
ENABLE = CFG.enable_coinbase and not CFG.coinbase_is_sandbox
ENABLE_MSG = "Enable coinbase in config and disable sandbox"

s = Session()
wallet = {}


def _update_wallet():
    global wallet
    raw_wallet: list = _get_all_wallets()["accounts"]
    wallet = {w['name']: w['available_balance']['value'] + " " + w["available_balance"]["currency"] for w in raw_wallet}

    logger.debug(f"Wallet updated: {wallet}")


def _add_headers(request: Request) -> Request:
    timestamp = str(int(time.time()))
    path = str(urlparse(request.url).path).split('?')[0]
    message = timestamp + request.method + path + str(request.data or '')
    signature = hmac.new(CFG.coinbase_api_secret.encode('utf-8'), message.encode('utf-8'), digestmod=hashlib.sha256).digest()

    request.headers['CB-ACCESS-KEY'] = CFG.coinbase_api_key
    request.headers['CB-ACCESS-SIGN'] = signature.hex()
    request.headers['CB-ACCESS-TIMESTAMP'] = timestamp
    request.headers['Content-Type'] = 'application/json'
    return request


def _make_request(request: Request) -> Response:
    request = _add_headers(request)
    return s.send(request.prepare())


def _get_all_wallets() -> Dict[str, List[Any]]:
    request = Request('GET', join(BASE_URL, 'accounts'))
    request.data = ''
    resp = _make_request(request)

    if not resp.ok:
        raise Exception(f"Error getting bitcoin wallet info: {resp.text}")

    return resp.json()


@command(
    "get_products",
    "Get a list of the available currency pairs for trading.",
    "",
    ENABLE,
    ENABLE_MSG,
)
def get_products() -> str:
    request = Request('GET', join(BASE_URL, 'products'))
    resp = _make_request(request)

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
    '"product_id": "<product_id>"',
    ENABLE,
    ENABLE_MSG,
)
def get_product_info(product_id: str) -> str:
    if regex.match(r"^[A-Z]{3,4}-[A-Z]{3,4}$", product_id) is None:
        return f"Invalid product id: {product_id}"

    request = Request('GET', join(BASE_URL, 'products', product_id))
    request.data = ''
    resp = _make_request(request)

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

    def _round_if_number(v: str) -> str:
        if type(v) == str and v.replace(".", "").isnumeric() and "." in v and len(v.split(".")[1]) > 5:
            return f"{float(v):.6f}"
        return v

    info = dict((k, _round_if_number(resp.json()[k])) for k in wanted_keys if k in resp.json())

    return f"Product information: {info}"


# TODO: bring back separate commands for buy and sell
@command(
    "create_buy_order",
    "Buy a cryptocurrency",
    '"product_id": "<product_id>", "quote_size": "<quote_size>"',
    ENABLE,
    ENABLE_MSG,
)
def create_buy_order(product_id: str, quote_size: str) -> str:
    return _create_order("BUY", product_id, quote_size)


@command(
    "create_sell_order",
    "Sell a cryptocurrency",
    '"product_id": "<product_id>", "base_size": "<base_size>"',
    ENABLE,
    ENABLE_MSG,
)
def create_sell_order(product_id: str, base_size: str) -> str:
    return _create_order("SELL", product_id, base_size)


def _create_order(side: str, product_id: str, size: str) -> str:
    if regex.match(r"^[A-Z]{3}-[A-Z]{3}$", product_id) is None:
        return f"Invalid product id: {product_id}. Should have form '<ticker1>-<ticker2>'"

    side = side.upper()
    if side not in ["BUY", "SELL"]:
        return f"Invalid side: {side} should be one of [BUY, SELL]"

    if type(size) != str or not size.replace(".", "").isnumeric():
        return f"Invalid quote size, should be a string representing a float: {size}"

    request = Request('POST', join(BASE_URL, 'orders'))
    request.data = json.dumps({
        "client_order_id": str(int(time.time())),
        "product_id": product_id,
        "side": side,
        "order_configuration": {
            "market_market_ioc": {
                "quote_size": size if side == "BUY" else None,
                "base_size": size if side == "SELL" else None
            }
        }
    })
    resp = _make_request(request)

    if not resp.ok:
        return f"Error creating order: {resp.text}"

    jsn = resp.json()
    if not jsn["success"]:
        return f"Error creating order: {jsn['error_response']}"

    print("Sleeping for 1h after making this trade successfully...")
    time.sleep(60 * 60)
    print("Waking up again")

    _update_wallet()
    return f"Order creation response: {resp.json()}"


@command(
    "no_order",
    "Choose not to make any trades for 10 mins",
    '',
    ENABLE,
    ENABLE_MSG,
    )
def no_order() -> str:
    print("sleeping for 10 minutes...")
    time.sleep(10 * 60)
    print("Waking up again")

    _update_wallet()  # in case any orders were still pending
    return "No order created"


_update_wallet()

# testing
if __name__ == '__main__':
    print(get_product_info('BTC-GBP'))
    print(get_products())
    # print(create_order('buy', 'BTC-GBP', '0.1'))
