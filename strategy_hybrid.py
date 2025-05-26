
import os
import time
import requests
import hmac
import hashlib
import json
import numpy as np
from datetime import datetime
import pandas as pd

# === ENV Variablen ===
API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")

# === KONSTANTEN ===
SYMBOL = "DOGEUSDT"
INTERVAL = "15"  # Minutenkerze
LIMIT = 200  # Anzahl Kerzen
BASE_URL = "https://api.bybit.com"
USDT_EINSATZ = 10
ADX_LEN = 14
ADX_SMOOTH = 14
ADX_THRESHOLD = 20
EMA_LEN = 200
RSI_LEN = 14
RSI_BUY = 40
RSI_SELL = 60
RSI_EXIT = 50
BREAKOUT_LEN = 20
ATR_LEN = 14
ATR_MULT = 2.0

has_position = False
entry_price = None
entry_type = None
entry_direction = None

# === HELFER ===
def create_signature(payload):
    return hmac.new(API_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()

def get_klines():
    url = f"{BASE_URL}/v5/market/kline"
    params = {"category": "spot", "symbol": SYMBOL, "interval": INTERVAL, "limit": LIMIT}
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

def place_order(side, qty, price):
    timestamp = str(int(time.time() * 1000))
    body = {
        "category": "spot",
        "symbol": SYMBOL,
        "side": side,
        "orderType": "Limit",
        "qty": str(qty),
        "price": str(price),
        "timeInForce": "GTC"
    }
    payload = f"{timestamp}{API_KEY}{json.dumps(body, separators=(',', ':'))}"
    sign = create_signature(payload)
    headers = {
        "X-BAPI-API-KEY": API_KEY,
        "X-BAPI-TIMESTAMP": timestamp,
        "X-BAPI-SIGN": sign,
        "Content-Type": "application/json"
    }
    url = f"{BASE_URL}/v5/order/create"
    r = requests.post(url, headers=headers, data=json.dumps(body))
    print(f"📨 Order: {side} {qty} @ {price} USDT → {r.text}")

# === MAIN LOGIK (Platzhalter für vollständige Logik) ===
def run():
    global has_position, entry_price, entry_type, entry_direction

    df = get_klines()
    df["ema"] = ema(df["close"], EMA_LEN)
    df["rsi"] = rsi(df["close"], RSI_LEN)
    df["atr"] = atr(df, ATR_LEN)

    close = df["close"].iloc[-1]
    ema_val = df["ema"].iloc[-1]
    rsi_val = df["rsi"].iloc[-1]
    atr_val = df["atr"].iloc[-1]
    high_break = df["close"].shift(1).rolling(BREAKOUT_LEN).max().iloc[-1]
    low_break = df["close"].shift(1).rolling(BREAKOUT_LEN).min().iloc[-1]

    trending = True  # ADX Platzhalter
    bullish = close > ema_val
    bearish = close < ema_val

    if not has_position:
        if rsi_val < RSI_BUY and not trending and bullish:
            print("✅ RSI BUY SIGNAL")
            qty = round(USDT_EINSATZ / close, 2)
            place_order("Buy", qty, round(close, 4))
            has_position = True
            entry_price = close
            entry_type = "RSI"
            entry_direction = "Long"
        elif close > high_break and trending and bullish:
            print("🚀 BREAKOUT LONG SIGNAL")
            qty = round(USDT_EINSATZ / close, 2)
            place_order("Buy", qty, round(close, 4))
            has_position = True
            entry_price = close
            entry_type = "Breakout"
            entry_direction = "Long"
    else:
        if rsi_val > RSI_EXIT:
            print("📤 RSI EXIT")
            place_order("Sell", qty, round(close, 4))
            has_position = False
        elif close < (entry_price - atr_val * ATR_MULT):
            print("📉 TRAILING STOP EXIT")
            place_order("Sell", qty, round(close, 4))
            has_position = False

if __name__ == "__main__":
    run()
