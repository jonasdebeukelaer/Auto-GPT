"""
A module that allows you to interact with the Coinbase API.
"""

from os.path import join
from urllib.parse import urlparse

from autogpt.commands.command import command
from regex import regex
from requests import Session, Request, Response
import json
import hmac
import hashlib
import time

from autogpt.config import Config

CFG = Config()

BASE_URL = "https://api.coinbase.com/api/v3/brokerage"

s = Session()


def add_headers(request: Request) -> Request:
    timestamp = str(int(time.time()))
    path = str(urlparse(request.url).path).split('?')[0]
    message = timestamp + request.method + path + str(request.data or '')
    signature = hmac.new(CFG.coinbase_api_secret.encode('utf-8'), message.encode('utf-8'), digestmod=hashlib.sha256).digest()

    request.headers['CB-ACCESS-KEY'] = CFG.coinbase_api_key
    request.headers['CB-ACCESS-SIGN'] = signature.hex()
    request.headers['CB-ACCESS-TIMESTAMP'] = timestamp
    request.headers['Content-Type'] = 'application/json'
    return request


def make_request(request: Request) -> Response:
    request = add_headers(request)
    return s.send(request.prepare())


@command(
    "get_wallet_balances",
    "Get available balances in coinbase wallet",
    "",
    CFG.enable_coinbase and not CFG.coinbase_is_sandbox,
    "enable coinbase in config and disable sandbox",
)
def get_all_wallets() -> str:
    request = Request('GET', join(BASE_URL, 'accounts'))
    request.data = ''
    resp = make_request(request)

    if not resp.ok:
        return f"Error getting wallets: {resp.text}"

    return f"Wallets information: {resp.json()}"


@command(
    "get_wallet_balance",
    "Get available balance in coinbase wallet for given cryptocurrency",
    '"ticker": "<ticker>"',
    CFG.enable_coinbase and not CFG.coinbase_is_sandbox,
    "enable coinbase in config and disable sandbox",
)
def get_wallet_for(ticker: str) -> str:
    if regex.match(r"^[A-Z]{3}$", ticker) is None:
        return f"Invalid ticker: {ticker}"

    request = Request('GET', join(BASE_URL, 'accounts'))
    request.data = ''
    resp = make_request(request)

    if not resp.ok:
        return f"Error getting bitcoin wallet info: {resp.text}"

    info = ""
    for account in resp.json()["accounts"]:
        if account["currency"] == ticker:
            info = account
            break

    return f"{ticker} wallet information: {info}"


@command(
    "get_product_info",
    "Get cryptocurrency product info including price in GBP",
    '"product_id": "<product_id>"',
    CFG.enable_coinbase and not CFG.coinbase_is_sandbox,
    "enable coinbase in config and disable sandbox",
)
def get_product_info(product_id: str) -> str:
    if regex.match(r"^[A-Z]{3}-[A-Z]{3}$", product_id) is None:
        return f"Invalid product id: {product_id}"

    request = Request('GET', join(BASE_URL, 'products', product_id))
    request.data = ''
    resp = make_request(request)

    if not resp.ok:
        return f"Error getting product info: {resp.text}"

    return f"Product information: {resp.json()}"


@command(
    "create_order",
    "Create a buy or sell order",
    '"side": "<side>", "product_id": "<product_id>", "quote_size": "<quote_size>"',
    CFG.enable_coinbase and not CFG.coinbase_is_sandbox,
    "enable coinbase in config and disable sandbox",
)
def create_order(side: str, product_id: str, quote_size: str) -> str:
    if regex.match(r"^[A-Z]{3}-[A-Z]{3}$", product_id) is None:
        return f"Invalid product id: {product_id}. Should have form 'XXX-GBP'"

    side = side.upper()
    if side not in ["BUY", "SELL"]:
        return f"Invalid side: {side} should be one of [BUY, SELL]"

    if type(quote_size) != str or not quote_size.replace(".", "").isnumeric():
        return f"Invalid quote size, should be a string representing a float: {quote_size}"
    quote_size = float(quote_size)

    # TEMP SAFETY CHECK
    if quote_size > 20:
        return f"Trade blocked! Quote size too large: £{quote_size}, only orders up to £20 are allowed"

    request = Request('POST', join(BASE_URL, 'orders'))
    request.data = json.dumps({
        "client_order_id": str(int(time.time())),
        "product_id": product_id,
        "side": side,
        "order_configuration": {
            "market_market_ioc": {
                "quote_size": str(quote_size),
            }
        }
    })
    resp = make_request(request)

    if not resp.ok:
        return f"Error creating order: {resp.text}"

    print("Sleeping for 1h after making this trade successfully...")
    time.sleep(60 * 60)
    print("Waking up again")

    return f"Order created: {resp.json()}"


# testing
if __name__ == '__main__':
    print(get_wallet_for('GBP'))
    print(get_product_info('BTC-USD'))
    print(create_order('buy', 'BTC-GBP', '1.0'))
