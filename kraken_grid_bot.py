import ccxt  # Connects to Kraken API
import time  # Manages trade execution timing
import csv  # Logs trade history in CSV format
import os  # Handles environment variables & file operations
import requests  # Sends Telegram notifications
import json  # Parses API responses
import datetime  # Adds timestamps to trades
import traceback  # Captures detailed error information
import dotenv  # Securely loads API keys from .env file

# 🔹 Load environment variables from the .env file
dotenv.load_dotenv('/root/.env')

# 🔹 Retrieve Kraken API credentials from .env file
api_key = os.getenv("KRAKEN_API_KEY")
api_secret = os.getenv("KRAKEN_API_SECRET")

# 🔹 Validate API Key presence (Ensures the bot has access)
if not api_key or not api_secret:
    print("❌ API Key Error: Missing API key or secret. Check .env file.")
    exit()

# 🔹 Initialize Kraken Exchange Connection
exchange = ccxt.kraken({
    'apiKey': api_key.strip(),  # Removes accidental spaces
    'secret': api_secret.strip(),  # Removes accidental spaces
})

# 🔹 Verify API Key validity (Prevents errors before trading starts)
try:
    exchange.fetch_balance()  # Fetches account balance to validate connection
    print("✅ API Key is valid! Connected to Kraken successfully.")
except Exception as e:
    print(f"❌ API Key Validation Failed: {e}")
    exit()

# 🔹 Trading Configuration
trading_pairs = ["BTC/USD", "ETH/USD", "SOL/USD"]  # Pairs to trade
grid_levels = 5  # Number of buy/sell orders
grid_spacing = 10  # Price difference between grid orders (in USD)
take_profit_percentage = 0.05  # 5% profit target per trade
stop_loss_percentage = 0.03  # 3% maximum loss per trade
trailing_stop_percentage = 0.02  # 2% trailing stop-loss
trade_log = "/root/kraken_trade_history.csv"  # CSV log file location

# 🔹 Telegram Bot for Notifications
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # Bot API token
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # Your Telegram Chat ID

# 🔹 Kraken Minimum Trade Sizes (Auto-fetch)
minimum_trade_sizes = {}

def fetch_min_trade_sizes():
    """
    Fetches the minimum trade size required for each trading pair.
    This prevents placing orders that are too small for Kraken.
    """
    global minimum_trade_sizes
    try:
        markets = exchange.load_markets()
        for pair in trading_pairs:
            if pair in markets:
                min_size = markets[pair]['limits']['amount']['min']
                minimum_trade_sizes[pair] = min_size
        print(f"✅ Minimum trade sizes: {minimum_trade_sizes}")
    except Exception as e:
        print(f"⚠ Error fetching minimum trade sizes: {e}")

# 🔹 Telegram Message Function with Rate Limit Handling
def send_telegram_message(message):
    """
    Sends alerts to Telegram with built-in rate limit handling.
    Prevents exceeding API limits by automatically retrying after a cooldown.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=data)
        if response.status_code == 429:  # Telegram rate limit exceeded
            retry_after = response.json().get('parameters', {}).get('retry_after', 60)
            print(f"⚠ Telegram rate limit exceeded. Retrying in {retry_after} sec.")
            time.sleep(retry_after)
            requests.post(url, data=data)  # Retry the request
    except Exception as e:
        print(f"⚠ Telegram Message Failed: {e}")

# 🔹 Fetches Current Price for a Symbol
def get_current_price(symbol):
    """
    Retrieves the latest market price for a given trading pair.
    Returns None if the price fetch fails.
    """
    try:
        ticker = exchange.fetch_ticker(symbol)
        return ticker['last']
    except Exception as e:
        print(f"⚠ Failed to fetch price for {symbol}: {e}")
        return None

# 🔹 Places a Buy Order
def place_buy_order(symbol):
    """
    Places a limit buy order at the current market price.
    Ensures the trade amount meets Kraken's minimum requirements.
    """
    buy_price = get_current_price(symbol)
    trade_amount = minimum_trade_sizes.get(symbol, 0.0001) * 1.2  # Adds buffer to min size

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

# 🔹 Places a Sell Order
def place_sell_order(symbol, sell_price):
    """
    Places a limit sell order.
    """
    trade_amount = minimum_trade_sizes.get(symbol, 0.0001) * 1.2
    try:
        order = exchange.create_limit_sell_order(symbol, trade_amount, sell_price)
        print(f"🔴 SOLD {trade_amount} {symbol} at ${sell_price}")
        send_telegram_message(f"🔴 SOLD {trade_amount} {symbol} at ${sell_price}")
        log_trade("SELL", symbol, sell_price, trade_amount)
    except Exception as e:
        print(f"⚠ Order failed for {symbol}: {e}")
        send_telegram_message(f"⚠ Order failed for {symbol}: {e}")

# 🔹 Implements Trailing Stop
def trailing_sell(symbol, buy_price):
    """
    Monitors price movements and sells when the price drops below the trailing stop threshold.
    """
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

        time.sleep(5)

# 🔹 Manages Take-Profit & Stop-Loss
def check_take_profit_and_stop_loss(symbol, buy_price):
    """
    Monitors price fluctuations and triggers a sell order when a profit target or stop-loss threshold is reached.
    """
    while True:
        current_price = get_current_price(symbol)
        target_price = buy_price * (1 + take_profit_percentage)
        stop_loss_price = buy_price * (1 - stop_loss_percentage)

        if current_price >= target_price:
            place_sell_order(symbol, current_price)
            send_telegram_message(f"✅ TAKE PROFIT at ${current_price}")
            break
        elif current_price <= stop_loss_price:
            place_sell_order(symbol, current_price)
            send_telegram_message(f"⛔ STOP-LOSS at ${current_price}")
            break

        time.sleep(5)

# 🔹 Logs Trades to CSV
def log_trade(order_type, symbol, price, amount):
    """
    Saves all trades in a CSV file for record-keeping.
    """
    file_exists = os.path.isfile(trade_log)
    with open(trade_log, mode='a', newline='') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Timestamp", "Order Type", "Symbol", "Price", "Amount"])
        writer.writerow([datetime.datetime.now(), order_type, symbol, price, amount])

# 🔹 Main Trading Execution
def execute_trading_strategy():
    fetch_min_trade_sizes()
    for symbol in trading_pairs:
        buy_price = place_buy_order(symbol)
        if buy_price:
            check_take_profit_and_stop_loss(symbol, buy_price)
            trailing_sell(symbol, buy_price)

execute_trading_strategy()