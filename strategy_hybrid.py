
import os
import time
import requests
import hmac
import hashlib
import json
import csv
import pandas as pd
from datetime import datetime

# === KONFIGURATION ===
SYMBOLS = ["BTCUSDT", "ETHUSDT", "DOGEUSDT"]
USDT_EINSATZ = 100
INTERVAL = "15"
LIMIT = 200
BASE_URL = "https://api.bybit.com"
EMA_LEN = 200
RSI_LEN = 14
RSI_BUY = 40
RSI_SELL = 60
RSI_EXIT = 50
BREAKOUT_LEN = 20
ATR_LEN = 14
ATR_MULT = 2.0

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

# === FUNKTIONEN ===
def create_signature(payload):
    return hmac.new(API_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()

def get_klines(symbol):
    url = f"{BASE_URL}/v5/market/kline"
    params = {"category": "spot", "symbol": symbol, "interval": INTERVAL, "limit": LIMIT}
    r = requests.get(url, params=params)
    raw = r.json()["result"]["list"]
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"])
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["open"] = df["open"].astype(float)
    return df

def ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def rsi(series, period):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def atr(df, period):
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def log_trade(symbol, trade_type, direction, qty, price, signal_type):
    with open("tradelog.csv", mode="a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([datetime.now().isoformat(), symbol, trade_type, direction, qty, price, signal_type])

def place_order(symbol, side, qty, price):
    timestamp = str(int(time.time() * 1000))
    recv_window = "5000"
    body = {
        "category": "spot",
        "symbol": symbol,
        "side": side,
        "orderType": "Limit",
        "qty": str(qty),
        "price": str(price),
        "timeInForce": "GTC"
    }
    body_json = json.dumps(body, separators=(",", ":"))
    payload = f"{timestamp}{API_KEY}{recv_window}{body_json}"
    sign = hmac.new(API_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    headers = {
        "X-BAPI-API-KEY": API_KEY,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-RECV-WINDOW": recv_window,
        "X-BAPI-SIGN": sign,
        "Content-Type": "application/json"
    }
    url = f"{BASE_URL}/v5/order/create"
    r = requests.post(url, headers=headers, data=body_json)
    print(f"[{symbol}] 📨 Order: {side} {qty} @ {price} USDT → {r.text}")

# === BOT LOGIK ===
def run_bot():
    for symbol in SYMBOLS:
        try:
            df = get_klines(symbol)
            df["ema"] = ema(df["close"], EMA_LEN)
            df["rsi"] = rsi(df["close"], RSI_LEN)
            df["atr"] = atr(df, ATR_LEN)

            close = df["close"].iloc[-1]
            ema_val = df["ema"].iloc[-1]
            rsi_val = df["rsi"].iloc[-1]
            atr_val = df["atr"].iloc[-1]
            high_break = df["close"].shift(1).rolling(BREAKOUT_LEN).max().iloc[-1]

            trending = True
            bullish = close > ema_val

            qty = int(USDT_EINSATZ / close)

            # RSI BUY
            if rsi_val < RSI_BUY and not trending and bullish:
                print(f"[{symbol}] ✅ RSI BUY SIGNAL")
                place_order(symbol, "Buy", qty, round(close, 4))
                log_trade(symbol, "Buy", "Long", qty, close, "RSI")

            # BREAKOUT BUY
            elif close > high_break and trending and bullish:
                print(f"[{symbol}] 🚀 BREAKOUT LONG SIGNAL")
                place_order(symbol, "Buy", qty, round(close, 4))
                log_trade(symbol, "Buy", "Long", qty, close, "Breakout")

        except Exception as e:
            print(f"[{symbol}] ❌ Fehler: {e}")

if __name__ == "__main__":
    run_bot()
