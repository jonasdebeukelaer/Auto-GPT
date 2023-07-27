"""
A module that allows you to interact with the Coinbase API.
"""
import os
from datetime import datetime, timedelta
from os.path import join
from typing import Dict, List, Any, Union
from urllib.parse import urlparse

import numpy as np
from regex import regex
from requests import Session, Request, Response
import json
import hmac
import hashlib
import time
import talib

from autogpt.config import Config
from autogpt.logs import logger

CFG = Config() # init with empty config
BASE_URL = "https://api.coinbase.com/api/v3/brokerage"
ENABLE = False
ENABLE_MSG = "Enable coinbase in config and disable sandbox"

def init_config(config: Config) -> None:
    global CFG, ENABLE
    CFG = config
    ENABLE = CFG.coinbase_api_key is not None and CFG.coinbase_api_secret is not None

s = Session()
wallet = []
trades = []


def update_btc_price_history():
    global btc_price_history
    btc_price_history = get_candles("BTC-GBP")

    logger.debug(f"Updated BTC price history: {btc_price_history}")


def update_eth_price_history():
    global eth_price_history
    eth_price_history = get_candles("ETH-GBP")

    logger.debug(f"Updated ETH price history: {eth_price_history}")


def get_candles(
        product_id: str,
        look_back_days: int = 3,
        days_offset: int = 0,
        granularity: int = 6,
        keep_stats: list[str] = ["low", "high"]
) -> List[Dict[str, str]]:
    if not _is_valid_product_id_format(product_id):
        raise ValueError(f"Invalid product id: {product_id}")

    granularity_map = {
        1: "ONE_HOUR",
        2: "TWO_HOUR",
        6: "SIX_HOUR",
        24: "ONE_DAY"
    }

    now = datetime.utcnow()

    params = {
        "granularity": granularity_map[granularity],
        "start": int((now - timedelta(days=look_back_days)).timestamp()),
        "end": int(now.timestamp() - timedelta(days=days_offset).total_seconds()),
    }

    request = Request("GET", url=join(BASE_URL, "products", product_id, "candles"), params=params)
    request.data = ""
    resp = make_request(request)

    if not resp.ok:
        raise Exception(f"Error getting candles: {resp.text}")

    candles_raw = resp.json()['candles']
    candles_fmt = []
    for candle in candles_raw:
        candle_fmt = {'start_time': datetime.fromtimestamp(int(candle['start'])).strftime("%Y-%m-%d %H:%M:%S")}

        for stat in keep_stats:
            candle_fmt[stat] = to_sig_digits(candle[stat], 4)

        candles_fmt.append(candle_fmt)

    return candles_fmt


def _update_last_10_trades() -> None:
    global trades
    trades = get_last_filled_orders()
    logger.debug(f"last_10_trades updated: {trades}")


def get_last_filled_orders(product_id: Union[str, None] = None, limit: int = 10) -> List[str]:
    if product_id is not None and not _is_valid_product_id_format(product_id):
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


def get_ema(product_id: str = "BTC-GBP", look_back_days: int = 10, ema_period: int = 50) -> List[float]:
    btc_prices = []

    max = look_back_days // 5
    for i in range(max):
        btc_price_hist = get_candles(product_id, look_back_days=10, days_offset=i, granularity=1, keep_stats=["close"])
        btc_prices = btc_prices + [float(candle['close']) for candle in btc_price_hist]

    ta_ema = talib.EMA(np.array(btc_prices), timeperiod=ema_period)
    return to_sig_digits(ta_ema.tolist(), 5)


def _update_wallet():
    global wallet
    raw_wallet: list = _get_all_wallets()["accounts"]
    wallet = [to_sig_digits(w['available_balance']['value'], 4) + " " + w["available_balance"]["currency"]
              for w in raw_wallet]

    logger.debug(f"Wallet updated: {wallet}")


def to_sig_digits(val: Union[str, float, List[float]], n: int) -> Union[str, float, List[float]]:
    if type(val) == list:
        return [to_sig_digits(v, n) for v in val]
    elif type(val) == str:
        if type(val) == str and val.replace(".", "").replace("-", "").isnumeric():
            num = float(val)
            return '{:g}'.format(float('{:.{p}g}'.format(num, p=n)))
    else:
        return float('{:.{p}g}'.format(val, p=n))


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


def _is_valid_product_id_format(product_id: str) -> bool:
    return regex.match(r"^[A-Z]{3,4}-[A-Z]{3,4}$", product_id) is not None


# TODO: move to coinbase file
def create_order(side: str, product_id: str, size: str, reason: str) -> str:
    if not _is_valid_product_id_format:
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

        # TODO: handle INVALID_SIZE_PRECISION error
        if resp.json()["error"] == "INVALID_SIZE_PRECISION" and resp.json()["message"] == "Too many decimals in order amount":
            current_precision = int(size.split(".")[1])
            return create_order(side, product_id, to_sig_digits(size, current_precision-1), reason)

        return f"Error creating order: {resp.text}"

    jsn = resp.json()
    if not jsn["success"]:
        return f"Error creating order: {jsn['error_response']}"

    print("Sleeping for 1h after making this trade successfully...")
    time.sleep(1 * 60 * 60)
    print("Waking up again")

    update_state()
    return f"Order creation response: {resp.json()}"


def update_state():
    _update_wallet()
    _update_last_10_trades()


# testing
if __name__ == '__main__':
    # CFG.coinbase_api_key = os.getenv("COINBASE_API_KEY")
    # CFG.coinbase_api_secret = os.getenv("COINBASE_API_SECRET")

    print(wallet)
    print(trades)

    print(get_ema())
    print(get_ema(look_back_days=2))

    # TODO: add some tests finally