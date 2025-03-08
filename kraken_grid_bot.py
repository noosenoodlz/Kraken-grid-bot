import ccxt                # Kraken API connection
import time                # For delays and cooldowns
import csv                 # For trade logging
import os                  # For file handling and .env loading
import requests            # For sending Telegram notifications
import json                # For JSON parsing (if needed)
import datetime            # For timestamping trades
import traceback           # For detailed error tracking
import threading           # For parallel processing
import statistics          # For ATR calculation (volatility)
import dotenv              # For loading .env securely

# =============================================================================
# 1. Load API Credentials Securely
# =============================================================================
dotenv.load_dotenv('/root/.env')
api_key = os.getenv("KRAKEN_API_KEY")
api_secret = os.getenv("KRAKEN_API_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not api_key or not api_secret:
    print("❌ API Key Error: Missing API key or secret. Check your .env file.")
    exit()

# =============================================================================
# 2. Connect to Kraken and Validate API Key
# =============================================================================
exchange = ccxt.kraken({
    'apiKey': api_key.strip(),
    'secret': api_secret.strip(),
})

try:
    exchange.fetch_balance()  # validate connection
    print("✅ API Key is valid! Connected to Kraken successfully.")
except Exception as e:
    print(f"❌ API Key Validation Failed: {e}")
    exit()

# =============================================================================
# 3. Trading & Bot Settings
# =============================================================================
# Trading pairs we wish to trade. Kraken uses "XBT/USD" for Bitcoin.
trading_pairs = {
    "BTC/USD": "XBT/USD",  # Kraken uses XBT for Bitcoin
    "ETH/USD": "ETH/USD",
    "SOL/USD": "SOL/USD",
}

# Basic grid/trade parameters (these may be modified dynamically)
grid_levels = 5                  # number of orders (not fully used in this example)
grid_spacing = 10                # base USD gap between orders (we will adjust it)
take_profit_percentage = 0.05    # 5% profit target
stop_loss_percentage = 0.03      # 3% stop-loss threshold
trailing_stop_percentage = 0.02  # 2% trailing stop
trade_log = "/root/kraken_trade_history.csv"  # trade history CSV

# Cooldown between trades (in seconds)
COOLDOWN_TIME = 60

# Profit target for smart exit (example: $100 profit)
TARGET_PROFIT = 100.0

# =============================================================================
# 4. Global Variables for Minimum Sizes and Balance Tracking
# =============================================================================
minimum_trade_sizes = {}   # Filled dynamically from Kraken's markets

def fetch_min_trade_sizes():
    """
    Fetches and stores Kraken's minimum trade sizes for each trading pair.
    """
    global minimum_trade_sizes
    try:
        markets = exchange.load_markets()
        for pair in trading_pairs:
            if pair in markets:
                min_size = markets[pair]['limits']['amount']['min']
                minimum_trade_sizes[pair] = min_size
            else:
                print(f"⚠ Warning: {pair} not found in Kraken markets.")
        print(f"✅ Minimum trade sizes: {minimum_trade_sizes}")
    except Exception as e:
        print(f"⚠ Error fetching minimum trade sizes: {e}")

def get_trade_amount(pair):
    """
    Determines a trade amount based on Kraken's minimum size.
    Here we add a 20% buffer over the minimum.
    """
    min_size = minimum_trade_sizes.get(pair, 0.0001)
    return min_size * 1.2

# =============================================================================
# 5. Telegram Messaging with Rate Limit Handling
# =============================================================================
def send_telegram_message(message):
    """
    Sends a message to Telegram. If the rate limit is hit, waits for the cooldown.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠ Telegram credentials missing. Skipping alert.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=data)
        if response.status_code == 429:  # Too Many Requests
            retry_after = response.json().get('parameters', {}).get('retry_after', 60)
            print(f"⚠ Telegram rate limit exceeded. Retrying in {retry_after} sec.")
            time.sleep(retry_after)
            requests.post(url, data=data)
    except Exception as e:
        print(f"⚠ Telegram Message Failed: {e}")

# =============================================================================
# 6. Market Data & Volatility Functions
# =============================================================================
def get_current_price(symbol):
    """
    Retrieves the current market price for the given symbol.
    Returns None if the price cannot be fetched.
    """
    try:
        ticker = exchange.fetch_ticker(symbol)
        return ticker['last']
    except Exception as e:
        print(f"⚠ Failed to fetch price for {symbol}: {e}")
        return None

def get_market_volatility(symbol, timeframe='1h', limit=20):
    """
    Calculates an approximate volatility using the Average True Range (ATR) of recent candles.
    This ATR value is used to adjust grid spacing dynamically.
    """
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        atr_values = []
        for candle in ohlcv:
            high, low, close = candle[2], candle[3], candle[4]
            atr_values.append(high - low)
        if atr_values:
            atr = statistics.mean(atr_values)
            return atr
    except Exception as e:
        print(f"⚠ Failed to fetch volatility data for {symbol}: {e}")
    return grid_spacing  # fallback to base grid spacing

# =============================================================================
# 7. Order Placement Functions
# =============================================================================
def place_buy_order(pair):
    """
    Places a limit buy order for the specified pair.
    Validates the current price and adjusts the trade amount based on the minimum.
    """
    kraken_pair = trading_pairs[pair]
    buy_price = get_current_price(kraken_pair)
    trade_amount = get_trade_amount(pair)

    if buy_price is None or buy_price <= 0:
        print(f"❌ ERROR: Invalid price for {pair}. Aborting buy order.")
        return None

    print(f"🟢 Attempting to BUY {trade_amount} {pair} at ${buy_price}")
    try:
        order = exchange.create_limit_buy_order(kraken_pair, trade_amount, buy_price)
        send_telegram_message(f"🟢 BOUGHT {trade_amount} {pair} at ${buy_price}")
        log_trade("BUY", pair, buy_price, trade_amount)
        return buy_price
    except Exception as e:
        print(f"⚠ Order failed for {pair}: {e}")
        send_telegram_message(f"⚠ Order failed for {pair}: {e}")
        return None

def place_sell_order(pair, sell_price):
    """
    Places a limit sell order for the specified pair.
    """
    kraken_pair = trading_pairs[pair]
    trade_amount = get_trade_amount(pair)
    print(f"🔴 Attempting to SELL {trade_amount} {pair} at ${sell_price}")
    try:
        order = exchange.create_limit_sell_order(kraken_pair, trade_amount, sell_price)
        send_telegram_message(f"🔴 SOLD {trade_amount} {pair} at ${sell_price}")
        log_trade("SELL", pair, sell_price, trade_amount)
    except Exception as e:
        print(f"⚠ Order failed for {pair}: {e}")
        send_telegram_message(f"⚠ Order failed for {pair}: {e}")

# =============================================================================
# 8. Advanced Trading Logic
# =============================================================================
def trailing_sell(pair, buy_price):
    """
    Monitors the market price after a buy to exit via a trailing stop.
    """
    kraken_pair = trading_pairs[pair]
    highest_price = get_current_price(kraken_pair)
    stop_price = highest_price * (1 - trailing_stop_percentage)

    while True:
        current_price = get_current_price(kraken_pair)
        if current_price is None:
            time.sleep(5)
            continue

        if current_price > highest_price:
            highest_price = current_price
            stop_price = highest_price * (1 - trailing_stop_percentage)
        if current_price <= stop_price:
            place_sell_order(pair, current_price)
            break
        time.sleep(5)

def check_take_profit_and_stop_loss(pair, buy_price):
    """
    Continuously checks if the market price has reached either the take profit
    or stop loss threshold, and exits the trade accordingly.
    """
    kraken_pair = trading_pairs[pair]
    while True:
        current_price = get_current_price(kraken_pair)
        if current_price is None:
            time.sleep(5)
            continue

        target_price = buy_price * (1 + take_profit_percentage)
        stop_loss_price = buy_price * (1 - stop_loss_percentage)

        if current_price >= target_price:
            place_sell_order(pair, current_price)
            send_telegram_message(f"✅ TAKE PROFIT triggered for {pair} at ${current_price}")
            break
        elif current_price <= stop_loss_price:
            place_sell_order(pair, current_price)
            send_telegram_message(f"⛔ STOP-LOSS triggered for {pair} at ${current_price}")
            break

        time.sleep(5)

# =============================================================================
# 9. Trade Logging to CSV
# =============================================================================
def log_trade(order_type, pair, price, amount):
    """
    Logs the trade details (timestamp, order type, pair, price, and amount) to a CSV file.
    """
    file_exists = os.path.isfile(trade_log)
    with open(trade_log, mode='a', newline='') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(["Timestamp", "Order Type", "Pair", "Price", "Amount"])
        writer.writerow([datetime.datetime.now(), order_type, pair, price, amount])

# =============================================================================
# 10. Smart Exit: Check Total Profit and Stop Trading if Target is Met
# =============================================================================
def check_total_profit():
    """
    Reads the trade log CSV and calculates a simplified net profit.
    (Note: This example assumes buy orders are negative and sell orders positive.)
    If the target profit is met, the bot will exit.
    """
    if not os.path.isfile(trade_log):
        return False
    total_profit = 0.0
    try:
        with open(trade_log, 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                price = float(row["Price"])
                amount = float(row["Amount"])
                if row["Order Type"] == "BUY":
                    total_profit -= price * amount
                elif row["Order Type"] == "SELL":
                    total_profit += price * amount
        print(f"💰 Current net profit (approx.): ${total_profit:.2f}")
        if total_profit >= TARGET_PROFIT:
            send_telegram_message(f"🎉 Profit target of ${TARGET_PROFIT} reached. Stopping bot.")
            return True
    except Exception as e:
        print(f"⚠ Error calculating total profit: {e}")
    return False

# =============================================================================
# 11. Balance-Based Trade Sizing (Optional)
# =============================================================================
def get_trade_amount_from_balance(pair):
    """
    Adjusts the trade amount based on available balance.
    Uses 20% of available funds for the asset (if possible).
    """
    try:
        balance = exchange.fetch_balance()
        asset = pair.split('/')[0]  # e.g., "BTC" from "BTC/USD"
        available_funds = balance['free'].get(asset, 0)
        min_size = minimum_trade_sizes.get(pair, 0.0001)
        # Use 20% of available funds, or twice the minimum—whichever is lower.
        trade_amount = min(available_funds * 0.2, min_size * 2)
        return max(trade_amount, min_size)
    except Exception as e:
        print(f"⚠ Error fetching balance for {pair}: {e}")
        return minimum_trade_sizes.get(pair, 0.0001) * 1.2

# =============================================================================
# 12. Execution Function for Each Trading Pair (with Threading & Cooldown)
# =============================================================================
def execute_trading_strategy(pair):
    """
    Executes the full trading strategy for a given trading pair.
    It:
    - Fetches minimum trade sizes
    - Places a buy order
    - Monitors take profit and stop loss
    - Uses trailing stop for exit
    - Implements a cooldown period after trades
    - Checks for a profit target to exit trading entirely
    """
    try:
        print(f"🚀 Starting trading strategy for {pair}...")
        buy_price = place_buy_order(pair)
        if buy_price:
            check_take_profit_and_stop_loss(pair, buy_price)
            trailing_sell(pair, buy_price)
            print(f"⏳ Cooldown: Waiting {COOLDOWN_TIME} seconds before next trade for {pair}...")
            time.sleep(COOLDOWN_TIME)
    except Exception as e:
        print(f"❌ Critical Error in strategy for {pair}: {e}")
        traceback.print_exc()
        send_telegram_message(f"❌ Critical Error in {pair}: {e}")
    # After each pair completes, check if the overall profit target is reached.
    if check_total_profit():
        print("🎉 Profit target reached. Exiting bot.")
        exit()

# =============================================================================
# 13. Main Loop: Run Each Trading Pair in a Separate Thread
# =============================================================================
def main():
    fetch_min_trade_sizes()
    threads = []
    for pair in trading_pairs:
        # For each trading pair, start the strategy in a new thread.
        t = threading.Thread(target=execute_trading_strategy, args=(pair,))
        t.start()
        threads.append(t)
    # Wait for all threads to finish (if ever)
    for t in threads:
        t.join()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("🛑 Trading bot stopped manually.")
    except Exception as e:
        print(f"❌ Critical Error in main execution: {e}")
        traceback.print_exc()
        send_telegram_message(f"❌ Bot crashed: {e}")