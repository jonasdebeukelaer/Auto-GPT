"""
A module that allows you to interact with the Coinbase API.
"""
from datetime import datetime, timedelta
from os.path import join
from typing import Dict, List, Any, Union
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
wallet = []
last_10_trades = []
btc_price_history = []  # TODO: include this in context?
eth_price_history = []  # TODO: include this in context?


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

    resp_json: dict = resp.json()
    info = dict((k, resp_json[k]) for k in wanted_keys if k in resp_json)

    # reduce precision of some values to save tokens
    info["volume_24h"] = _to_sig_digits(info["volume_24h"], 4)
    info["price_percentage_change_24h"] = _to_sig_digits(info["price_percentage_change_24h"], 4)
    info["volume_percentage_change_24h"] = _to_sig_digits(info["volume_percentage_change_24h"], 4)

    return f"Product information: {info}"


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


@command(
    "no_action",
    "Choose not to take any actions or make any trades for up to 120 minutes",
    '"minutes": "<minutes>"',
    ENABLE,
    ENABLE_MSG,
)
def no_action(minutes: int) -> str:
    if minutes < 1 or minutes > 120:
        return "Invalid number of minutes to wait. Must be in range [1, 120]"

    print(f"sleeping for {minutes} minutes...")
    time.sleep(minutes * 60)
    print("Waking up again")

    _update_state()
    return f"Finished waiting for {minutes} minutes"


@command(
    "get_last_10_trades_for_product",
    "Get last 10 trades you have made for a given product",
    '"product_id": "<product_id>"',
    ENABLE,
    ENABLE_MSG,
)
def get_last_10_trades_for_product(product_id: str) -> str:
    return f"Last 10 trades for this product: {_get_last_filled_orders(product_id)}"


@command(
    "get_price_history",
    "Get price info for last 3 days for a product",
    '"product_id": "<product_id>"',
    ENABLE,
    ENABLE_MSG,
)
def get_price_history(product_id: str) -> str:
    return f"Price info for last 3 days for {product_id}: {_get_candles(product_id)}"


def _update_btc_price_history():
    global btc_price_history
    btc_price_history = _get_candles("BTC-GBP")

    logger.debug(f"Updated BTC price history: {btc_price_history}")


def _update_eth_price_history():
    global eth_price_history
    eth_price_history = _get_candles("ETH-GBP")

    logger.debug(f"Updated ETH price history: {eth_price_history}")


def _get_candles(product_id: str, look_back_days: int = 3) -> List[Dict[str, str]]:
    if regex.match(r"^[A-Z]{3,4}-[A-Z]{3,4}$", product_id) is None:
        raise ValueError(f"Invalid product id: {product_id}")

    now = datetime.utcnow()

    params = {
        "granularity": "SIX_HOUR",
        "start": int((now - timedelta(days=look_back_days)).timestamp()),
        "end": int(now.timestamp()),
    }

    request = Request("GET", url=join(BASE_URL, "products", product_id, "candles"), params=params)
    request.data = ""
    resp = _make_request(request)

    if not resp.ok:
        raise Exception(f"Error getting candles: {resp.text}")

    candles_raw = resp.json()['candles']
    candles_fmt = []
    for candle in candles_raw:
        candle_fmt = {
            'low': _to_sig_digits(candle['low'], 4),
            'high': _to_sig_digits(candle['high'], 4),
            'start_time': datetime.fromtimestamp(int(candle['start'])).strftime("%Y-%m-%d %H:%M:%S")
        }
        candles_fmt.append(candle_fmt)

    return candles_fmt


def _update_last_10_trades() -> None:
    global last_10_trades
    last_10_trades = _get_last_filled_orders()
    logger.debug(f"last_10_trades updated: {last_10_trades}")


def _get_last_filled_orders(product_id: Union[str, None] = None, limit: int = 10) -> List[str]:
    if product_id is not None and regex.match(r"^[A-Z]{3,4}-[A-Z]{3,4}$", product_id) is None:
        raise ValueError(f"Invalid product id: {product_id}")

    params = {"order_status": "FILLED", "limit": limit}
    if product_id is not None:
        params["product_id"] = product_id

    request = Request('GET', url=join(BASE_URL, 'orders/historical/batch'), params=params)
    request.data = ''
    resp = _make_request(request)

    if not resp.ok:
        raise Exception(f"Error getting last filled orders: {resp.text}")

    filled_orders = []
    for order in resp.json()["orders"]:
        fmt_time = datetime.strptime(order["created_time"], "%Y-%m-%dT%H:%M:%S.%fZ").strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        fmt_size = _to_sig_digits(order["filled_size"], 4)
        fmt_price = _to_sig_digits(order["average_filled_price"], 4)
        fmt_entry = f"{fmt_time} {order['side']} {fmt_size} {order['product_id']} @ {fmt_price}"
        filled_orders.append(fmt_entry)

    return filled_orders


def _update_wallet():
    global wallet
    raw_wallet: list = _get_all_wallets()["accounts"]
    wallet = [_to_sig_digits(w['available_balance']['value'], 4) + " " + w["available_balance"]["currency"]
              for w in raw_wallet]

    logger.debug(f"Wallet updated: {wallet}")


def _to_sig_digits(val: str, n: int) -> str:
    if type(val) == str and val.replace(".", "").replace("-", "").isnumeric():
        num = float(val)
        return '{:g}'.format(float('{:.{p}g}'.format(num, p=n)))
    return val


def _add_headers(request: Request) -> Request:
    timestamp = str(int(time.time()))
    path = str(urlparse(request.url).path).split('?')[0]
    message = timestamp + request.method + path + str(request.data or '')
    signature = hmac.new(CFG.coinbase_api_secret.encode('utf-8'), message.encode('utf-8'),
                         digestmod=hashlib.sha256).digest()

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

    print("Sleeping for 2h after making this trade successfully...")
    time.sleep(2 * 60 * 60)
    print("Waking up again")

    _update_state()
    return f"Order creation response: {resp.json()}"


def _update_state():
    _update_wallet()
    _update_last_10_trades()
    _update_btc_price_history()
    _update_eth_price_history()


_update_state()


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
    filled_orders = _get_last_filled_orders(limit=50)

    # Calculate the average prices.
    average_prices = average_price(filled_orders)

    # Print the average prices.
    for product_id, avg_price in average_prices.items():
        print(f"The average price of {product_id} is {avg_price}")


# testing
if __name__ == '__main__':
    # print(get_product_info('BTC-GBP'))
    # print(get_products())
    # print(create_order('buy', 'BTC-GBP', '0.1'))
    print(wallet)
    print(last_10_trades)
    print(btc_price_history)

    # get_trade_price_data()
