"""
A module that allows you to interact with the Coinbase API.
"""
from datetime import datetime, timedelta
from os.path import join
from typing import Dict, List, Any, Union
from urllib.parse import urlparse

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


def update_btc_price_history():
    global btc_price_history
    btc_price_history = get_candles("BTC-GBP")

    logger.debug(f"Updated BTC price history: {btc_price_history}")


def update_eth_price_history():
    global eth_price_history
    eth_price_history = get_candles("ETH-GBP")

    logger.debug(f"Updated ETH price history: {eth_price_history}")


def get_candles(product_id: str, look_back_days: int = 3) -> List[Dict[str, str]]:
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
    resp = make_request(request)

    if not resp.ok:
        raise Exception(f"Error getting candles: {resp.text}")

    candles_raw = resp.json()['candles']
    candles_fmt = []
    for candle in candles_raw:
        candle_fmt = {
            'low': to_sig_digits(candle['low'], 4),
            'high': to_sig_digits(candle['high'], 4),
            'start_time': datetime.fromtimestamp(int(candle['start'])).strftime("%Y-%m-%d %H:%M:%S")
        }
        candles_fmt.append(candle_fmt)

    return candles_fmt


def _update_last_10_trades() -> None:
    global last_10_trades
    last_10_trades = get_last_filled_orders()
    logger.debug(f"last_10_trades updated: {last_10_trades}")


def get_last_filled_orders(product_id: Union[str, None] = None, limit: int = 10) -> List[str]:
    if product_id is not None and regex.match(r"^[A-Z]{3,4}-[A-Z]{3,4}$", product_id) is None:
        raise ValueError(f"Invalid product id: {product_id}")

    params = {"order_status": "FILLED", "limit": limit}
    if product_id is not None:
        params["product_id"] = product_id

    request = Request('GET', url=join(BASE_URL, 'orders/historical/batch'), params=params)
    request.data = ''
    resp = make_request(request)

    if not resp.ok:
        raise Exception(f"Error getting last filled orders: {resp.text}")

    filled_orders = []
    for order in resp.json()["orders"]:
        fmt_time = datetime.strptime(order["created_time"], "%Y-%m-%dT%H:%M:%S.%fZ").strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        fmt_size = to_sig_digits(order["filled_size"], 4)
        fmt_price = to_sig_digits(order["average_filled_price"], 4)
        fmt_entry = f"{fmt_time} {order['side']} {fmt_size} {order['product_id']} @ {fmt_price}"
        filled_orders.append(fmt_entry)

    return filled_orders


def _update_wallet():
    global wallet
    raw_wallet: list = _get_all_wallets()["accounts"]
    wallet = [to_sig_digits(w['available_balance']['value'], 4) + " " + w["available_balance"]["currency"]
              for w in raw_wallet]

    logger.debug(f"Wallet updated: {wallet}")


def to_sig_digits(val: str, n: int) -> str:
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


def make_request(request: Request) -> Response:
    request = _add_headers(request)
    return s.send(request.prepare())


def _get_all_wallets() -> Dict[str, List[Any]]:
    request = Request('GET', join(BASE_URL, 'accounts'))
    request.data = ''
    resp = make_request(request)

    if not resp.ok:
        raise Exception(f"Error getting bitcoin wallet info: {resp.text}")

    return resp.json()


def create_order(side: str, product_id: str, size: str, reason: str) -> str:
    logger.info(f"Reason for {side} order: '{reason}'")

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
    resp = make_request(request)

    if not resp.ok:
        return f"Error creating order: {resp.text}"

    jsn = resp.json()
    if not jsn["success"]:
        return f"Error creating order: {jsn['error_response']}"

    print("Sleeping for 2h after making this trade successfully...")
    time.sleep(2 * 60 * 60)
    print("Waking up again")

    update_state()
    return f"Order creation response: {resp.json()}"


def update_state():
    _update_wallet()
    _update_last_10_trades()


update_state()

# testing
if __name__ == '__main__':
    print(wallet)
    print(last_10_trades)
    print(btc_price_history)

    # get_trade_price_data()
    # TODO: add some tests finally