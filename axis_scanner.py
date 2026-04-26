#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
轴心双子 · 起爆与下杀鱼池 · 最终完整武器版 vFINAL
"""
import time, requests, smtplib, json
from email.mime.text import MIMEText
from email.header import Header
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
# ==================== 接收推送通道（三通道） ====================
WECOM_WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=0d944f97-915b-4fa0-b32b-a6f3152e3a33"
EMAIL_163_FROM = "zmxfll@163.com"
EMAIL_163_PASSWORD = "LQvNtdQL3KfL36Cx"
EMAIL_QQ_FROM = "822389158@qq.com"
EMAIL_QQ_PASSWORD = "你的QQ邮箱授权码"
EMAIL_TO = "henryford198610@gmail.com"
EMAIL_CC = "zmxfll@163.com"
# ==================== 数据抓取渠道 ====================
BINANCE_FAPI_URLS = [
    "https://fapi.binance.com",
    "https://fapi-gcp.binance.com",
    "https://fapi1.binance.com",
    "https://fapi2.binance.com",
    "https://fapi3.binance.com",
    "https://fapi4.binance.com"
]
BINANCE_API_KEY = "O7n3YEos7ukSERcRgkRLg1qN7X6gENGU0DkuCyY2oaDpdAhmZ1wtpKKlfhrN3jvo"
BINANCE_SECRET_KEY = "88TeHjwSoJfO7wCBM1Xojuf3Nilcjf1F0sXD9y0QKdu7hy3xPkEvx1LxcdNYVdOb"
COINCAP_API = "https://api.coincap.io/v2/assets"
COINGECKO_API = "https://api.coingecko.com/api/v3"
SCAN_INTERVAL = 60
PUSH_HISTORY = {}
B_LEVEL_CACHE = []
# ==================== 推送函数 ====================
def push_wecom(message: str) -> bool:
    try:
        resp = requests.post(WECOM_WEBHOOK, json={"msgtype": "text", "text": {"content": message}}, timeout=10)
        return resp.status_code == 200 and resp.json().get("errcode") == 0
    except: return False
def _send_email(smtp_server: str, port: int, user: str, password: str, subject: str, body: str) -> bool:
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = Header(subject, 'utf-8')
        msg['From'] = user
        msg['To'] = EMAIL_TO
        if EMAIL_CC: msg['Cc'] = EMAIL_CC
        server = smtplib.SMTP_SSL(smtp_server, port)
        server.login(user, password)
        server.sendmail(user, [EMAIL_TO] + ([EMAIL_CC] if EMAIL_CC else []), msg.as_string())
        server.quit()
        return True
    except: return False
def push_email_163(subject: str, body: str) -> bool:
    return _send_email("smtp.163.com", 465, EMAIL_163_FROM, EMAIL_163_PASSWORD, subject, body)
def push_email_qq(subject: str, body: str) -> bool:
    return _send_email("smtp.qq.com", 465, EMAIL_QQ_FROM, EMAIL_QQ_PASSWORD, subject, body)
def push_all(message: str, subject: str = "轴心中枢信号"):
    push_wecom(message)
    push_email_163(subject, message)
    push_email_qq(subject, message)
def push_b_level_batch():
    global B_LEVEL_CACHE
    if not B_LEVEL_CACHE: return
    batch_msg = "【轴心·B级观察鱼】30分钟汇总\n" + "\n".join(B_LEVEL_CACHE)
    push_all(batch_msg, "轴心·B级观察鱼汇总")
    B_LEVEL_CACHE.clear()
# ==================== 数据获取 ====================
def request_binance(endpoint: str, params: dict = None, timeout: int = 10):
    for base_url in BINANCE_FAPI_URLS:
        try:
            resp = requests.get(f"{base_url}{endpoint}", params=params, timeout=timeout)
            if resp.status_code == 200: return resp
        except: continue
    return None
def fetch_tickers():
    resp = request_binance("/fapi/v1/ticker/24hr", timeout=10)
    if resp:
        data = resp.json()
        print(f"[数据源] 币安成功，获取 {len(data)} 个币种")
        return data
    try:
        print("[数据源] 尝试 CoinCap...")
        resp = requests.get(COINCAP_API, timeout=15)
        if resp.status_code == 200:
            raw = resp.json().get('data', [])
            formatted = []
            for asset in raw:
                formatted.append({
                    "symbol": asset['symbol'] + 'USDT',
                    "lastPrice": asset['priceUsd'],
                    "priceChangePercent": asset['changePercent24Hr'],
                    "quoteVolume": asset['volumeUsd24Hr']
                })
            print(f"[数据源] CoinCap 成功，获取 {len(formatted)} 个币种")
            return formatted
    except Exception as e: print(f"[数据源] CoinCap 异常: {e}")
    print("[数据源] 获取行情失败")
    return []
def fetch_klines(symbol: str, interval: str = "30m", limit: int = 60):
    resp = request_binance(f"/fapi/v1/klines", params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=5)
    if resp is None: return None
    data = resp.json()
    return {
        "open": [float(d[1]) for d in data],
        "high": [float(d[2]) for d in data],
        "low": [float(d[3]) for d in data],
        "close": [float(d[4]) for d in data],
        "volume": [float(d[5]) for d in data]
    }
# ==================== 指标计算 ====================
def calc_ma(values, period):
    if len(values) < period: return sum(values) / len(values) if values else 0
    return sum(values[-period:]) / period
def calc_rsi(closes, period=14):
    if len(closes) < period + 1: return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(diff if diff > 0 else 0)
        losses.append(-diff if diff < 0 else 0)
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0: return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))
def calc_macd(closes):
    if len(closes) < 26: return 0, 0, 0
    ema12 = closes[0]; ema26 = closes[0]
    for price in closes[1:]:
        ema12 = price * 0.1538 + ema12 * 0.8462
        ema26 = price * 0.0741 + ema26 * 0.9259
    dif = ema12 - ema26; dea = dif * 0.2
    return dif, dea, (dif - dea) * 2
def calc_obv(closes, volumes):
    if len(closes) < 2: return [0]
    obv = [0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i-1]: obv.append(obv[-1] + volumes[i])
        elif closes[i] < closes[i-1]: obv.append(obv[-1] - volumes[i])
        else: obv.append(obv[-1])
    return obv
def calc_kdj(highs, lows, closes, n=9):
    if len(closes) < n: return 50, 50, 50
    low_n = min(lows[-n:]); high_n = max(highs[-n:])
    rsv = (closes[-1] - low_n) / (high_n - low_n) * 100 if high_n != low_n else 50
    k = 50 * 2/3 + rsv * 1/3; d = 50 * 2/3 + k * 1/3; j = 3 * k - 2 * d
    return k, d, j
# ==================== 生命周期评分引擎 ====================
def detect_zone(change_pct):
    if change_pct >= 100: return "ultimate_guillotine", 3.0
    if 50 <= change_pct < 100: return "counter_short", 2.0
    if 30 <= change_pct < 50: return "defense_reduce", 0.2
    if 20 <= change_pct < 30: return "demon_acceleration", 0.5
    if 10 <= change_pct < 20: return "roll_position", 0.9
    if 3 <= change_pct < 10: return "breakout_confirm", 1.0
    if -6 <= change_pct < 3: return "embryo_latent", 1.2
    if -10 <= change_pct < -6: return "scout_zone", 0.6
    return "none", 0
def get_subzone_weight(change_pct):
    if -6 <= change_pct < -3: return 1.2
    if -3 <= change_pct < 0: return 1.5
    if 0 <= change_pct < 3: return 1.0
    if 3 <= change_pct < 6: return 1.3
    return 1.0
def score_embryo_latent(ticker, klines_30m, klines_15m, klines_1h):
    score = 0; detail = {}
    change_pct = ticker.get("priceChangePercent", 0)
    closes_30m = klines_30m["close"]; volumes_30m = klines_30m["volume"]
    closes_1h = klines_1h["close"]; volumes_1h = klines_1h["volume"]
    highs_1h = klines_1h["high"]; lows_1h = klines_1h["low"]
    # 结构维（30分）
    struct_score = 0
    if len(closes_30m) >= 60:
        mid = len(closes_30m) // 2
        area1 = sum([abs(x) for x in [closes_30m[i] - closes_30m[i-1] for i in range(1, mid)]])
        area2 = sum([abs(x) for x in [closes_30m[i] - closes_30m[i-1] for i in range(mid+1, len(closes_30m))]])
        if area2 < area1 * 0.7: struct_score += 18
    if len(klines_15m.get("low", [])) >= 5:
        lows_15m = klines_15m["low"]; closes_15m = klines_15m["close"]
        if lows_15m[-3] < lows_15m[-2] and lows_15m[-3] < lows_15m[-4] and closes_15m[-1] > closes_15m[-2]:
            recent_vols = volumes_30m[-3:]
            if recent_vols and len(recent_vols) >= 2 and recent_vols[-1] > sum(recent_vols) / len(recent_vols) * 1.5: struct_score += 8
    if len(klines_15m.get("low", [])) >= 5 and struct_score < 4:
        struct_score += 4
    detail["structure"] = min(struct_score, 30); score += detail["structure"]
    # 量能维
    vol_score = 0
    avg_vol_168 = sum(volumes_1h[-168:]) / 168 if len(volumes_1h) >= 168 else sum(volumes_1h) / len(volumes_1h)
    if volumes_1h[-1] < avg_vol_168 * 0.3: vol_score += 10
    if ticker.get("turnover_rate", 5) < 5: vol_score += 5
    detail["volume"] = vol_score; score += vol_score
    # 资金维
    obv = calc_obv(closes_1h, volumes_1h)
    fund_score = 0
    if len(obv) >= 40:
        recent_low = min(obv[-20:]); prev_low = min(obv[-40:-20])
        if recent_low > prev_low: fund_score += 8
    detail["funds"] = fund_score; score += fund_score
    # 动能维
    rsi = calc_rsi(closes_1h)
    k, d, j = calc_kdj(highs_1h, lows_1h, closes_1h)
    macd_dif, macd_dea, _ = calc_macd(closes_30m)
    momentum_score = 0
    if rsi < 30: momentum_score += 7
    if k > d and k < 30 and d < 30: momentum_score += 5
    if macd_dif > macd_dea and len(closes_30m) >= 30 and min(closes_30m[-10:]) < min(closes_30m[-30:-10]): momentum_score += 5
    detail["momentum"] = momentum_score; score += momentum_score
    # 辅助共振
    extra_score = 0
    if len(obv) >= 40 and min(obv[-20:]) > min(obv[-40:-20]): extra_score += 6
    if len(volumes_1h) >= 3 and volumes_1h[-1] > volumes_1h[-2] * 1.5 and volumes_1h[-2] < volumes_1h[-3] * 0.5: extra_score += 5
    extra_score += 5 # 一目均衡简化
    extra_score += 5 # 板块联动简化
    detail["extra"] = extra_score; score += extra_score
    subzone_weight = get_subzone_weight(change_pct)
    zone, zone_weight = detect_zone(change_pct)
    final_score = int(score * subzone_weight)
    level = "A" if final_score >= 70 else "B" if final_score >= 50 else "C"
    return final_score, level, "long", detail
def score_breakout_confirm(ticker, klines_30m, klines_15m, klines_1h, klines_4h):
    score = 0; detail = {}
    closes_15m = klines_15m["close"]; volumes_15m = klines_15m["volume"]
    closes_1h = klines_1h["close"]; volumes_1h = klines_1h["volume"]
    highs_1h = klines_1h["high"]; lows_1h = klines_1h["low"]
    # 结构维（24分）
    if len(closes_15m) >= 3 and closes_15m[-1] > closes_15m[-2] > closes_15m[-3]: score += 24
    # 量能维（21分）
    avg_vol_168 = sum(volumes_1h[-168:]) / 168 if len(volumes_1h) >= 168 else sum(volumes_1h) / len(volumes_1h)
    if volumes_15m[-1] > avg_vol_168 * 1.5: score += 21
    # 动能维（23分）
    rsi = calc_rsi(closes_1h); k, d, j = calc_kdj(highs_1h, lows_1h, closes_1h)
    macd_dif, macd_dea, _ = calc_macd(closes_30m)
    macd_dif_4h, macd_dea_4h, _ = calc_macd(klines_4h.get("close", closes_1h))
    macd_dif_1h, macd_dea_1h, _ = calc_macd(closes_1h)
    if rsi < 30: score += 7
    if k > d and k < 30 and d < 30: score += 5
    if macd_dif > macd_dea: score += 5
    if (macd_dif_4h > 0 or macd_dif_4h > macd_dea_4h) and macd_dif_1h > macd_dea_1h and macd_dif > macd_dea: score += 6
    # 形态维（20分）
    if len(klines_15m.get("open", [])) >= 1:
        open_15 = klines_15m["open"][-1]; close_15 = closes_15m[-1]; high_15 = klines_15m["high"][-1]; low_15 = klines_15m["low"][-1]
        body = abs(close_15 - open_15); total = high_15 - low_15 if high_15 != low_15 else 1
        upper_wick = high_15 - max(open_15, close_15)
        if body / total >= 0.7 and upper_wick / total <= 0.1: score += 20
    # 均线维（10分）
    ma5 = calc_ma(closes_15m, 5); ma5_prev = calc_ma(closes_15m[:-1], 5)
    if closes_15m[-1] > ma5 and ma5 > ma5_prev: score += 10
    # 辅助共振（27分）
    obv = calc_obv(closes_1h, volumes_1h)
    if len(obv) >= 20 and obv[-1] > max(obv[-20:-1]): score += 6
    if len(volumes_1h) >= 3 and volumes_1h[-1] > avg_vol_168 * 1.5: score += 5
    score += 5; score += 5; score += 3; score += 3 # 一目均衡+板块联动+多空比+资金费率
    subzone_weight = get_subzone_weight(ticker.get("priceChangePercent", 0))
    final_score = int(score * subzone_weight)
    level = "A" if final_score >= 70 else "B" if final_score >= 50 else "C"
    return final_score, level, "long", detail
def score_counter_short(ticker, klines_30m, klines_15m, klines_1h):
    score = 0; detail = {}
    change_pct = ticker.get("priceChangePercent", 0)
    closes_30m = klines_30m["close"]; volumes_30m = klines_30m["volume"]
    closes_15m = klines_15m["close"]; volumes_15m = klines_15m["volume"]
    closes_1h = klines_1h["close"]; volumes_1h = klines_1h["volume"]
    highs_1h = klines_1h["high"]; lows_1h = klines_1h["low"]
    # 区间权重
    if 30 <= change_pct < 50: zone_weight = 1.5
    elif 50 <= change_pct < 100: zone_weight = 2.0
    elif change_pct >= 100: zone_weight = 3.0
    elif 20 <= change_pct < 30: zone_weight = 0.8
    else: zone_weight = 1.0
    # 量能维（25分）
    avg_vol_168 = sum(volumes_1h[-168:]) / 168 if len(volumes_1h) >= 168 else sum(volumes_1h) / len(volumes_1h)
    if volumes_1h[-1] < avg_vol_168 * 0.4: score += 10
    if volumes_1h[-1] >= avg_vol_168 * 3: score += 15
    # 结构维（38分）
    if len(closes_30m) >= 60:
        mid = len(closes_30m) // 2
        area1 = sum([abs(closes_30m[i] - closes_30m[i-1]) for i in range(1, mid)])
        area2 = sum([abs(closes_30m[i] - closes_30m[i-1]) for i in range(mid+1, len(closes_30m))])
        if area2 < area1 * 0.7: score += 18
    if len(klines_15m.get("high", [])) >= 5 and volumes_15m[-1] >= avg_vol_168 * 3:
        highs_15m = klines_15m["high"]; lows_15m = klines_15m["low"]
        if highs_15m[-1] > highs_15m[-2] * 1.05 and closes_15m[-1] < lows_15m[-2]: score += 8
    if len(klines_15m.get("high", [])) >= 5:
        highs_15m = klines_15m["high"]; lows_15m = klines_15m["low"]
        if highs_15m[-3] > highs_15m[-2] and highs_15m[-3] > highs_15m[-4] and closes_15m[-1] < closes_15m[-2]:
            recent_vols = volumes_15m[-3:]
            if recent_vols and len(recent_vols) >= 2 and recent_vols[-1] > sum(recent_vols) / len(recent_vols) * 1.3: score += 4
    ma7_30 = calc_ma(closes_30m, 7); ma7_30_prev = calc_ma(closes_30m[:-1], 7)
    if closes_30m[-1] < ma7_30 and volumes_30m[-1] > avg_vol_168 * 1.3 and ma7_30 < ma7_30_prev: score += 8
    # 资金维（8分）
    obv = calc_obv(closes_1h, volumes_1h)
    if len(obv) >= 40 and max(obv[-20:]) < max(obv[-40:-20]): score += 8
    # 动能维（21分）
    rsi = calc_rsi(closes_1h); macd_dif, macd_dea, _ = calc_macd(closes_30m)
    if rsi > 70: score += 7
    if macd_dif < macd_dea and len(closes_30m) >= 30 and max(closes_30m[-10:]) > max(closes_30m[-30:-10]): score += 14
    # 跌幅确认
    if len(closes_15m) >= 2:
        drop_15m = (closes_15m[-1] - closes_15m[-2]) / closes_15m[-2] * 100
        if 30 <= change_pct < 50 and drop_15m <= -8 and volumes_15m[-1] >= avg_vol_168 * 3: score += 10
        elif 50 <= change_pct < 100 and drop_15m <= -15 and volumes_15m[-1] >= avg_vol_168 * 5: score += 10
        elif change_pct >= 100 and drop_15m <= -5 and ticker.get("turnover_rate", 0) >= 15: score += 10
    # 辅助共振（29分）
    if len(obv) >= 40 and max(obv[-20:]) < max(obv[-40:-20]): score += 6
    if len(volumes_1h) >= 3 and volumes_1h[-1] < volumes_1h[-2] * 0.5: score += 5
    score += 5; score += 5; score += 3; score += 5 # 一目均衡+板块联动+资金费率+巨鲸
    final_score = int(score * zone_weight)
    level = "A" if final_score >= 70 else "B" if final_score >= 50 else "C"
    return final_score, level, "short", detail
# ==================== 推送分级处理 ====================
def should_push(symbol, direction):
    key = f"{symbol}_{direction}"
    now = datetime.now()
    if key in PUSH_HISTORY and (now - PUSH_HISTORY[key]).total_seconds() < 86400: return False
    PUSH_HISTORY[key] = now
    return True
def push_signal(symbol, direction, score, level, ticker):
    if not should_push(symbol, direction): return
    direction_cn = "起爆" if direction == "long" else "下杀"
    message = f"【轴心·{direction_cn}】{level}级 评分{score}\n标的：{symbol}\n涨幅：{ticker.get('priceChangePercent', 0):.1f}%\n价格：{ticker.get('lastPrice', 0):.6f}\n时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    if level == "A":
        push_all(message, f"轴心·{direction_cn} {symbol}")
    elif level == "B":
        B_LEVEL_CACHE.append(message)
# ==================== 主扫描 ====================
def scan():
    global B_LEVEL_CACHE
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始扫描...")
    tickers = fetch_tickers()
    if not tickers: return
    for t in tickers[:200]:
        symbol = t["symbol"]
        if not symbol.endswith("USDT"): continue
        if any(x in symbol for x in ["UP", "DOWN", "BULL", "BEAR", "USDC", "USDP", "TUSD"]): continue
        klines_30m = fetch_klines(symbol, "30m", 60)
        klines_15m = fetch_klines(symbol, "15m", 60)
        klines_1h = fetch_klines(symbol, "1h", 168)
        klines_4h = fetch_klines(symbol, "4h", 60)
        if not klines_30m or not klines_15m or not klines_1h: continue
        if not klines_4h: klines_4h = klines_1h
        ticker = {
            "lastPrice": float(t["lastPrice"]),
            "priceChangePercent": float(t["priceChangePercent"]),
            "quoteVolume": float(t["quoteVolume"]),
            "turnover_rate": float(t.get("volume", 0)) / float(t.get("quoteVolume", 1)) * 100 if float(t.get("quoteVolume", 0)) > 0 else 0
        }
        if ticker["quoteVolume"] < 30000: continue
        change_pct = ticker["priceChangePercent"]
        zone, _ = detect_zone(change_pct)
        if zone in ["embryo_latent", "scout_zone"]:
            score, level, direction, _ = score_embryo_latent(ticker, klines_30m, klines_15m, klines_1h)
        elif zone == "breakout_confirm":
            score, level, direction, _ = score_breakout_confirm(ticker, klines_30m, klines_15m, klines_1h, klines_4h)
        elif zone in ["counter_short", "ultimate_guillotine", "defense_reduce", "demon_acceleration"]:
            score, level, direction, _ = score_counter_short(ticker, klines_30m, klines_15m, klines_1h)
        else:
            continue
        if score >= 50:
            push_signal(symbol, direction, score, level, ticker)
            print(f"[推送] {symbol} {direction} {level}级 评分{score}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 扫描完成")
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        push_all("✅ 轴心中枢 · 测试消息", "轴心测试")
        print("测试推送已发送")
    elif len(sys.argv) > 1 and sys.argv[1] == "--loop":
        last_b_push = datetime.now()
        while True:
            scan()
            if (datetime.now() - last_b_push).total_seconds() >= 1800:
                push_b_level_batch()
                last_b_push = datetime.now()
            time.sleep(SCAN_INTERVAL)
    else:
        scan()
      def main_handler(event, context):
    scan()
    return "扫描完成"

