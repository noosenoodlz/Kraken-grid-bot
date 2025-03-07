import ccxt  # Crypto exchange connection (Kraken API)
import time  # Sleep intervals for trading frequency
import csv  # Store trade history
import os  # File handling
import requests  # Send Telegram notifications
import json  # Parse API responses if needed
import datetime  # Timestamps for logging
import traceback  # Detailed error handling

# 🔹 Replace with your Kraken API Keys (Ensure correctness)
api_key = "your_kraken_api_key"
api_secret = "your_kraken_api_secret"

# 🔹 Connect to Kraken Exchange
exchange = ccxt.kraken({
    'apiKey': api_key,
    'secret': api_secret,
})

# 🔹 Validate API Key Before Running (Prevents 'EAPI:Invalid key' errors)
try:
    account_balance = exchange.fetch_balance()
    print("✅ API Key is valid! Connected to Kraken successfully.")
except Exception as e:
    print(f"❌ API Key Validation Failed: {e}")
    exit()  # Stops execution if API key is invalid

# 🔹 Trading settings (Dynamic Trade Sizing)
trading_pairs = ["BTC/USD", "ETH/USD", "SOL/USD"]  # Trade multiple pairs
grid_levels = 5  # Number of grid orders
grid_spacing = 10  # USD price gap between orders
take_profit_percentage = 0.05  # 5% profit target
stop_loss_percentage = 0.03  # 3% loss prevention
trailing_stop_percentage = 0.02  # 2% trailing stop
trade_log = "kraken_trade_history.csv"  # CSV file to store trade history

# 🔹 Telegram Bot Credentials (Optional, for Alerts)
TELEGRAM_BOT_TOKEN = "your_telegram_bot_token"
TELEGRAM_CHAT_ID = "your_telegram_chat_id"

# 🔹 Kraken Minimum Trade Sizes (Auto-fetch from API)
minimum_trade_sizes = {}

def fetch_min_trade_sizes():
    global minimum_trade_sizes
    try:
        markets = exchange.load_markets()
        for pair in trading_pairs:
            if pair in markets:
                min_size = markets[pair]['limits']['amount']['min']
                minimum_trade_sizes[pair] = min_size
        print(f"✅ Minimum trade sizes fetched: {minimum_trade_sizes}")
    except Exception as e:
        print(f"⚠ Error fetching minimum trade sizes: {e}")

# 🔹 Telegram Messaging Function (Handles 429 Errors)
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=data)
        if response.status_code == 429:  # Too Many Requests
            retry_after = response.json().get('parameters', {}).get('retry_after', 60)
            print(f"⚠ Telegram rate limit exceeded. Retrying after {retry_after} seconds.")
            time.sleep(retry_after)
            requests.post(url, data=data)
    except Exception as e:
        print(f"⚠ Telegram Message Failed: {e}")

# 🔹 Get Current Price Function
def get_current_price(symbol):
    try:
        ticker = exchange.fetch_ticker(symbol)
        return ticker['last']
    except Exception as e:
        print(f"⚠ Failed to fetch price for {symbol}: {e}")
        return None

# 🔹 Place Buy Order Function
def place_buy_order(symbol):
    buy_price = get_current_price(symbol)
    trade_amount = minimum_trade_sizes.get(symbol, 0.0001) * 1.2  # Add 20% buffer

    if buy_price:
        try:
            order = exchange.create_limit_buy_order(symbol, trade_amount, buy_price)
            print(f"🟢 BOUGHT {trade_amount} {symbol} at ${buy_price}")
            send_telegram_message(f"🟢 BOUGHT {trade_amount} {symbol} at ${buy_price}")
            log_trade("BUY", symbol, buy_price, trade_amount)
            return buy_price
        except Exception as e:
            print(f"⚠ Order failed for {symbol}: {e}")
            send_telegram_message(f"⚠ Order failed for {symbol}: {e}")
    return None

# 🔹 Place Sell Order Function
def place_sell_order(symbol, sell_price):
    trade_amount = minimum_trade_sizes.get(symbol, 0.0001) * 1.2
    try:
        order = exchange.create_limit_sell_order(symbol, trade_amount, sell_price)
        print(f"🔴 SOLD {trade_amount} {symbol} at ${sell_price}")
        send_telegram_message(f"🔴 SOLD {trade_amount} {symbol} at ${sell_price}")
        log_trade("SELL", symbol, sell_price, trade_amount)
    except Exception as e:
        print(f"⚠ Order failed for {symbol}: {e}")
        send_telegram_message(f"⚠ Order failed for {symbol}: {e}")

# 🔹 Trailing Stop Logic
def trailing_sell(symbol, buy_price):
    highest_price = get_current_price(symbol)
    stop_price = highest_price * (1 - trailing_stop_percentage)

    while True:
        current_price = get_current_price(symbol)

        if current_price > highest_price:
            highest_price = current_price
            stop_price = highest_price * (1 - trailing_stop_percentage)

        if current_price <= stop_price:
            place_sell_order(symbol, current_price)
            break

        time.sleep(5)  # Check price every 5 seconds

# 🔹 Check Take Profit & Stop Loss
def check_take_profit_and_stop_loss(symbol, buy_price):
    while True:
        current_price = get_current_price(symbol)
        target_price = buy_price * (1 + take_profit_percentage)
        stop_loss_price = buy_price * (1 - stop_loss_percentage)

        if current_price >= target_price:
            place_sell_order(symbol, current_price)
            print(f"✅ TAKE PROFIT Triggered at ${current_price}")
            send_telegram_message(f"✅ TAKE PROFIT Triggered at ${current_price}")
            break
        elif current_price <= stop_loss_price:
            place_sell_order(symbol, current_price)
            print(f"⛔ STOP-LOSS Triggered at ${current_price}")
            send_telegram_message(f"⛔ STOP-LOSS Triggered at ${current_price}")
            break

        time.sleep(5)  # Check price every 5 seconds

# 🔹 Trade Logging (CSV File)
def log_trade(order_type, symbol, price, amount):
    file_exists = os.path.isfile(trade_log)
    with open(trade_log, mode='a', newline='') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Timestamp", "Order Type", "Symbol", "Price", "Amount"])
        writer.writerow([datetime.datetime.now(), order_type, symbol, price, amount])

# 🔹 Main Execution Loop
def execute_trading_strategy():
    fetch_min_trade_sizes()  # Ensure we get the correct trade sizes
    for symbol in trading_pairs:
        buy_price = place_buy_order(symbol)
        if buy_price:
            check_take_profit_and_stop_loss(symbol, buy_price)
            trailing_sell(symbol, buy_price)

execute_trading_strategy()