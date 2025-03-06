import ccxt
import time
import csv
import os
import datetime
import requests

# 🔹 Replace with your Kraken API Keys (Copy & Paste Exactly as Shown in Kraken)
api_key = "Zzmf8P6h8jzPa1Cu9q7xCFLebFML/QvNul/c1n4ujtil+QEJxHHamW/W"
api_secret = "tn3ft57r/SR1IfQA6xsDnjA5HKfPH73dTqvXqBHWPoQtYrv87oaoS4Z7zsmmnw1St4JQYHfFi2nCcvr2l1R6Wg=="

# 🔹 Connect to Kraken Exchange
exchange = ccxt.kraken({
    'apiKey': api_key,
    'secret': api_secret,
})

# 🔹 Trading settings
symbol = "BTC/USD"  # Trading pair
grid_levels = 5  # Number of grid orders
grid_spacing = 10  # USD price gap between orders
trade_amount = 0.00002  # BTC per order
take_profit_percentage = 0.05  # 5% profit target
stop_loss_percentage = 0.03  # 3% loss prevention
trailing_stop_percentage = 0.02  # 2% trailing stop
trade_log = "kraken_trade_history.csv"  # File to store trade history

# 🔹 Telegram Bot Credentials (Optional, for Alerts)
TELEGRAM_BOT_TOKEN = "your_telegram_bot_token"
TELEGRAM_CHAT_ID = "your_telegram_chat_id"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(url, data=data)

def get_current_price():
    ticker = exchange.fetch_ticker(symbol)
    return ticker['last']

def place_buy_order():
    buy_price = get_current_price()
    order = exchange.create_limit_buy_order(symbol, trade_amount, buy_price)
    print(f"🟢 BOUGHT {trade_amount} BTC at ${buy_price}")
    send_telegram_message(f"🟢 BOUGHT {trade_amount} BTC at ${buy_price}")
    return buy_price

def place_sell_order(sell_price):
    order = exchange.create_limit_sell_order(symbol, trade_amount, sell_price)
    print(f"🔴 SOLD {trade_amount} BTC at ${sell_price}")
    send_telegram_message(f"🔴 SOLD {trade_amount} BTC at ${sell_price}")

def trailing_sell():
    highest_price = get_current_price()
    stop_price = highest_price * (1 - trailing_stop_percentage)

    while True:
        current_price = get_current_price()

        if current_price > highest_price:
            highest_price = current_price  # Update highest price
            stop_price = highest_price * (1 - trailing_stop_percentage)

        if current_price <= stop_price:
            place_sell_order(current_price)
            break

        time.sleep(5)  # Check price every 5 seconds

def check_take_profit_and_stop_loss(buy_price):
    while True:
        current_price = get_current_price()
        target_price = buy_price * (1 + take_profit_percentage)
        stop_loss_price = buy_price * (1 - stop_loss_percentage)

        if current_price >= target_price:
            place_sell_order(current_price)
            print(f"✅ TAKE PROFIT Triggered at ${current_price}")
            send_telegram_message(f"✅ TAKE PROFIT Triggered at ${current_price}")
            break

        elif current_price <= stop_loss_price:
            place_sell_order(current_price)
            print(f"⛔ STOP-LOSS Triggered at ${current_price}")
            send_telegram_message(f"⛔ STOP-LOSS Triggered at ${current_price}")
            break

        time.sleep(5)  # Check price every 5 seconds

def execute_trading_strategy():
    buy_price = place_buy_order()
    check_take_profit_and_stop_loss(buy_price)
    trailing_sell()

execute_trading_strategy()