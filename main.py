#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
轴心双子·全量化筛选系统 v1.1
"""

import os
import sys
import json
import time
import yaml
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

# =======================================================
# 全局配置
# =======================================================

CONFIG_PATH = "config.yaml"
SIGNAL_HISTORY = {}

STABLECOINS = set()

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
WECOM_WEBHOOK = os.environ.get("WECOM_WEBHOOK", "")
QMSG_QQ = os.environ.get("QMSG_QQ", "")
QMSG_KEY = os.environ.get("QMSG_KEY", "")

BINANCE_FAPI = "https://fapi.binance.com"
AICOIN_PUBLIC = "https://api.aicoin.net"
AICOIN_UID = "5374665"

VALID_PERPETUALS = set()


def load_config() -> Dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


CONFIG = load_config()
STABLECOINS = set(CONFIG["filter"]["stablecoins"])


def init_valid_perpetuals() -> None:
    global VALID_PERPETUALS
    try:
        resp = requests.get(
            f"{BINANCE_FAPI}/fapi/v1/exchangeInfo",
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json()
            for s in data.get("symbols", []):
                if (s.get("contractType") == "PERPETUAL" and
                        s.get("symbol", "").endswith("USDT")):
                    VALID_PERPETUALS.add(s["symbol"])
            print(f"[初始化] 已缓存 {len(VALID_PERPETUALS)} 个USDT永续合约")
    except Exception as e:
        print(f"[初始化] 获取合约列表失败: {e}")


def fetch_klines(symbol: str, interval: str, limit: int = 100) -> Optional[Dict]:
    if symbol not in VALID_PERPETUALS:
        return None

    try:
        resp = requests.get(
            f"{BINANCE_FAPI}/fapi/v1/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=3
        )
        if resp.status_code == 200:
            data = resp.json()
            return {
                "close": [float(d[4]) for d in data],
                "high": [float(d[2]) for d in data],
                "low": [float(d[3]) for d in data],
                "volume": [float(d[5]) for d in data],
                "open": [float(d[1]) for d in data]
            }
    except:
        pass

    try:
        resp = requests.get(
            f"{AICOIN_PUBLIC}/v1/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            if data:
                return {
                    "close": [float(d[4]) for d in data],
                    "high": [float(d[2]) for d in data],
                    "low": [float(d[3]) for d in data],
                    "volume": [float(d[5]) for d in data],
                    "open": [float(d[1]) for d in data]
                }
    except:
        pass

    try:
        resp = requests.get(
            f"{AICOIN_PUBLIC}/v1/klines",
            params={"symbol": symbol, "interval": interval, "limit": limit, "uid": AICOIN_UID},
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            if data:
                return {
                    "close": [float(d[4]) for d in data],
                    "high": [float(d[2]) for d in data],
                    "low": [float(d[3]) for d in data],
                    "volume": [float(d[5]) for d in data],
                    "open": [float(d[1]) for d in data]
                }
    except:
        pass

    return None


def fetch_24hr_tickers() -> List[Dict]:
    try:
        resp = requests.get(f"{BINANCE_FAPI}/fapi/v1/ticker/24hr", timeout=10)
        if resp.status_code == 200:
            return resp.json()
    except:
        pass
    return []


def calc_ema(closes: List[float], period: int) -> List[float]:
    if len(closes) < period:
        return []
    ema = [sum(closes[:period]) / period]
    multiplier = 2 / (period + 1)
    for price in closes[period:]:
        ema.append(price * multiplier + ema[-1] * (1 - multiplier))
    return ema


def calc_rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(diff if diff > 0 else 0)
        losses.append(-diff if diff < 0 else 0)
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def calc_macd(closes: List[float]) -> Tuple[float, float, float]:
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    if not ema12 or not ema26:
        return 0, 0, 0
    dif = ema12[-1] - ema26[-1]
    difs = [e12 - e26 for e12, e26 in zip(ema12[-9:], ema26[-9:])]
    dea = sum(difs) / len(difs) if difs else dif
    return dif, dea, (dif - dea) * 2


def calc_kdj(highs: List[float], lows: List[float], closes: List[float], n: int = 9) -> Tuple[float, float, float]:
    if len(closes) < n:
        return 50, 50, 50
    low_n = min(lows[-n:])
    high_n = max(highs[-n:])
    rsv = (closes[-1] - low_n) / (high_n - low_n) * 100 if high_n != low_n else 50
    return rsv, rsv, 3 * rsv - 2 * rsv


def calc_cci(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    if len(closes) < period:
        return 0
    tp = [(h + l + c) / 3 for h, l, c in zip(highs[-period:], lows[-period:], closes[-period:])]
    tp_avg = sum(tp) / period
    md = sum(abs(t - tp_avg) for t in tp) / period
    if md == 0:
        return 0
    return (tp[-1] - tp_avg) / (0.015 * md)


def calc_adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 20.0
    tr, plus_dm, minus_dm = [], [], []
    for i in range(1, len(highs)):
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
        up = highs[i] - highs[i-1]
        down = lows[i-1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)
    atr = sum(tr[-period:]) / period
    plus_di = (sum(plus_dm[-period:]) / period) / atr * 100 if atr else 0
    minus_di = (sum(minus_dm[-period:]) / period) / atr * 100 if atr else 0
    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) else 0
    return dx


def calc_atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 0
    tr = []
    for i in range(1, len(highs)):
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
    return sum(tr[-period:]) / period


def calc_bollinger_bandwidth(closes: List[float], period: int = 20, std_mult: int = 2) -> float:
    if len(closes) < period:
        return 10.0
    recent = closes[-period:]
    avg = sum(recent) / period
    variance = sum((c - avg) ** 2 for c in recent) / period
    std = variance ** 0.5
    return (std * std_mult * 2) / avg * 100


def calc_obv(closes: List[float], volumes: List[float]) -> List[float]:
    if len(closes) < 2:
        return [0]
    obv = [0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]:
            obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i-1]:
            obv.append(obv[-1] - volumes[i])
        else:
            obv.append(obv[-1])
    return obv


def find_fractals(highs: List[float], lows: List[float]) -> Tuple[List[int], List[int]]:
    top_fractals, bottom_fractals = [], []
    for i in range(2, len(highs) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i-2] and highs[i] > highs[i+1] and highs[i] > highs[i+2]:
            top_fractals.append(i)
        if lows[i] < lows[i-1] and lows[i] < lows[i-2] and lows[i] < lows[i+1] and lows[i] < lows[i+2]:
            bottom_fractals.append(i)
    return top_fractals, bottom_fractals


def has_central_structure(klines: Dict) -> Tuple[bool, float, float]:
    closes = klines["close"]
    highs = klines["high"]
    lows = klines["low"]
    top_f, bottom_f = find_fractals(highs, lows)
    if len(top_f) < 3 or len(bottom_f) < 3:
        return False, 0, 0
    recent_tops = top_f[-3:]
    recent_bottoms = bottom_f[-3:]
    overlap_high = min(highs[i] for i in recent_tops)
    overlap_low = max(lows[i] for i in recent_bottoms)
    if overlap_high > overlap_low:
        return True, overlap_high, overlap_low
    return False, 0, 0


def detect_divergence(closes: List[float], macd_difs: List[float]) -> Tuple[bool, bool]:
    if len(closes) < 30 or len(macd_difs) < 30:
        return False, False
    recent_low = min(closes[-20:])
    recent_low_idx = closes[-20:].index(recent_low)
    prev_low = min(closes[-40:-20])
    prev_low_idx = closes[-40:-20].index(prev_low) + 20
    recent_high = max(closes[-20:])
    recent_high_idx = closes[-20:].index(recent_high)
    prev_high = max(closes[-40:-20])
    prev_high_idx = closes[-40:-20].index(prev_high) + 20
    bottom_div = (recent_low < prev_low and
                  macd_difs[-20:][recent_low_idx] > macd_difs[-40:-20][prev_low_idx])
    top_div = (recent_high > prev_high and
               macd_difs[-20:][recent_high_idx] < macd_difs[-40:-20][prev_high_idx])
    return bottom_div, top_div


def score_signal(symbol: str, klines_30m: Dict, klines_5m: Dict,
                 klines_4h: Dict, klines_1d: Dict, klines_1w: Dict,
                 ticker: Dict, is_long: bool) -> Tuple[int, Dict]:
    weights = CONFIG["weights"]
    score = 0
    detail = {}

    closes_30m = klines_30m["close"]
    highs_30m = klines_30m["high"]
    lows_30m = klines_30m["low"]
    volumes_30m = klines_30m["volume"]

    has_central, central_high, central_low = has_central_structure(klines_30m)
    if has_central:
        structure_score = weights["structure"]
        detail["structure"] = structure_score
        score += structure_score
        detail["central_high"] = central_high
        detail["central_low"] = central_low
    else:
        return 0, {"error": "无有效中枢"}

    difs = []
    for i in range(26, len(closes_30m)+1):
        dif, _, _ = calc_macd(closes_30m[:i])
        difs.append(dif)
    bottom_div, top_div = detect_divergence(closes_30m, difs)

    macd_score = 0
    if is_long and bottom_div:
        _, _, macd_4h = calc_macd(klines_4h["close"])
        macd_score = weights["macd"] if macd_4h > 0 else weights["macd"] // 2
    elif not is_long and top_div:
        macd_score = weights["macd"]
    score += macd_score
    detail["macd"] = macd_score

    avg_vol = sum(volumes_30m[-20:]) / 20 if len(volumes_30m) >= 20 else volumes_30m[-1]
    curr_vol = volumes_30m[-1]
    obv = calc_obv(closes_30m, volumes_30m)
    obv_new_high = obv[-1] > max(obv[-20:-1]) if len(obv) >= 20 else False

    vol_threshold = CONFIG["volume"]["breakout_long_mult"] if is_long else CONFIG["volume"]["breakout_short_mult"]
    vol_score = 0
    if curr_vol > avg_vol * vol_threshold:
        if obv_new_high:
            vol_score = weights["volume_obv"]
        else:
            vol_score = weights["volume_obv"] // 2
    score += vol_score
    detail["volume_obv"] = vol_score

    ema12 = calc_ema(closes_30m, 12)
    ema26 = calc_ema(closes_30m, 26)
    if ema12 and ema26 and ema12[-1] > ema26[-1] and closes_30m[-1] > ema12[-1]:
        ma_score = weights["ma_resonance"] if is_long else weights["ma_resonance"]
        score += ma_score
        detail["ma"] = ma_score
    else:
        detail["ma"] = 0

    rsi = calc_rsi(closes_30m, CONFIG["rsi"]["period"])
    rsi_score = 0
    if is_long and CONFIG["rsi"]["strong_min"] <= rsi <= CONFIG["rsi"]["strong_max"]:
        rsi_score = weights["rsi"]
    elif not is_long and rsi < CONFIG["rsi"]["weak_threshold"]:
        rsi_score = weights["rsi"]
    elif CONFIG["rsi"]["strong_min"] - 5 <= rsi <= CONFIG["rsi"]["strong_max"] + 5:
        rsi_score = weights["rsi"] // 2
    score += rsi_score
    detail["rsi"] = rsi_score
    detail["rsi_value"] = round(rsi, 2)

    _, _, j = calc_kdj(highs_30m, lows_30m, closes_30m, CONFIG["kdj"]["n"])
    kdj_score = 0
    if is_long and j < CONFIG["kdj"]["oversold"]:
        kdj_score = weights["kdj"]
    elif not is_long and j > CONFIG["kdj"]["overbought"]:
        kdj_score = weights["kdj"]
    score += kdj_score
    detail["kdj"] = kdj_score
    detail["j_value"] = round(j, 2)

    cci = calc_cci(highs_30m, lows_30m, closes_30m, CONFIG["cci"]["period"])
    cci_score = 0
    if is_long and cci > CONFIG["cci"]["strong_threshold"]:
        cci_score = weights["cci"]
    score += cci_score
    detail["cci"] = cci_score
    detail["cci_value"] = round(cci, 2)

    bb_width = calc_bollinger_bandwidth(closes_30m)
    if bb_width < CONFIG["bollinger"]["bandwidth_threshold"]:
        score += 5
        detail["bollinger"] = 5
    else:
        detail["bollinger"] = 0

    if klines_1w:
        high_52w = max(klines_1w["high"][-52:]) if len(klines_1w["high"]) >= 52 else max(klines_1w["high"])
        position = closes_30m[-1] / high_52w
        if is_long and position < 0.7:
            score += 5
            detail["weekly_position"] = 5
        elif not is_long and position > 0.85:
            score += 5
            detail["weekly_position"] = 5

    detail["total_score"] = score
    return score, detail


def apply_adx_filter(score: int, rating: str, klines_30m: Dict) -> Tuple[int, str, str]:
    adx = calc_adx(klines_30m["high"], klines_30m["low"], klines_30m["close"],
                   CONFIG["adx"]["period"])
    if adx > CONFIG["adx"]["trend_threshold"]:
        return score, rating, "趋势"
    elif adx < CONFIG["adx"]["range_threshold"]:
        if rating == "S":
            return score, "A", "震荡"
        elif rating == "A":
            return score, "B", "震荡"
    return score, rating, ""


def push_telegram(message: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        resp = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=10)
        return resp.status_code == 200
    except:
        return False


def push_wecom(message: str) -> bool:
    if not WECOM_WEBHOOK:
        return False
    try:
        resp = requests.post(WECOM_WEBHOOK, json={"msgtype": "text", "text": {"content": message}}, timeout=10)
        return resp.status_code == 200
    except:
        return False


def push_qmsg(message: str) -> bool:
    if not QMSG_QQ or not QMSG_KEY:
        return False
    try:
        url = f"https://qmsg.zendee.cn/send/{QMSG_KEY}"
        resp = requests.post(url, data={"msg": message, "qq": QMSG_QQ}, timeout=10)
        return resp.status_code == 200
    except:
        return False


def push_signal(symbol: str, rating: str, detail: Dict, is_long: bool) -> None:
    global SIGNAL_HISTORY
    signal_key = f"{symbol}_{rating}_{'long' if is_long else 'short'}"
    now = datetime.now()
    if signal_key in SIGNAL_HISTORY:
        last_time = SIGNAL_HISTORY[signal_key]
        if now - last_time < timedelta(minutes=CONFIG["dedup"]["minutes"]):
            return
    SIGNAL_HISTORY[signal_key] = now

    direction = "起爆" if is_long else "下杀"
    message = f"""【轴心·{direction}】{rating}级
标的：{symbol}
防守位：{detail.get('defense', 'N/A')}
进攻位：{detail.get('attack', 'N/A')}
最后防线：{detail.get('stop_loss', 'N/A')}
风险标签：{detail.get('risk_tag', '')}
路况标签：{detail.get('adx_tag', '')}
时间：{now.strftime('%Y-%m-%d %H:%M:%S')}"""

    if rating == "S":
        push_telegram(message)
        push_wecom(message)
        if not push_telegram(message) and not push_wecom(message):
            push_qmsg(message)
    elif rating == "A":
        push_telegram(message)
    elif rating == "B":
        with open("b_signals.log", "a", encoding="utf-8") as f:
            f.write(f"{now.isoformat()} | {message}\n")


def scan_and_push():
    print(f"[扫描] {datetime.now().isoformat()} 开始扫描...")
    if not VALID_PERPETUALS:
        init_valid_perpetuals()
    tickers = fetch_24hr_tickers()
    if not tickers:
        print("[扫描] 获取行情失败")
        return
    candidates = []
    for t in tickers:
        symbol = t["symbol"]
        if symbol not in VALID_PERPETUALS:
            continue
        if symbol in STABLECOINS:
            continue
        vol = float(t["quoteVolume"])
        change = float(t["priceChangePercent"])
        if vol < CONFIG["filter"]["min_volume_24h"]:
            continue
        if abs(change) > CONFIG["filter"]["max_abs_change_24h"]:
            continue
        candidates.append({
            "symbol": symbol,
            "price": float(t["lastPrice"]),
            "change": change,
            "volume": vol
        })
    print(f"[扫描] 初筛剩余 {len(candidates)} 个候选")
    for c in candidates[:30]:
        symbol = c["symbol"]
        price = c["price"]
        change = c["change"]
        klines_30m = fetch_klines(symbol, "30m", 60)
        if not klines_30m:
            continue
        klines_5m = fetch_klines(symbol, "5m", 60)
        klines_4h = fetch_klines(symbol, "4h", 30)
        klines_1d = fetch_klines(symbol, "1d", 30)
        klines_1w = fetch_klines(symbol, "1w", 60)
        is_long = change > 0
        score, detail = score_signal(
            symbol, klines_30m, klines_5m, klines_4h, klines_1d, klines_1w, c, is_long
        )
        if score == 0:
            continue
        if "central_low" in detail:
            atr = calc_atr(klines_30m["high"], klines_30m["low"], klines_30m["close"])
            detail["defense"] = round(detail["central_low"] - 0.5 * atr, 6)
            detail["stop_loss"] = round(detail["central_low"] - 1.5 * atr, 6)
            detail["attack"] = round(detail.get("central_high", price) * 1.02, 6)
        if score >= CONFIG["rating"]["s_threshold"]:
            rating = "S"
        elif score >= CONFIG["rating"]["a_threshold"]:
            rating = "A"
        elif score >= CONFIG["rating"]["b_threshold"]:
            rating = "B"
        else:
            rating = "C"
        if rating == "C":
            continue
        score, rating, adx_tag = apply_adx_filter(score, rating, klines_30m)
        detail["adx_tag"] = adx_tag
        push_signal(symbol, rating, detail, is_long)
    print(f"[扫描] 完成")


def send_heartbeat():
    now = datetime.now()
    if now.hour % CONFIG["heartbeat"]["interval_hours"] == 0 and now.minute < 30:
        push_telegram(CONFIG["heartbeat"]["message"])


if __name__ == "__main__":
    scan_and_push()
    send_heartbeat()