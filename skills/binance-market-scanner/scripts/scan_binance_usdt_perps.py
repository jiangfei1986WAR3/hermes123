#!/usr/bin/env python3
"""Scan Binance USDT perpetual futures and save ranked setup reports."""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_URL = "https://fapi.binance.com"
DEFAULT_OUT_DIR = "/root/Documents/trae_projects/zhuandaqian/market-scans"


def api_get(
    path: str,
    params: dict[str, Any] | None = None,
    timeout: int = 20,
    retries: int = 2,
    retry_sleep: float = 1.0,
) -> Any:
    query = ""
    if params:
        query = "?" + urllib.parse.urlencode(params)
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            BASE_URL + path + query,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - retry public market endpoints.
            last_exc = exc
            if attempt >= retries:
                break
            time.sleep(retry_sleep * (attempt + 1))
    raise last_exc or RuntimeError("request failed")


def avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def round_float(value: float, digits: int = 8) -> float:
    if not math.isfinite(value):
        return 0.0
    return round(value, digits)


@dataclass
class KlineRow:
    open_time: int
    close_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    taker_buy_quote: float


def parse_klines(raw: list[list[Any]], drop_unclosed: bool = True) -> list[KlineRow]:
    rows = [
        KlineRow(
            open_time=int(row[0]),
            close_time=int(row[6]),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
            quote_volume=float(row[7]),
            taker_buy_quote=float(row[10]),
        )
        for row in raw
    ]
    # Binance klines 最后一根永远是进行中的未收盘K线，其成交量/高低都是不完整数据。
    # 剔除后所有指标基于已收盘K线计算，消除扫描时刻对 volRatio 等指标的系统性污染。
    if drop_unclosed and rows and rows[-1].close_time >= int(time.time() * 1000):
        rows = rows[:-1]
    return rows


def timeframe_stats(raw: list[list[Any]]) -> dict[str, Any]:
    rows = parse_klines(raw)
    bars = len(rows)
    # 数据不足时静默降级是严重隐患：MA99 变 MA30、prev20 变 prev4，新币极易被误判突破。
    # 100 根是 MA99 的最低要求（99根均线+1根当前），不足则标记 insufficient 由调用方跳过。
    if bars < 100:
        return {"dataQuality": "insufficient", "bars": bars}
    last = rows[-1]
    prev20 = rows[-21:-1]
    last20 = rows[-20:]
    recent_high = max(row.high for row in prev20)
    recent_low = min(row.low for row in prev20)
    avg_vol20 = max(avg([row.volume for row in prev20]), 1e-12)
    avg_qvol20 = max(avg([row.quote_volume for row in prev20]), 1e-12)
    quote_sum20 = max(sum(row.quote_volume for row in last20), 1e-12)
    buy_quote_sum20 = sum(row.taker_buy_quote for row in last20)
    range_position = (
        (last.close - recent_low) / (recent_high - recent_low)
        if recent_high > recent_low
        else 0.5
    )
    atr_rows = rows[-15:]
    true_ranges: list[float] = []
    for prev, cur in zip(atr_rows, atr_rows[1:]):
        true_ranges.append(
            max(
                cur.high - cur.low,
                abs(cur.high - prev.close),
                abs(cur.low - prev.close),
            )
        )
    atr = avg(true_ranges)
    return {
        "dataQuality": "ok",
        "bars": bars,
        "close": round_float(last.close),
        "high": round_float(last.high),
        "low": round_float(last.low),
        "ma7": round_float(avg([row.close for row in rows[-7:]])),
        "ma25": round_float(avg([row.close for row in rows[-25:]])),
        "ma99": round_float(avg([row.close for row in rows[-99:]])),
        "volRatio": round_float(last.volume / avg_vol20, 2),
        "quoteVolRatio": round_float(last.quote_volume / avg_qvol20, 2),
        "takerBuyRatio20": round_float(buy_quote_sum20 / quote_sum20, 3),
        "recent20High": round_float(recent_high),
        "recent20Low": round_float(recent_low),
        "rangePosition": round_float(range_position, 3),
        "atrPct": round_float((atr / max(last.close, 1e-12)) * 100, 2),
    }


def score_long(item: dict[str, Any]) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []
    warnings: list[str] = []
    d = item["1d"]
    h4 = item["4h"]
    h1 = item["1h"]
    m15 = item["15m"]

    if d["close"] > d["ma7"] > d["ma25"]:
        score += 18
        reasons.append("日线多头排列")
    elif d["close"] > d["ma7"]:
        score += 10
        reasons.append("日线在MA7上方")

    if h4["close"] > h4["ma7"] > h4["ma25"]:
        score += 18
        reasons.append("4H趋势偏多")
    elif h4["close"] > h4["ma25"]:
        score += 10
        reasons.append("4H仍在MA25上方")

    if h1["close"] > h1["ma7"]:
        score += 10
        reasons.append("1H站上MA7")
    else:
        warnings.append("1H未站上短均线")

    if m15["close"] > m15["ma7"]:
        score += 8
        reasons.append("15m短线转强")

    if h1["close"] > h1["recent20High"] and h1["volRatio"] >= 1.3:
        score += 18
        reasons.append("1H放量突破20根高点")
    elif h1["rangePosition"] >= 0.75 and h1["volRatio"] >= 1.0:
        score += 8
        reasons.append("1H接近区间上沿且量能不弱")

    # P2-9 注：突破(volRatio>=1.3)与回踩(volRatio<=0.9)由 volRatio 阈值保证互斥，
    # 不可能同时命中。若未来调整阈值须重新验证此约束。
    near_h1_ma25 = abs((h1["close"] - h1["ma25"]) / max(h1["close"], 1e-12)) <= 0.012
    # 下限 0.5 防止零成交量/极低流动性被误判为"缩量"（P0-3 修复）
    if near_h1_ma25 and 0.5 <= h1["volRatio"] <= 0.9 and h4["close"] > h4["ma25"]:
        score += 14
        reasons.append("接近1H MA25缩量回踩")

    if m15["volRatio"] >= 1.2 and m15["takerBuyRatio20"] >= 0.52:
        score += 8
        reasons.append("15m主动买盘/量能改善")

    if abs(item["funding"]) < 0.0003:
        score += 6
        reasons.append("资金费率不过热")
    else:
        warnings.append("资金费率偏极端")

    if item["changePct"] > 18:
        warnings.append("24h涨幅过大，追高风险")
    if h1["volRatio"] >= 1.5 and h1["close"] < h1["ma7"]:
        warnings.append("放量但未收复短均线，可能分歧/出货")

    return {"score": min(score, 100), "reasons": reasons, "warnings": warnings}


def score_short(item: dict[str, Any]) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []
    warnings: list[str] = []
    d = item["1d"]
    h4 = item["4h"]
    h1 = item["1h"]
    m15 = item["15m"]

    if d["close"] < d["ma7"] < d["ma25"]:
        score += 18
        reasons.append("日线空头排列")
    elif d["close"] < d["ma25"]:
        score += 10
        reasons.append("日线弱于MA25")

    if h4["close"] < h4["ma7"] < h4["ma25"]:
        score += 18
        reasons.append("4H趋势偏空")
    elif h4["close"] < h4["ma25"]:
        score += 10
        reasons.append("4H弱于MA25")

    if h1["close"] < h1["ma7"]:
        score += 10
        reasons.append("1H在MA7下方")
    if m15["close"] < m15["ma7"]:
        score += 8
        reasons.append("15m短线偏弱")

    if h1["close"] < h1["recent20Low"] and h1["volRatio"] >= 1.3:
        score += 18
        reasons.append("1H放量跌破20根低点")
    elif h1["rangePosition"] <= 0.25 and h1["volRatio"] >= 1.0:
        score += 8
        reasons.append("1H贴近区间下沿且量能不弱")

    if m15["volRatio"] >= 1.2 and m15["takerBuyRatio20"] <= 0.48:
        score += 8
        reasons.append("15m主动卖压较强")

    if abs(item["funding"]) < 0.0003:
        score += 6
        reasons.append("资金费率不过热")
    else:
        warnings.append("资金费率偏极端")

    if item["changePct"] < -18:
        warnings.append("24h跌幅过大，追空防反抽")

    return {"score": min(score, 100), "reasons": reasons, "warnings": warnings}


def classify(long_score: int, short_score: int, ambiguous_gap: int = 8) -> str:
    # 多空拉锯：双方都强且差距小，不该进场（P1-5 修复：消除先判long的顺序偏置）
    if (
        abs(long_score - short_score) <= ambiguous_gap
        and max(long_score, short_score) >= 46
    ):
        return "AMBIGUOUS"
    if long_score > short_score:
        if long_score >= 60:
            return "LONG_TRIGGER_OR_CLOSE"
        if long_score >= 46:
            return "LONG_WATCH"
    else:
        if short_score >= 60:
            return "SHORT_TRIGGER_OR_CLOSE"
        if short_score >= 46:
            return "SHORT_WATCH"
    return "NEUTRAL"


def build_market_filter(results: list[dict[str, Any]]) -> dict[str, Any]:
    majors = {item["symbol"]: item for item in results if item["symbol"] in {"BTCUSDT", "ETHUSDT"}}
    # P1-6 修复：主流币缺失时保守封锁，不静默放行
    missing = [s for s in ("BTCUSDT", "ETHUSDT") if s not in majors]
    if missing:
        return {
            "longOk": False,
            "shortOk": False,
            "strength": None,
            "notes": [f"主流币数据缺失，保守封锁: {', '.join(missing)}"],
        }
    weak = 0
    strong = 0
    notes: list[str] = []
    for symbol in ("BTCUSDT", "ETHUSDT"):
        item = majors[symbol]
        h1 = item["1h"]
        h4 = item["4h"]
        # 数据不足的主流币与缺失同等对待：保守封锁（P1-6 补修）
        if h1.get("dataQuality") != "ok" or h4.get("dataQuality") != "ok":
            return {
                "longOk": False,
                "shortOk": False,
                "strength": None,
                "notes": [f"{symbol} 数据不足，保守封锁"],
            }
        if h1["close"] < h1["ma25"] and h4["close"] < h4["ma25"]:
            weak += 1
            notes.append(f"{symbol} weak below 1h/4h MA25")
        if h1["close"] > h1["ma25"] and h4["close"] > h4["ma25"]:
            strong += 1
            notes.append(f"{symbol} strong above 1h/4h MA25")
    # strength: -1.0(全弱) ~ +1.0(全强)，连续值供后续加权使用
    strength = (strong - weak) / 2.0
    return {
        "longOk": weak < 2,
        "shortOk": strong < 2,
        "strength": round_float(strength, 2),
        "notes": notes or ["BTC/ETH filter neutral"],
    }


def nearest_level_below(levels: list[float], current: float) -> float | None:
    valid = [level for level in levels if 0 < level < current]
    return max(valid) if valid else None


def nearest_level_above(levels: list[float], current: float) -> float | None:
    valid = [level for level in levels if level > current]
    return min(valid) if valid else None


def entry_buffer_pct(item: dict[str, Any]) -> float:
    h1_atr = item["1h"]["atrPct"] / 100.0
    return max(0.003, min(0.01, h1_atr * 0.35))


def empty_execution(status: str, reason: str) -> dict[str, Any]:
    return {
        "status": status,
        "side": "",
        "setupType": "",
        "entryLow": None,
        "entryHigh": None,
        "trigger": None,
        "current": None,
        "protection": None,
        "target1": None,
        "riskRewardToTarget1": None,
        "stopDistancePct": None,
        "reason": reason,
    }


def evaluate_executable_now(
    item: dict[str, Any],
    market_filter: dict[str, Any],
    max_stop_pct: float,
    min_rr: float,
) -> dict[str, Any]:
    state = item["state"]
    # INSUFFICIENT_DATA 标的无法评估执行，直接返回
    if state == "INSUFFICIENT_DATA":
        return empty_execution("NOT_EXECUTABLE", "insufficient data for execution evaluation")
    current = float(item.get("mark") or item.get("last") or 0)
    h1 = item["1h"]
    m15 = item["15m"]
    buffer_pct = entry_buffer_pct(item)

    if state == "LONG_TRIGGER_OR_CLOSE":
        trigger = h1["recent20High"]
        entry_high = trigger * (1 + buffer_pct)
        protection = nearest_level_below([h1["ma25"], m15["recent20Low"], h1["recent20Low"]], current)
        if not market_filter["longOk"]:
            result = empty_execution("NOT_EXECUTABLE", "BTC/ETH market filter blocks long")
        elif current < trigger:
            result = empty_execution("WAIT_TRIGGER", "price has not broken the 1h trigger")
        elif current > entry_high:
            result = empty_execution("MISSED_ENTRY", "price is beyond the allowed breakout entry band")
        elif not protection:
            result = empty_execution("NOT_EXECUTABLE", "no valid protection level below current price")
        elif h1["close"] <= h1["ma7"] or m15["close"] <= m15["ma7"]:
            result = empty_execution("NOT_EXECUTABLE", "short-term trend confirmation failed")
        elif h1["volRatio"] < 1.2 and not (m15["volRatio"] >= 1.2 and m15["takerBuyRatio20"] >= 0.52):
            result = empty_execution("NOT_EXECUTABLE", "volume confirmation is not strong enough")
        else:
            risk = current - protection
            stop_distance_pct = (risk / current) * 100
            range_width = max(h1["recent20High"] - h1["recent20Low"], 0)
            target1 = trigger + range_width * 0.5
            rr = (target1 - current) / risk if risk > 0 else 0
            if stop_distance_pct > max_stop_pct:
                result = empty_execution("NOT_EXECUTABLE", "stop distance is too wide for immediate execution")
            elif rr < min_rr:
                result = empty_execution("NOT_EXECUTABLE", "target room is too small versus stop risk")
            else:
                result = empty_execution("EXECUTABLE_NOW", "triggered and still inside the entry band")
                result.update(
                    {
                        "target1": round_float(target1),
                        "riskRewardToTarget1": round_float(rr, 2),
                        "stopDistancePct": round_float(stop_distance_pct, 2),
                    }
                )
        result.update(
            {
                "side": "long",
                "setupType": "breakout_long",
                "entryLow": round_float(trigger),
                "entryHigh": round_float(entry_high),
                "trigger": round_float(trigger),
                "current": round_float(current),
                "protection": round_float(protection) if protection else None,
            }
        )
        return result

    if state == "SHORT_TRIGGER_OR_CLOSE":
        trigger = h1["recent20Low"]
        entry_low = trigger * (1 - buffer_pct)
        protection = nearest_level_above([h1["ma25"], m15["recent20High"], h1["recent20High"]], current)
        if not market_filter["shortOk"]:
            result = empty_execution("NOT_EXECUTABLE", "BTC/ETH market filter blocks short")
        elif current > trigger:
            result = empty_execution("WAIT_TRIGGER", "price has not broken the 1h trigger")
        elif current < entry_low:
            result = empty_execution("MISSED_ENTRY", "price is beyond the allowed breakdown entry band")
        elif not protection:
            result = empty_execution("NOT_EXECUTABLE", "no valid protection level above current price")
        elif h1["close"] >= h1["ma7"] or m15["close"] >= m15["ma7"]:
            result = empty_execution("NOT_EXECUTABLE", "short-term trend confirmation failed")
        elif h1["volRatio"] < 1.2 and not (m15["volRatio"] >= 1.2 and m15["takerBuyRatio20"] <= 0.48):
            result = empty_execution("NOT_EXECUTABLE", "volume confirmation is not strong enough")
        else:
            risk = protection - current
            stop_distance_pct = (risk / current) * 100
            range_width = max(h1["recent20High"] - h1["recent20Low"], 0)
            target1 = trigger - range_width * 0.5
            rr = (current - target1) / risk if risk > 0 else 0
            if stop_distance_pct > max_stop_pct:
                result = empty_execution("NOT_EXECUTABLE", "stop distance is too wide for immediate execution")
            elif rr < min_rr:
                result = empty_execution("NOT_EXECUTABLE", "target room is too small versus stop risk")
            else:
                result = empty_execution("EXECUTABLE_NOW", "triggered and still inside the entry band")
                result.update(
                    {
                        "target1": round_float(target1),
                        "riskRewardToTarget1": round_float(rr, 2),
                        "stopDistancePct": round_float(stop_distance_pct, 2),
                    }
                )
        result.update(
            {
                "side": "short",
                "setupType": "breakdown_short",
                "entryLow": round_float(entry_low),
                "entryHigh": round_float(trigger),
                "trigger": round_float(trigger),
                "current": round_float(current),
                "protection": round_float(protection) if protection else None,
            }
        )
        return result

    return empty_execution("NOT_EXECUTABLE", "scanner state is not trigger-or-close")


def build_flat_row(item: dict[str, Any]) -> dict[str, Any]:
    long = item["long"]
    short = item["short"]
    # INSUFFICIENT_DATA 标的：时间周期字段不完整，只输出基础字段，指标填 None
    if item["state"] == "INSUFFICIENT_DATA":
        return {
            "symbol": item["symbol"],
            "state": item["state"],
            "longScore": long["score"],
            "shortScore": short["score"],
            "last": item["last"],
            "mark": item["mark"],
            "changePct": item["changePct"],
            "quoteVolume": item["quoteVolume"],
            "funding": item["funding"],
            "oi": item["oi"],
            "m15Close": None, "m15MA7": None, "m15MA25": None,
            "m15VolRatio": None, "m15BuyRatio": None,
            "h1Close": None, "h1MA7": None, "h1MA25": None,
            "h1High20": None, "h1Low20": None, "h1VolRatio": None, "h1RangePos": None,
            "h4Close": None, "h4MA7": None, "h4MA25": None,
            "dClose": None, "dMA7": None, "dMA25": None,
            "longReasons": "",
            "longWarnings": "；".join(long["warnings"]),
            "shortReasons": "",
            "shortWarnings": "；".join(short["warnings"]),
        }
    row = {
        "symbol": item["symbol"],
        "state": item["state"],
        "longScore": long["score"],
        "shortScore": short["score"],
        "last": item["last"],
        "mark": item["mark"],
        "changePct": item["changePct"],
        "quoteVolume": item["quoteVolume"],
        "funding": item["funding"],
        "oi": item["oi"],
        "m15Close": item["15m"]["close"],
        "m15MA7": item["15m"]["ma7"],
        "m15MA25": item["15m"]["ma25"],
        "m15VolRatio": item["15m"]["volRatio"],
        "m15BuyRatio": item["15m"]["takerBuyRatio20"],
        "h1Close": item["1h"]["close"],
        "h1MA7": item["1h"]["ma7"],
        "h1MA25": item["1h"]["ma25"],
        "h1High20": item["1h"]["recent20High"],
        "h1Low20": item["1h"]["recent20Low"],
        "h1VolRatio": item["1h"]["volRatio"],
        "h1RangePos": item["1h"]["rangePosition"],
        "h4Close": item["4h"]["close"],
        "h4MA7": item["4h"]["ma7"],
        "h4MA25": item["4h"]["ma25"],
        "dClose": item["1d"]["close"],
        "dMA7": item["1d"]["ma7"],
        "dMA25": item["1d"]["ma25"],
        "longReasons": "；".join(long["reasons"]),
        "longWarnings": "；".join(long["warnings"]),
        "shortReasons": "；".join(short["reasons"]),
        "shortWarnings": "；".join(short["warnings"]),
    }
    execution = item.get("execution")
    if execution:
        row.update(
            {
                "executableStatus": execution["status"],
                "executableSide": execution["side"],
                "entryLow": execution["entryLow"],
                "entryHigh": execution["entryHigh"],
                "protection": execution["protection"],
                "target1": execution["target1"],
                "riskRewardToTarget1": execution["riskRewardToTarget1"],
                "stopDistancePct": execution["stopDistancePct"],
                "executableReason": execution["reason"],
            }
        )
    return row


def progress(args: argparse.Namespace, message: str) -> None:
    if args.verbose or args.progress:
        print(message, flush=True)


def scan(args: argparse.Namespace) -> dict[str, Any]:
    progress(args, "Loading Binance futures exchange info and 24h tickers...")
    exchange = api_get("/fapi/v1/exchangeInfo", timeout=args.timeout, retries=args.retries)
    tickers = api_get("/fapi/v1/ticker/24hr", timeout=args.timeout, retries=args.retries)
    ticker_map = {ticker["symbol"]: ticker for ticker in tickers}
    symbols = [
        symbol["symbol"]
        for symbol in exchange["symbols"]
        if symbol.get("contractType") == "PERPETUAL"
        and symbol.get("quoteAsset") == "USDT"
        and symbol.get("status") == "TRADING"
    ]
    universe = []
    for symbol in symbols:
        ticker = ticker_map.get(symbol)
        if not ticker:
            continue
        quote_volume = float(ticker["quoteVolume"])
        if quote_volume >= args.min_quote_volume:
            universe.append(
                {
                    "symbol": symbol,
                    "quoteVolume": quote_volume,
                    "changePct": float(ticker["priceChangePercent"]),
                    "last": float(ticker["lastPrice"]),
                }
            )
    universe.sort(key=lambda row: row["quoteVolume"], reverse=True)
    if args.limit:
        universe = universe[: args.limit]
    progress(
        args,
        f"Scanning {len(universe)} USDT perpetual symbols "
        f"(minQuoteVolume={args.min_quote_volume:g}, limit={args.limit or 'all'})...",
    )

    # P2-11: premiumIndex 不带 symbol 一次返回全部，N次请求→1次
    progress(args, "Fetching premium index for all symbols...")
    all_premium = api_get("/fapi/v1/premiumIndex", timeout=args.timeout, retries=args.retries)
    premium_map = {p["symbol"]: p for p in all_premium}

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    insufficient_count = 0

    def fetch_symbol(base: dict[str, Any]) -> dict[str, Any]:
        """获取单个标的的 OI + 4 个周期 K线（并发执行）。"""
        symbol = base["symbol"]
        premium = premium_map.get(symbol)
        if not premium:
            raise ValueError(f"premiumIndex 中无 {symbol}")

        # OI + 4个klines 并发
        intervals = ("15m", "1h", "4h", "1d")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            oi_future = pool.submit(
                api_get, "/fapi/v1/openInterest",
                {"symbol": symbol}, timeout=args.timeout, retries=args.retries,
            )
            kline_futures = {
                iv: pool.submit(
                    api_get, "/fapi/v1/klines",
                    {"symbol": symbol, "interval": iv, "limit": 121},
                    timeout=args.timeout, retries=args.retries,
                )
                for iv in intervals
            }
            oi = oi_future.result()
            klines_raw = {iv: kline_futures[iv].result() for iv in intervals}

        item: dict[str, Any] = {
            "symbol": symbol,
            "last": base["last"],
            "mark": float(premium["markPrice"]),
            "changePct": round_float(base["changePct"], 2),
            "quoteVolume": round_float(base["quoteVolume"], 2),
            "funding": float(premium["lastFundingRate"]),
            "oi": float(oi["openInterest"]),
            "fetchedAt": datetime.now().isoformat(timespec="seconds"),
        }
        for iv in intervals:
            item[iv] = timeframe_stats(klines_raw[iv])
        return item

    for index, base in enumerate(universe, start=1):
        symbol = base["symbol"]
        try:
            item = fetch_symbol(base)
            # 任一时间周期数据不足则跳过评分，避免 MA99 变 MA30 等静默失真
            insufficient_tfs = [
                tf for tf in ("15m", "1h", "4h", "1d")
                if item[tf].get("dataQuality") == "insufficient"
            ]
            if insufficient_tfs:
                item["long"] = {"score": 0, "reasons": [], "warnings": [f"数据不足: {','.join(insufficient_tfs)}"]}
                item["short"] = {"score": 0, "reasons": [], "warnings": [f"数据不足: {','.join(insufficient_tfs)}"]}
                item["state"] = "INSUFFICIENT_DATA"
                insufficient_count += 1
            else:
                item["long"] = score_long(item)
                item["short"] = score_short(item)
                item["state"] = classify(item["long"]["score"], item["short"]["score"])
            results.append(item)
            if args.verbose or args.progress:
                print(f"{index}/{len(universe)} {symbol} {item['state']} L={item['long']['score']} S={item['short']['score']}")
            time.sleep(args.sleep)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            # 网络类错误：可重试，记录后继续
            errors.append({"symbol": symbol, "error": str(exc), "type": "network"})
            if args.verbose or args.progress:
                print(f"warn [network]: {symbol}: {exc}")
        except (KeyError, ValueError, IndexError) as exc:
            # 数据结构错误：API 返回格式异常，应告警
            errors.append({"symbol": symbol, "error": str(exc), "type": "data"})
            print(f"⚠️ 数据结构异常: {symbol}: {exc}", file=sys.stderr, flush=True)
        except Exception as exc:  # noqa: BLE001 - keep scanning other symbols.
            errors.append({"symbol": symbol, "error": str(exc), "type": "unknown"})
            if args.verbose or args.progress:
                print(f"warn [unknown]: {symbol}: {exc}")

    # P3-14: 错误率超过 universe 的 10% 时显式警告
    if universe and len(errors) / len(universe) > 0.10:
        print(
            f"⚠️ 错误率过高: {len(errors)}/{len(universe)} "
            f"({len(errors)/len(universe)*100:.1f}%) 个标的获取失败",
            file=sys.stderr,
            flush=True,
        )

    market_filter = build_market_filter(results)
    if args.executable_now:
        for item in results:
            item["execution"] = evaluate_executable_now(
                item,
                market_filter,
                max_stop_pct=args.max_stop_pct,
                min_rr=args.min_rr,
            )

    flat_rows = [build_flat_row(item) for item in results]
    flat_rows.sort(key=lambda row: (row["longScore"], row["shortScore"]), reverse=True)
    top_long = sorted(results, key=lambda item: item["long"]["score"], reverse=True)[: args.top]
    top_short = sorted(results, key=lambda item: item["short"]["score"], reverse=True)[: args.top]
    executable_now = [
        item
        for item in results
        if item.get("execution", {}).get("status") == "EXECUTABLE_NOW"
    ]
    executable_now.sort(
        key=lambda item: (
            item["execution"]["riskRewardToTarget1"] or 0,
            -1 * (item["execution"]["stopDistancePct"] or 999),
        ),
        reverse=True,
    )
    filter_meta = {
        "market": "Binance USDT perpetual futures",
        "minQuoteVolume": args.min_quote_volume,
        "limit": args.limit,
        "intervals": ["15m", "1h", "4h", "1d"],
    }
    counts = {
        "universe": len(universe),
        "scanned": len(results),
        "errors": len(errors),
        "insufficientData": insufficient_count,
    }
    if args.executable_now:
        filter_meta.update(
            {
                "executableNow": True,
                "maxStopPct": args.max_stop_pct,
                "minRiskReward": args.min_rr,
            }
        )
        counts["executableNow"] = len(executable_now)

    payload = {
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "filter": filter_meta,
        "counts": counts,
        "errors": errors,
        "results": results,
        "summaryRows": flat_rows,
        "topLong": top_long,
        "topShort": top_short,
    }
    if args.executable_now:
        payload["marketFilter"] = market_filter
        payload["executableNow"] = executable_now[: args.top]
    return payload


def compute_stability(payload: dict[str, Any], out_dir: Path) -> dict[str, Any] | None:
    """与上一份扫描对比候选名单 Jaccard 相似度，检测名单跳变（P1-7）。"""
    prev_files = sorted(out_dir.glob("*-scan.json"), key=lambda p: p.stat().st_mtime)
    if not prev_files:
        return None
    try:
        with prev_files[-1].open(encoding="utf-8") as fh:
            prev = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None

    def watchset(data: dict[str, Any]) -> set[str]:
        return {
            r["symbol"]
            for r in data.get("results", [])
            if r.get("state", "").startswith(("LONG", "SHORT"))
        }

    cur_w = watchset(payload)
    prev_w = watchset(prev)
    union = cur_w | prev_w
    jac = len(cur_w & prev_w) / len(union) if union else 1.0
    return {
        "jaccard": round(jac, 3),
        "prevAt": prev.get("generatedAt"),
        "added": sorted(cur_w - prev_w),
        "dropped": sorted(prev_w - cur_w),
        "warning": "名单跳变异常" if jac < 0.5 else None,
    }


def write_outputs(payload: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)

    # P1-7：写入前计算名单稳定性
    stability = compute_stability(payload, out_dir)
    if stability:
        payload["stability"] = stability
        if stability["warning"]:
            print(
                f"⚠️ 名单稳定性警告: Jaccard={stability['jaccard']} "
                f"(上一份: {stability['prevAt']})",
                file=sys.stderr,
                flush=True,
            )

    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    json_path = out_dir / f"{stamp}_binance-usdt-perp-scan.json"
    csv_path = out_dir / f"{stamp}_binance-usdt-perp-summary.csv"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    rows = payload["summaryRows"]
    if rows:
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    else:
        csv_path.write_text("", encoding="utf-8-sig")

    return {"json": str(json_path), "csv": str(csv_path)}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-quote-volume", type=float, default=30_000_000)
    parser.add_argument("--limit", type=int, default=100, help="Limit to top N symbols by 24h quote volume. Use 0 for no limit.")
    parser.add_argument("--top", type=int, default=12, help="Number of top long/short entries to include in terminal summary.")
    parser.add_argument("--sleep", type=float, default=0.08, help="Delay between symbols to reduce public API pressure.")
    parser.add_argument("--timeout", type=int, default=35, help="Per-request timeout in seconds for Binance public endpoints.")
    parser.add_argument("--retries", type=int, default=2, help="Retries per Binance public endpoint request.")
    parser.add_argument("--progress", action="store_true", help="Print per-symbol progress even without verbose details.")
    parser.add_argument("--executable-now", action="store_true", help="Add strict immediate-execution status without changing base scanner labels.")
    parser.add_argument("--max-stop-pct", type=float, default=3.0, help="Maximum stop distance percent for EXECUTABLE_NOW candidates.")
    parser.add_argument("--min-rr", type=float, default=1.5, help="Minimum reward/risk to target1 for EXECUTABLE_NOW candidates.")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    if args.limit == 0:
        args.limit = None

    payload = scan(args)
    paths = write_outputs(payload, Path(args.out_dir))
    terminal_summary = {
        "json": paths["json"],
        "csv": paths["csv"],
        "counts": payload["counts"],
        "topLong": [build_flat_row(item) for item in payload["topLong"]],
        "topShort": [build_flat_row(item) for item in payload["topShort"]],
    }
    if args.executable_now:
        terminal_summary["marketFilter"] = payload["marketFilter"]
        terminal_summary["executableNow"] = [
            build_flat_row(item) for item in payload["executableNow"]
        ]
    print(json.dumps(terminal_summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
