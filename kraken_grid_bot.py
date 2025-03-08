import ccxt  # Library for interacting with crypto exchanges
import asyncio  # Required for WebSocket asynchronous streaming
import json  # Handles WebSocket messages
import os  # File handling and environment variables
import requests  # Sends Telegram notifications
import datetime  # Handling timestamps for logging
import dotenv  # Loads environment variables from a .env file
import threading  # Multi-threaded execution
import numpy as np  # Numerical operations
import websockets  # Real-time WebSocket streaming for price data

# Load environment variables
dotenv.load_dotenv('/root/.env')

# Retrieve API credentials and Telegram settings
api_key = os.getenv("KRAKEN_API_KEY")
api_secret = os.getenv("KRAKEN_API_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Initialize Kraken Exchange Connection
exchange = ccxt.kraken({
    'apiKey': api_key.strip(),
    'secret': api_secret.strip(),
    'rateLimit': 1000,
    'enableRateLimit': True
})

# Validate API Key Before Running
try:
    account_balance = exchange.fetch_balance()
    print("✅ API Key is valid! Connected to Kraken successfully.")
except Exception as e:
    print(f"❌ API Key Validation Failed: {e}")
    exit()

# **Trading Configuration**
trading_pairs = ["BTC/USD", "ETH/USD", "SOL/USD", "DOGE/USD", "ADA/USD", "XRP/USD"]
base_trade_size = 0.02
take_profit_percentage = 0.03
stop_loss_percentage = 0.02
trailing_stop_percentage = 0.015
cooldown_period = 30  # Cooldown between trades (seconds)

# **WebSocket URL**
KRAKEN_WS_URL = "wss://ws.kraken.com"

# **Real-Time Price Storage**
live_prices = {}

# **Send Telegram Alerts**
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print(f"⚠ Telegram Message Failed: {e}")

# **WebSocket Connection to Kraken**
async def kraken_websocket():
    """
    Connects to Kraken WebSocket API and streams real-time prices.
    Updates the `live_prices` dictionary with the latest market prices.
    """
    async with websockets.connect(KRAKEN_WS_URL) as ws:
        # **Subscribe to price feed for trading pairs**
        subscribe_message = {
            "event": "subscribe",
            "pair": trading_pairs,
            "subscription": {"name": "ticker"}
        }
        await ws.send(json.dumps(subscribe_message))
        print(f"📡 Subscribed to WebSocket price updates for {trading_pairs}")

        while True:
            try:
                response = await ws.recv()
                data = json.loads(response)

                # **Ensure it's a valid price update message**
                if isinstance(data, list) and len(data) > 1:
                    pair = data[-1]
                    price = float(data[1]['c'][0])  # Current price from the update
                    live_prices[pair] = price
                    print(f"📈 Live price update: {pair} - ${price}")

            except Exception as e:
                print(f"⚠ WebSocket Error: {e}")
                break

# **Monitor Live Prices for Buy Signals**
def monitor_market():
    """
    Monitors live prices and executes trades when conditions are met.
    Uses trailing stops, take profit, and stop-loss to maximize gains.
    """
    while True:
        for pair in trading_pairs:
            if pair in live_prices:
                current_price = live_prices[pair]

                # **Trade Logic: Buy When Price Drops Significantly**
                buy_price = current_price * (1 - 0.005)  # Buy 0.5% lower
                sell_price = buy_price * (1 + take_profit_percentage)
                stop_loss_price = buy_price * (1 - stop_loss_percentage)

                # **Check if we should buy**
                print(f"🔍 Checking trade conditions for {pair}: {current_price}")
                if current_price <= buy_price:
                    place_buy_order(pair, buy_price)
                    threading.Thread(target=monitor_trade, args=(pair, buy_price, sell_price, stop_loss_price)).start()

        time.sleep(2)  # Short delay to avoid CPU overload

# **Place a Buy Order**
def place_buy_order(symbol, price):
    """Places a buy order at the given price."""
    try:
        trade_amount = base_trade_size
        order = exchange.create_limit_buy_order(symbol, trade_amount, price)
        print(f"🟢 BOUGHT {trade_amount} {symbol} at ${price}")
        send_telegram_message(f"🟢 BOUGHT {trade_amount} {symbol} at ${price}")
        return price
    except Exception as e:
        print(f"⚠ Buy Order Failed: {e}")

# **Place a Sell Order**
def place_sell_order(symbol, price):
    """Places a sell order at the given price."""
    try:
        trade_amount = base_trade_size
        order = exchange.create_limit_sell_order(symbol, trade_amount, price)
        print(f"🔴 SOLD {trade_amount} {symbol} at ${price}")
        send_telegram_message(f"🔴 SOLD {trade_amount} {symbol} at ${price}")
    except Exception as e:
        print(f"⚠ Sell Order Failed: {e}")

# **Monitor Trade Until Profit or Stop-Loss**
def monitor_trade(symbol, buy_price, sell_price, stop_loss_price):
    """
    Watches trade performance and executes take-profit or stop-loss when needed.
    """
    while True:
        current_price = live_prices.get(symbol, buy_price)

        if current_price >= sell_price:
            place_sell_order(symbol, current_price)
            send_telegram_message(f"✅ TAKE PROFIT {symbol} at ${current_price}")
            break
        elif current_price <= stop_loss_price:
            place_sell_order(symbol, current_price)
            send_telegram_message(f"⛔ STOP-LOSS {symbol} at ${current_price}")
            break

        time.sleep(3)

# **Run WebSocket in Background**
websocket_thread = threading.Thread(target=lambda: asyncio.run(kraken_websocket()))
websocket_thread.start()

# **Start Market Monitoring**
monitor_market()