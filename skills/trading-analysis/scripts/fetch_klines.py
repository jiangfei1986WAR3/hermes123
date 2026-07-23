#!/usr/bin/env python3
"""
fetch_klines.py - 为 trading-analysis 拉取多周期K线数据并计算技术指标

用法：
  python3 fetch_klines.py --symbols KAITOUSDT,ADAUSDT --timeframes 15m,1h,4h,1d --bars 100
  python3 fetch_klines.py --symbols KAITOUSDT --json   # 输出JSON（供程序消费）

输出：
  默认：人类可读的中文分析报告（直接贴给 trading-analysis 用）
  --json：结构化JSON（供其他脚本消费）

数据源：Binance 公开 API（无需登录）
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

# ============================================================
# 配置
# ============================================================
BASE_URL = "https://fapi.binance.com"
DEFAULT_TIMEFRAMES = ["15m", "1h", "4h", "1d"]
DEFAULT_BARS = 100
MAX_RETRIES = 3
RETRY_DELAY = 2  # 秒
REQUEST_TIMEOUT = 30  # 秒

# 周期中文名
TF_NAMES = {
    "15m": "15分钟",
    "1h": "1小时",
    "4h": "4小时",
    "1d": "日线",
}


# ============================================================
# API 请求
# ============================================================
def api_get(path: str, params: dict = None, retries: int = MAX_RETRIES) -> dict:
    """带重试的 GET 请求"""
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{BASE_URL}{path}?{query}"
    else:
        url = f"{BASE_URL}{path}"

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, urllib.error.HTTPError, Exception) as e:
            if attempt < retries - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))
            else:
                raise RuntimeError(f"API 请求失败 ({retries}次重试后): {url} -> {e}")


def fetch_klines(symbol: str, interval: str, limit: int = DEFAULT_BARS) -> list:
    """拉取K线数据，返回 [{open_time, open, high, low, close, volume, quote_volume, taker_buy_volume}, ...]"""
    data = api_get("/fapi/v1/klines", {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    })
    candles = []
    for k in data:
        candles.append({
            "open_time": k[0],
            "open": float(k[1]),
            "high": float(k[2]),
            "low": float(k[3]),
            "close": float(k[4]),
            "volume": float(k[5]),
            "quote_volume": float(k[7]),
            "taker_buy_volume": float(k[9]),
        })
    return candles


def fetch_funding_rate(symbol: str) -> dict:
    """拉取最新资金费率"""
    try:
        data = api_get("/fapi/v1/premiumIndex", {"symbol": symbol})
        return {
            "mark_price": float(data.get("markPrice", 0)),
            "funding_rate": float(data.get("lastFundingRate", 0)),
            "next_funding_time": data.get("nextFundingTime", 0),
        }
    except Exception:
        return {"mark_price": 0, "funding_rate": 0, "next_funding_time": 0}


def fetch_open_interest(symbol: str) -> dict:
    """拉取持仓量"""
    try:
        data = api_get("/fapi/v1/openInterest", {"symbol": symbol})
        return {"open_interest": float(data.get("openInterest", 0))}
    except Exception:
        return {"open_interest": 0}


def fetch_ticker_24h(symbol: str) -> dict:
    """拉取24h行情"""
    try:
        data = api_get("/fapi/v1/ticker/24hr", {"symbol": symbol})
        return {
            "last_price": float(data.get("lastPrice", 0)),
            "price_change_pct": float(data.get("priceChangePercent", 0)),
            "high_24h": float(data.get("highPrice", 0)),
            "low_24h": float(data.get("lowPrice", 0)),
            "quote_volume_24h": float(data.get("quoteVolume", 0)),
        }
    except Exception:
        return {"last_price": 0, "price_change_pct": 0, "high_24h": 0, "low_24h": 0, "quote_volume_24h": 0}


# ============================================================
# 技术指标计算
# ============================================================
def calc_ma(closes: list, period: int) -> list:
    """简单移动平均线"""
    result = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        result[i] = sum(closes[i - period + 1:i + 1]) / period
    return result


def calc_ema(closes: list, period: int) -> list:
    """指数移动平均线"""
    result = [None] * len(closes)
    multiplier = 2 / (period + 1)
    # 用第一个值初始化
    result[0] = closes[0]
    for i in range(1, len(closes)):
        result[i] = closes[i] * multiplier + result[i - 1] * (1 - multiplier)
    return result


def calc_macd(closes: list, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    """MACD指标"""
    ema_fast = calc_ema(closes, fast)
    ema_slow = calc_ema(closes, slow)
    dif = [None] * len(closes)
    for i in range(len(closes)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            dif[i] = ema_fast[i] - ema_slow[i]

    # DEA = DIF 的 EMA
    dif_values = [d if d is not None else 0 for d in dif]
    dea = calc_ema(dif_values, signal)

    # MACD柱 = (DIF - DEA) * 2
    macd_hist = [None] * len(closes)
    for i in range(len(closes)):
        if dif[i] is not None and dea[i] is not None:
            macd_hist[i] = (dif[i] - dea[i]) * 2

    return {"dif": dif, "dea": dea, "macd_hist": macd_hist}


def calc_rsi(closes: list, period: int = 14) -> list:
    """RSI指标"""
    result = [None] * len(closes)
    if len(closes) < period + 1:
        return result

    gains = []
    losses = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(closes)):
        if i == period:
            avg_gain = sum(gains[:period]) / period
            avg_loss = sum(losses[:period]) / period
        else:
            avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period

        if avg_loss == 0:
            result[i] = 100
        else:
            rs = avg_gain / avg_loss
            result[i] = 100 - (100 / (1 + rs))

    return result


def calc_bollinger(closes: list, period: int = 20, std_mult: float = 2.0) -> dict:
    """布林带"""
    upper = [None] * len(closes)
    middle = [None] * len(closes)
    lower = [None] * len(closes)

    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1:i + 1]
        avg = sum(window) / period
        variance = sum((x - avg) ** 2 for x in window) / period
        std = variance ** 0.5
        middle[i] = avg
        upper[i] = avg + std_mult * std
        lower[i] = avg - std_mult * std

    return {"upper": upper, "middle": middle, "lower": lower}


def calc_atr(candles: list, period: int = 14) -> list:
    """ATR（平均真实波幅）"""
    result = [None] * len(candles)
    if len(candles) < period + 1:
        return result

    trs = []
    for i in range(1, len(candles)):
        high = candles[i]["high"]
        low = candles[i]["low"]
        prev_close = candles[i - 1]["close"]
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)

    # 第一个ATR用简单平均
    atr = sum(trs[:period]) / period
    result[period] = atr
    for i in range(period + 1, len(candles)):
        atr = (atr * (period - 1) + trs[i - 1]) / period
        result[i] = atr

    return result


def find_support_resistance(candles: list, lookback: int = 20) -> dict:
    """找近期关键支撑/阻力位（基于高低点）"""
    recent = candles[-lookback:] if len(candles) >= lookback else candles

    highs = [c["high"] for c in recent]
    lows = [c["low"] for c in recent]

    # 近期最高/最低
    period_high = max(highs)
    period_low = min(lows)

    # 找局部高点（比前后都高）
    resistance_levels = []
    support_levels = []
    for i in range(1, len(recent) - 1):
        if recent[i]["high"] >= recent[i - 1]["high"] and recent[i]["high"] >= recent[i + 1]["high"]:
            resistance_levels.append(recent[i]["high"])
        if recent[i]["low"] <= recent[i - 1]["low"] and recent[i]["low"] <= recent[i + 1]["low"]:
            support_levels.append(recent[i]["low"])

    # 去重（合并接近的价位，差距<0.3%视为同一位）
    def merge_levels(levels):
        if not levels:
            return []
        levels = sorted(set(levels))
        merged = [levels[0]]
        for lv in levels[1:]:
            if abs(lv - merged[-1]) / merged[-1] > 0.003:
                merged.append(lv)
            else:
                # 取平均
                merged[-1] = (merged[-1] + lv) / 2
        return merged

    return {
        "period_high": period_high,
        "period_low": period_low,
        "resistance_levels": merge_levels(resistance_levels),
        "support_levels": merge_levels(support_levels),
    }


def analyze_volume(candles: list, lookback: int = 20) -> dict:
    """量价分析：最近几根K线的量能特征"""
    if len(candles) < lookback + 1:
        return {"note": "数据不足"}

    recent = candles[-lookback:]
    volumes = [c["volume"] for c in recent]
    avg_volume = sum(volumes) / len(volumes)

    # 最近3根K线的量比
    last3 = candles[-3:]
    vol_ratios = []
    for c in last3:
        ratio = c["volume"] / avg_volume if avg_volume > 0 else 0
        direction = "涨" if c["close"] >= c["open"] else "跌"
        vol_ratios.append({
            "ratio": round(ratio, 2),
            "direction": direction,
            "body_pct": round(abs(c["close"] - c["open"]) / c["open"] * 100, 3) if c["open"] > 0 else 0,
        })

    # 主动买盘占比（最近lookback根）
    total_taker_buy = sum(c["taker_buy_volume"] for c in recent)
    total_volume = sum(c["volume"] for c in recent)
    taker_buy_ratio = total_taker_buy / total_volume if total_volume > 0 else 0

    # 放量K线标注（量比>1.5的K线）
    high_volume_candles = []
    for i, c in enumerate(recent):
        ratio = c["volume"] / avg_volume if avg_volume > 0 else 0
        if ratio > 1.5:
            direction = "阳线" if c["close"] >= c["open"] else "阴线"
            high_volume_candles.append({
                "index": i,
                "ratio": round(ratio, 2),
                "direction": direction,
                "close": c["close"],
            })

    return {
        "avg_volume": avg_volume,
        "last3_vol_ratios": vol_ratios,
        "taker_buy_ratio": round(taker_buy_ratio, 4),
        "high_volume_candles": high_volume_candles[-5:],  # 最近5根放量的
    }


def detect_candle_patterns(candles: list, lookback: int = 5) -> list:
    """检测最近几根K线的形态"""
    patterns = []
    recent = candles[-lookback:] if len(candles) >= lookback else candles

    for i, c in enumerate(recent):
        body = abs(c["close"] - c["open"])
        full_range = c["high"] - c["low"]
        if full_range == 0:
            continue

        upper_wick = c["high"] - max(c["close"], c["open"])
        lower_wick = min(c["close"], c["open"]) - c["low"]
        body_ratio = body / full_range

        idx = len(candles) - lookback + i if len(candles) >= lookback else i

        # 十字星：实体<10%
        if body_ratio < 0.1:
            patterns.append({"index": idx, "pattern": "十字星", "close": c["close"]})
        # 锤子线：下影线>实体2倍，上影线短
        elif lower_wick > body * 2 and upper_wick < body * 0.5:
            patterns.append({"index": idx, "pattern": "锤子线", "close": c["close"]})
        # 上吊线/射击之星：上影线>实体2倍，下影线短
        elif upper_wick > body * 2 and lower_wick < body * 0.5:
            patterns.append({"index": idx, "pattern": "射击之星" if c["close"] < c["open"] else "上吊线", "close": c["close"]})
        # 大阳线/大阴线：实体>70%
        elif body_ratio > 0.7:
            direction = "大阳线" if c["close"] > c["open"] else "大阴线"
            patterns.append({"index": idx, "pattern": direction, "close": c["close"]})

    # 吞没形态（最后两根）
    if len(recent) >= 2:
        prev = recent[-2]
        curr = recent[-1]
        prev_body = prev["close"] - prev["open"]
        curr_body = curr["close"] - curr["open"]
        if prev_body < 0 and curr_body > 0 and curr["close"] > prev["open"] and curr["open"] < prev["close"]:
            patterns.append({"index": len(candles) - 1, "pattern": "看涨吞没", "close": curr["close"]})
        elif prev_body > 0 and curr_body < 0 and curr["close"] < prev["open"] and curr["open"] > prev["close"]:
            patterns.append({"index": len(candles) - 1, "pattern": "看跌吞没", "close": curr["close"]})

    return patterns


# ============================================================
# 单周期分析
# ============================================================
def analyze_timeframe(symbol: str, interval: str, candles: list) -> dict:
    """对单个周期的K线数据做完整技术分析"""
    closes = [c["close"] for c in candles]
    current_price = closes[-1]

    # 均线
    ma7 = calc_ma(closes, 7)
    ma25 = calc_ma(closes, 25)
    ma99 = calc_ma(closes, 99) if len(closes) >= 99 else [None] * len(closes)

    # MACD
    macd = calc_macd(closes)

    # RSI
    rsi = calc_rsi(closes)

    # 布林带
    boll = calc_bollinger(closes)

    # ATR
    atr = calc_atr(candles)

    # 支撑阻力
    sr = find_support_resistance(candles)

    # 量价分析
    vol = analyze_volume(candles)

    # K线形态
    patterns = detect_candle_patterns(candles)

    # 均线排列判断
    ma_state = "数据不足"
    if ma7[-1] is not None and ma25[-1] is not None:
        if current_price > ma7[-1] > ma25[-1]:
            ma_state = "多头排列（价格>MA7>MA25）"
        elif current_price < ma7[-1] < ma25[-1]:
            ma_state = "空头排列（价格<MA7<MA25）"
        elif ma7[-1] > ma25[-1]:
            ma_state = "MA7>MA25（偏多但价格在均线间）"
        else:
            ma_state = "MA7<MA25（偏空但价格在均线间）"

    # MACD状态
    macd_state = "数据不足"
    if macd["dif"][-1] is not None and macd["dea"][-1] is not None:
        dif = macd["dif"][-1]
        dea = macd["dea"][-1]
        hist = macd["macd_hist"][-1]
        prev_hist = macd["macd_hist"][-2] if len(macd["macd_hist"]) >= 2 and macd["macd_hist"][-2] is not None else 0

        if dif > dea and hist > 0:
            if prev_hist is not None and hist > prev_hist:
                macd_state = "金叉且红柱放大（多头动能增强）"
            else:
                macd_state = "金叉但红柱缩小（多头动能减弱）"
        elif dif < dea and hist < 0:
            if prev_hist is not None and hist < prev_hist:
                macd_state = "死叉且绿柱放大（空头动能增强）"
            else:
                macd_state = "死叉但绿柱缩小（空头动能减弱）"
        elif dif > dea:
            macd_state = "DIF>DEA（偏多）"
        else:
            macd_state = "DIF<DEA（偏空）"

    # RSI状态
    rsi_state = "数据不足"
    if rsi[-1] is not None:
        rsi_val = rsi[-1]
        if rsi_val > 70:
            rsi_state = f"超买({rsi_val:.1f})"
        elif rsi_val < 30:
            rsi_state = f"超卖({rsi_val:.1f})"
        elif rsi_val > 55:
            rsi_state = f"偏强({rsi_val:.1f})"
        elif rsi_val < 45:
            rsi_state = f"偏弱({rsi_val:.1f})"
        else:
            rsi_state = f"中性({rsi_val:.1f})"

    # 布林带位置
    boll_state = "数据不足"
    if boll["upper"][-1] is not None:
        upper = boll["upper"][-1]
        middle = boll["middle"][-1]
        lower = boll["lower"][-1]
        if current_price >= upper:
            boll_state = "触及/突破上轨（强势或超买）"
        elif current_price <= lower:
            boll_state = "触及/跌破下轨（弱势或超卖）"
        elif current_price > middle:
            boll_state = "中轨上方（偏强）"
        else:
            boll_state = "中轨下方（偏弱）"

    return {
        "interval": interval,
        "interval_cn": TF_NAMES.get(interval, interval),
        "candle_count": len(candles),
        "current_price": current_price,
        "ma7": round(ma7[-1], 8) if ma7[-1] is not None else None,
        "ma25": round(ma25[-1], 8) if ma25[-1] is not None else None,
        "ma99": round(ma99[-1], 8) if ma99[-1] is not None else None,
        "ma_state": ma_state,
        "macd_dif": round(macd["dif"][-1], 8) if macd["dif"][-1] is not None else None,
        "macd_dea": round(macd["dea"][-1], 8) if macd["dea"][-1] is not None else None,
        "macd_hist": round(macd["macd_hist"][-1], 8) if macd["macd_hist"][-1] is not None else None,
        "macd_state": macd_state,
        "rsi": round(rsi[-1], 2) if rsi[-1] is not None else None,
        "rsi_state": rsi_state,
        "boll_upper": round(boll["upper"][-1], 8) if boll["upper"][-1] is not None else None,
        "boll_middle": round(boll["middle"][-1], 8) if boll["middle"][-1] is not None else None,
        "boll_lower": round(boll["lower"][-1], 8) if boll["lower"][-1] is not None else None,
        "boll_state": boll_state,
        "atr": round(atr[-1], 8) if atr[-1] is not None else None,
        "support_resistance": sr,
        "volume_analysis": vol,
        "candle_patterns": patterns,
        # 最近5根K线原始数据（供深度分析）
        "recent_candles": [
            {
                "time": datetime.fromtimestamp(
                    c["open_time"] / 1000, tz=timezone(timedelta(hours=8))
                ).strftime("%m-%d %H:%M"),
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "volume": round(c["volume"], 2),
                "taker_buy_vol": round(c["taker_buy_volume"], 2),
            }
            for c in candles[-5:]
        ],
    }


# ============================================================
# 完整分析（所有周期）
# ============================================================
def full_analysis(symbol: str, timeframes: list, bars: int) -> dict:
    """对一个币拉取所有周期数据并分析"""
    result = {
        "symbol": symbol,
        "analysis_time": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),
        "timeframes": {},
    }

    # 24h行情
    ticker = fetch_ticker_24h(symbol)
    result["ticker_24h"] = ticker

    # 资金费率
    funding = fetch_funding_rate(symbol)
    result["funding"] = funding

    # 持仓量
    oi = fetch_open_interest(symbol)
    result["open_interest"] = oi

    # 各周期K线
    for tf in timeframes:
        try:
            candles = fetch_klines(symbol, tf, bars)
            result["timeframes"][tf] = analyze_timeframe(symbol, tf, candles)
        except Exception as e:
            result["timeframes"][tf] = {"error": str(e)}

    return result


# ============================================================
# 人类可读输出
# ============================================================
def format_report(data: dict) -> str:
    """格式化为人类可读的中文报告"""
    lines = []
    sym = data["symbol"]
    ticker = data.get("ticker_24h", {})
    funding = data.get("funding", {})
    oi = data.get("open_interest", {})

    lines.append(f"{'='*60}")
    lines.append(f"  {sym} 多周期技术分析数据")
    lines.append(f"  分析时间: {data['analysis_time']} (UTC+8)")
    lines.append(f"{'='*60}")
    lines.append("")

    # 基础信息
    lines.append(f"【基础信息】")
    lines.append(f"  现价: {ticker.get('last_price', 'N/A')}")
    lines.append(f"  24h涨跌: {ticker.get('price_change_pct', 'N/A')}%")
    lines.append(f"  24h最高/最低: {ticker.get('high_24h', 'N/A')} / {ticker.get('low_24h', 'N/A')}")
    lines.append(f"  24h成交额: {ticker.get('quote_volume_24h', 0):,.0f} USDT")
    lines.append(f"  标记价格: {funding.get('mark_price', 'N/A')}")
    lines.append(f"  资金费率: {funding.get('funding_rate', 'N/A')}")
    lines.append(f"  持仓量(OI): {oi.get('open_interest', 'N/A')}")
    lines.append("")

    # 各周期
    for tf_key, tf_data in data.get("timeframes", {}).items():
        if "error" in tf_data:
            lines.append(f"【{TF_NAMES.get(tf_key, tf_key)}】❌ 数据拉取失败: {tf_data['error']}")
            lines.append("")
            continue

        lines.append(f"【{tf_data['interval_cn']}】({tf_data['candle_count']}根K线)")
        lines.append(f"  均线: MA7={tf_data['ma7']} | MA25={tf_data['ma25']} | MA99={tf_data['ma99']}")
        lines.append(f"  均线状态: {tf_data['ma_state']}")
        lines.append(f"  MACD: DIF={tf_data['macd_dif']} | DEA={tf_data['macd_dea']} | 柱={tf_data['macd_hist']}")
        lines.append(f"  MACD状态: {tf_data['macd_state']}")
        lines.append(f"  RSI(14): {tf_data['rsi']} → {tf_data['rsi_state']}")
        lines.append(f"  布林带: 上={tf_data['boll_upper']} | 中={tf_data['boll_middle']} | 下={tf_data['boll_lower']}")
        lines.append(f"  布林状态: {tf_data['boll_state']}")
        lines.append(f"  ATR(14): {tf_data['atr']}")

        # 支撑阻力
        sr = tf_data.get("support_resistance", {})
        lines.append(f"  区间高/低: {sr.get('period_high', 'N/A')} / {sr.get('period_low', 'N/A')}")
        if sr.get("resistance_levels"):
            lines.append(f"  阻力位: {', '.join(str(x) for x in sr['resistance_levels'])}")
        if sr.get("support_levels"):
            lines.append(f"  支撑位: {', '.join(str(x) for x in sr['support_levels'])}")

        # 量价
        vol = tf_data.get("volume_analysis", {})
        if vol.get("last3_vol_ratios"):
            vol_strs = [f"{v['ratio']}x{v['direction']}" for v in vol["last3_vol_ratios"]]
            lines.append(f"  最近3根量比: {' | '.join(vol_strs)}")
        lines.append(f"  主动买盘占比: {vol.get('taker_buy_ratio', 'N/A')}")
        if vol.get("high_volume_candles"):
            hv_strs = [f"#{c['index']}({c['ratio']}x{c['direction']})" for c in vol["high_volume_candles"]]
            lines.append(f"  放量K线: {', '.join(hv_strs)}")

        # K线形态
        if tf_data.get("candle_patterns"):
            pat_strs = [f"#{p['index']}:{p['pattern']}" for p in tf_data["candle_patterns"]]
            lines.append(f"  K线形态: {', '.join(pat_strs)}")

        # 最近5根K线
        lines.append(f"  最近5根K线:")
        for c in tf_data.get("recent_candles", []):
            direction = "阳" if c["close"] >= c["open"] else "阴"
            lines.append(f"    {c['time']} {direction} O={c['open']} H={c['high']} L={c['low']} C={c['close']} V={c['volume']}")

        lines.append("")

    return "\n".join(lines)


# ============================================================
# 主程序
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="拉取多周期K线数据并计算技术指标")
    parser.add_argument("--symbols", required=True, help="交易对，逗号分隔，如 KAITOUSDT,ADAUSDT")
    parser.add_argument("--timeframes", default=",".join(DEFAULT_TIMEFRAMES),
                        help=f"周期，逗号分隔（默认: {','.join(DEFAULT_TIMEFRAMES)}）")
    parser.add_argument("--bars", type=int, default=DEFAULT_BARS,
                        help=f"每个周期拉取的K线数量（默认: {DEFAULT_BARS}）")
    parser.add_argument("--json", action="store_true", help="输出JSON格式（默认输出人类可读报告）")
    parser.add_argument("--out", help="保存JSON到文件（仅--json模式有效）")

    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]

    all_results = []
    for symbol in symbols:
        print(f"正在分析 {symbol}...", file=sys.stderr)
        try:
            result = full_analysis(symbol, timeframes, args.bars)
            all_results.append(result)
        except Exception as e:
            print(f"❌ {symbol} 分析失败: {e}", file=sys.stderr)
            all_results.append({"symbol": symbol, "error": str(e)})

    if args.json:
        output = json.dumps(all_results, indent=2, ensure_ascii=False)
        if args.out:
            with open(args.out, "w") as f:
                f.write(output)
            print(f"✅ JSON 已保存到 {args.out}", file=sys.stderr)
        else:
            print(output)
    else:
        for result in all_results:
            if "error" in result:
                print(f"\n❌ {result['symbol']} 分析失败: {result['error']}")
            else:
                print(format_report(result))


if __name__ == "__main__":
    main()
