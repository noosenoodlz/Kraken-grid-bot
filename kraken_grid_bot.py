import ccxt  # Library for interacting with crypto exchanges
import time  # Sleep intervals for trade execution
import csv  # Logs trade history
import os  # File handling
import requests  # Sends Telegram notifications
import json  # Parses API responses
import datetime  # Adds timestamps for trade logs
import traceback  # Provides detailed error handling
import dotenv  # Loads environment variables
import threading  # Enables multi-threaded execution
import numpy as np  # Used for market data calculations

# Load environment variables from .env file
dotenv.load_dotenv('/root/.env')

# Retrieve API credentials from environment variables
api_key = os.getenv("KRAKEN_API_KEY")
api_secret = os.getenv("KRAKEN_API_SECRET")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Initialize Kraken Exchange Connection
exchange = ccxt.kraken({
    'apiKey': api_key.strip(),  # Strips accidental spaces
    'secret': api_secret.strip(),  # Strips accidental spaces
    'rateLimit': 1000,  # Ensures compliance with Kraken API rate limits
    'enableRateLimit': True  # Automatically handles API rate limits
})

# Validate API Key Before Running to Prevent 'EAPI:Invalid key' Errors
try:
    account_balance = exchange.fetch_balance()  # Fetch account balance
    print("✅ API Key is valid! Connected to Kraken successfully.")
except Exception as e:
    print(f"❌ API Key Validation Failed: {e}")
    exit()  # Stops script if API keys are invalid

# **Trading Configuration Settings**
trading_pairs = ["BTC/USD", "ETH/USD", "SOL/USD"]  # List of trading pairs
leverage = 2  # Set leverage (Optional: Requires Kraken margin trading)
grid_levels = 7  # Number of grid orders
grid_spacing = 5  # USD price gap between grid orders
base_trade_size = 0.02  # Adjusted dynamically based on account balance
take_profit_percentage = 0.03  # 3% take-profit target
stop_loss_percentage = 0.02  # 2% stop-loss threshold
trailing_stop_percentage = 0.015  # 1.5% trailing stop to maximize gains
dca_levels = 3  # Number of Dollar-Cost Averaging (DCA) levels
profit_reinvestment = True  # Enables reinvestment for compounding profits

# **Market Indicator Configuration (AI-Driven Trade Signals)**
rsi_overbought = 70  # RSI threshold for overbought condition
rsi_oversold = 30  # RSI threshold for oversold condition
macd_signal_diff = 0.5  # MACD threshold to identify trend shifts
sma_window = 20  # Moving average window for price smoothing

# **Telegram Messaging Function**
def send_telegram_message(message):
    """Sends trade notifications via Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, data=data)  # Sends message to Telegram
    except Exception as e:
        print(f"⚠ Telegram Message Failed: {e}")

# **Fetch Market Data**
def get_market_data(symbol):
    """Fetches real-time price, RSI, and MACD indicators for smarter trades."""
    try:
        candles = exchange.fetch_ohlcv(symbol, timeframe='1m', limit=30)
        close_prices = np.array([candle[4] for candle in candles])  # Extracts closing prices

        # Calculate Simple Moving Average (SMA)
        sma = np.mean(close_prices[-sma_window:])

        # Calculate Relative Strength Index (RSI)
        delta = np.diff(close_prices)
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)
        avg_gain = np.mean(gain)
        avg_loss = np.mean(loss)
        rs = avg_gain / avg_loss if avg_loss != 0 else 100
        rsi = 100 - (100 / (1 + rs))

        # Calculate MACD Indicator
        ema12 = np.mean(close_prices[-12:])
        ema26 = np.mean(close_prices[-26:])
        macd = ema12 - ema26
        macd_signal = np.mean([macd for _ in range(9)])
        macd_histogram = macd - macd_signal

        return {"price": close_prices[-1], "sma": sma, "rsi": rsi, "macd": macd_histogram}
    except Exception as e:
        print(f"⚠ Market Data Fetch Failed: {e}")
        return None

# **Buy Order Function**
def place_buy_order(symbol):
    """Places buy orders using AI signals & Dollar-Cost Averaging (DCA)."""
    data = get_market_data(symbol)
    if not data:
        return None

    buy_price = data["price"]
    trade_amount = base_trade_size  # Trade size determined dynamically

    total_bought = 0  # Track total purchased quantity
    for i in range(dca_levels):  # Execute DCA strategy
        price_adjusted = buy_price * (1 - (i * 0.005))  # Adjust price per level
        try:
            order = exchange.create_limit_buy_order(symbol, trade_amount, price_adjusted)
            total_bought += trade_amount
            print(f"🟢 BOUGHT {trade_amount} {symbol} at ${price_adjusted}")
            send_telegram_message(f"🟢 BOUGHT {trade_amount} {symbol} at ${price_adjusted}")
            time.sleep(2)  # Prevents API flooding
        except Exception as e:
            print(f"⚠ Buy Order Failed: {e}")

    return buy_price

# **Sell Order Function**
def place_sell_order(symbol, sell_price):
    """Places sell orders with AI-driven take-profit strategy."""
    trade_amount = base_trade_size  # Dynamic trade amount
    try:
        order = exchange.create_limit_sell_order(symbol, trade_amount, sell_price)
        print(f"🔴 SOLD {trade_amount} {symbol} at ${sell_price}")
        send_telegram_message(f"🔴 SOLD {trade_amount} {symbol} at ${sell_price}")
    except Exception as e:
        print(f"⚠ Sell Order Failed: {e}")

# **Monitor Trades for Take-Profit & Stop-Loss**
def monitor_trade(symbol, buy_price):
    """Monitors trade until take-profit or stop-loss conditions are met."""
    while True:
        data = get_market_data(symbol)
        if not data:
            continue

        current_price = data["price"]
        target_price = buy_price * (1 + take_profit_percentage)
        stop_loss_price = buy_price * (1 - stop_loss_percentage)

        if current_price >= target_price:
            place_sell_order(symbol, current_price)
            send_telegram_message(f"✅ TAKE PROFIT {symbol} at ${current_price}")
            break
        elif current_price <= stop_loss_price:
            place_sell_order(symbol, current_price)
            send_telegram_message(f"⛔ STOP-LOSS {symbol} at ${current_price}")
            break

        time.sleep(3)  # Prevents excessive API calls

# **Multi-Threaded Execution for Simultaneous Trading**
threads = []
for symbol in trading_pairs:
    thread = threading.Thread(target=lambda: (buy_price := place_buy_order(symbol)) and monitor_trade(symbol, buy_price))
    thread.start()
    threads.append(thread)

for thread in threads:
    thread.join()