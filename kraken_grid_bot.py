import ccxt
import time
import csv
import os
import datetime
import requests

# 🔹 Replace with your Kraken API Keys
api_key = "Zzmf8P6h8jzPa1Cu9q7xCFLebFML/QvNul/c1n4ujtil+QEJxHHamW/W"
api_secret = "tn3ft57r/SR1IfQA6xsDnjA5HKfPH73dTqvXqBHWPoQtYrv87oaoS4Z7zsmmnw1St4JQYHfFi2nCcvr2l1R6Wg=="

# 🔹 Connect to Kraken
exchange = ccxt.kraken({
    'apiKey': api_key,
    'secret': api_secret,
})

# 🔹 Trading settings
symbol = "BTC/USD"  # Trading pair
grid_levels = 5  # Number of grid orders
grid_spacing = 100  # USD price gap between orders
trade_amount = 0.0005  # BTC per order
trade_log = "kraken_trade_history.csv"  # File to save trades

# 🔹 Telegram Bot Credentials (Optional)
TELEGRAM_BOT_TOKEN = "your_telegram_bot_token"
TELEGRAM_CHAT_ID = "7394557654"

# ✅ Function to send Telegram notifications
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    requests.post(url, data=payload)

# ✅ Function to fetch current price
def get_price():
    ticker = exchange.fetch_ticker(symbol)
    return ticker['last']

# ✅ Function to place buy and sell grid orders
def place_grid_orders():
    current_price = get_price()
    
    for i in range(grid_levels):
        buy_price = current_price - (i * grid_spacing)
        sell_price = current_price + (i * grid_spacing)

        # Place limit buy order
        exchange.create_limit_buy_order(symbol, trade_amount, buy_price)
        print(f"🟢 BUY order placed at {buy_price}")

        # Place limit sell order
        exchange.create_limit_sell_order(symbol, trade_amount, sell_price)
        print(f"🔴 SELL order placed at {sell_price}")

# ✅ Function to log trades in CSV file
def log_trade(trade):
    file_exists = os.path.isfile(trade_log)
    
    with open(trade_log, mode="a", newline="") as file:
        writer = csv.writer(file)
        
        # Write headers if new file
        if not file_exists:
            writer.writerow(["Timestamp", "Type", "Amount", "Price", "Total Value"])
        
        # Convert timestamp
        timestamp = datetime.datetime.utcfromtimestamp(trade['timestamp'] / 1000)
        total_value = round(trade['amount'] * trade['price'], 2)
        
        # Write trade data
        writer.writerow([timestamp, trade['side'].upper(), trade['amount'], trade['price'], total_value])

    # Send Telegram notification
    message = f"📈 Trade Executed: {trade['side'].upper()} {trade['amount']} BTC @ ${trade['price']}"
    send_telegram_message(message)

# ✅ Function to track completed trades
def check_and_log_trades():
    while True:
        trades = exchange.fetch_my_trades(symbol)
        for trade in trades[-5:]:  # Log last 5 trades
            log_trade(trade)
        
        time.sleep(60)  # Update every 1 minute

# ✅ Start the bot
print("🚀 Starting Kraken Grid Trading Bot...")
place_grid_orders()
check_and_log_trades()

