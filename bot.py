import os
import time
import requests
import ccxt
import json
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("xxxx")
TELEGRAM_CHAT_ID = os.getenv("xxxxx1")
TELEGRAM_TOPIC_ID=xxx
BYBIT_API_KEY = os.getenv("BYBIT_API_KEY")
BYBIT_SECRET = os.getenv("BYBIT_SECRET")

exchange = ccxt.bybit({
    'apiKey': BYBIT_API_KEY,
    'secret': BYBIT_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

def get_session_tag():
    hour = datetime.utcnow().hour + 7
    if 8 <= hour < 15: return "Asia"
    if 15 <= hour < 22: return "London"
    return "New York"

def get_position(symbol="BTC/USDT:USDT"):
    try:
        positions = exchange.fetch_positions([symbol])
        for pos in positions:
            if pos['symbol'] == symbol:
                return pos
    except Exception as e:
        print("Error fetching position:", e)
    return None

def send_telegram_message(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    }
    requests.post(url, data=payload)

def format_message(change_type, pos):
    side = pos['side']
    size = pos['contracts']
    price = pos['entryPrice']
    leverage = pos['leverage']
    session = get_session_tag()
    return f"""*{change_type} Position*
Symbol: {pos['symbol']}
Side: {side}
Size: {size}
Price: {price}
Leverage: {leverage}x
Session: {session}
Account: Day-Trade
"""

def main_loop():
    symbol = "BTC/USDT:USDT"
    last_file = "last_state.json"
    last_state = {}
    if os.path.exists(last_file):
        with open(last_file, "r") as f:
            last_state = json.load(f)

    while True:
        current = get_position(symbol)
        if not current:
            time.sleep(10)
            continue

        cur_size = current['contracts']
        last_size = last_state.get('contracts', 0)

        if cur_size != last_size:
            if last_size == 0 and cur_size > 0:
                msg = format_message("🟢 Opened", current)
            elif cur_size == 0 and last_size > 0:
                msg = format_message("🔴 Closed", current)
            elif cur_size > last_size:
                msg = format_message("📈 Added", current)
            elif cur_size < last_size:
                msg = format_message("🟠 Partial TP", current)
            else:
                msg = None

            if msg:
                send_telegram_message(msg)

            with open(last_file, "w") as f:
                json.dump(current, f)

        time.sleep(10)

if __name__ == "__main__":
    main_loop()
