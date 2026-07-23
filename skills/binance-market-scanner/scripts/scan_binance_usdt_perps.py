#!/usr/bin/env python3
"""Scan Binance USDT perpetual futures and save ranked setup reports."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


BASE_URL = "https://fapi.binance.com"
DEFAULT_OUT_DIR = r"D:\Projects\codex1\market-scans"


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
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    taker_buy_quote: float


def parse_klines(raw: list[list[Any]]) -> list[KlineRow]:
    return [
        KlineRow(
            open_time=int(row[0]),
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


def timeframe_stats(raw: list[list[Any]]) -> dict[str, float]:
    rows = parse_klines(raw)
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

    near_h1_ma25 = abs((h1["close"] - h1["ma25"]) / max(h1["close"], 1e-12)) <= 0.012
    if near_h1_ma25 and h1["volRatio"] <= 0.9 and h4["close"] > h4["ma25"]:
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


def classify(long_score: int, short_score: int) -> str:
    if long_score >= 70:
        return "LONG_TRIGGER_OR_CLOSE"
    if long_score >= 58:
        return "LONG_WATCH"
    if short_score >= 70:
        return "SHORT_TRIGGER_OR_CLOSE"
    if short_score >= 58:
        return "SHORT_WATCH"
    return "NEUTRAL"


def build_market_filter(results: list[dict[str, Any]]) -> dict[str, Any]:
    majors = {item["symbol"]: item for item in results if item["symbol"] in {"BTCUSDT", "ETHUSDT"}}
    weak = 0
    strong = 0
    notes: list[str] = []
    for symbol in ("BTCUSDT", "ETHUSDT"):
        item = majors.get(symbol)
        if not item:
            continue
        h1 = item["1h"]
        h4 = item["4h"]
        if h1["close"] < h1["ma25"] and h4["close"] < h4["ma25"]:
            weak += 1
            notes.append(f"{symbol} weak below 1h/4h MA25")
        if h1["close"] > h1["ma25"] and h4["close"] > h4["ma25"]:
            strong += 1
            notes.append(f"{symbol} strong above 1h/4h MA25")
    return {
        "longOk": weak < 2,
        "shortOk": strong < 2,
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

    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for index, base in enumerate(universe, start=1):
        symbol = base["symbol"]
        try:
            premium = api_get(
                "/fapi/v1/premiumIndex",
                {"symbol": symbol},
                timeout=args.timeout,
                retries=args.retries,
            )
            oi = api_get(
                "/fapi/v1/openInterest",
                {"symbol": symbol},
                timeout=args.timeout,
                retries=args.retries,
            )
            item: dict[str, Any] = {
                "symbol": symbol,
                "last": base["last"],
                "mark": float(premium["markPrice"]),
                "changePct": round_float(base["changePct"], 2),
                "quoteVolume": round_float(base["quoteVolume"], 2),
                "funding": float(premium["lastFundingRate"]),
                "oi": float(oi["openInterest"]),
            }
            for interval in ("15m", "1h", "4h", "1d"):
                raw = api_get(
                    "/fapi/v1/klines",
                    {"symbol": symbol, "interval": interval, "limit": 120},
                    timeout=args.timeout,
                    retries=args.retries,
                )
                item[interval] = timeframe_stats(raw)
            item["long"] = score_long(item)
            item["short"] = score_short(item)
            item["state"] = classify(item["long"]["score"], item["short"]["score"])
            results.append(item)
            if args.verbose or args.progress:
                print(f"{index}/{len(universe)} {symbol} {item['state']} L={item['long']['score']} S={item['short']['score']}")
            time.sleep(args.sleep)
        except Exception as exc:  # noqa: BLE001 - keep scanning other symbols.
            errors.append({"symbol": symbol, "error": str(exc)})
            if args.verbose or args.progress:
                print(f"warn: {symbol}: {exc}")

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


def generate_report(payload: dict[str, Any], top_n: int = 3) -> str:
    """Generate a formatted Chinese report from scan results."""
    lines = []
    counts = payload.get("counts", {})
    mf = payload.get("marketFilter", {})
    rows = payload.get("summaryRows", [])

    lines.append("=" * 50)
    lines.append("📊 币安 USDT 永续合约扫描报告")
    lines.append("=" * 50)
    lines.append(f"扫描时间: {payload.get('generatedAt', 'N/A')}")
    lines.append(f"交易对数量: {counts.get('scanned', '?')}")
    lines.append(f"大盘过滤器: 做多{'✅' if mf.get('longOk') else '❌'} | 做空{'✅' if mf.get('shortOk') else '❌'}")
    if mf.get("notes"):
        lines.append(f"  备注: {'; '.join(mf['notes'])}")
    lines.append("")

    # EXECUTABLE_NOW
    exec_now = payload.get("executableNow", [])
    if exec_now:
        lines.append(f"🔥 EXECUTABLE_NOW（可直接进场）: {len(exec_now)} 个")
        lines.append("-" * 50)
        for item in exec_now:
            long = item["long"]
            short = item["short"]
            execution = item.get("execution", {})
            side = execution.get("side", "")
            score = long["score"] if side == "long" else short["score"]
            lines.append(f"  {item['symbol']} [{side.upper()}] 分数:{score}")
            lines.append(f"    当前价: {item.get('last', 'N/A')}")
            lines.append(f"    入场区间: {execution.get('entryLow', '?')} ~ {execution.get('entryHigh', '?')}")
            lines.append(f"    止损: {execution.get('protection', '?')}")
            lines.append(f"    TP1: {execution.get('target1', '?')} | 盈亏比: {execution.get('riskRewardToTarget1', '?')}")
            lines.append("")
    else:
        lines.append("🔥 EXECUTABLE_NOW: 0 个（当前无直接进场信号）")
        lines.append("")

    # 按多头评分排序，取前 top_n
    rows_sorted = sorted(rows, key=lambda x: x.get("longScore", 0), reverse=True)

    lines.append(f"📋 多头评分 Top {top_n}（最接近触发的）")
    lines.append("-" * 50)
    for i, r in enumerate(rows_sorted[:top_n], 1):
        symbol = r.get("symbol", "?")
        lines.append(f"")
        lines.append(f"  🥇🥈🥉"[i] if i <= 3 else f"  #{i}", )
        lines[-1] = f"  {'🥇🥈🥉'[i-1] if i <= 3 else '#'+str(i)} {symbol}"
        lines.append(f"    状态: {r.get('state', '?')} | 执行状态: {r.get('executableStatus', '?')}")
        lines.append(f"    多头分: {r.get('longScore', '?')} / 空头分: {r.get('shortScore', '?')}")
        lines.append(f"    当前价: {r.get('last', '?')}")
        lines.append(f"    1H区间位置: {round(r.get('h1RangePos', 0) * 100, 1)}%")
        h1_high = r.get("h1High20")
        last = r.get("last")
        if h1_high and last and last > 0:
            dist = round((h1_high - last) / last * 100, 2)
            lines.append(f"    1H前高(参考突破位): {h1_high} | 距突破: {dist}%")
        lines.append(f"    做多理由: {r.get('longReasons', '无')}")
        if r.get("longWarnings"):
            lines.append(f"    ⚠️ 警告: {r.get('longWarnings')}")
        lines.append(f"    不可执行原因: {r.get('executableReason', '无')}")
        lines.append("")

    # WAIT_TRIGGER 列表
    wait_triggers = [r for r in rows if r.get("executableStatus") == "WAIT_TRIGGER"]
    if wait_triggers:
        lines.append(f"⏳ WAIT_TRIGGER（等待触发）: {len(wait_triggers)} 个")
        lines.append("-" * 50)
        for r in wait_triggers:
            lines.append(f"  {r.get('symbol')} | 多头分:{r.get('longScore')} | 入场:{r.get('entryLow')}~{r.get('entryHigh')} | 止损:{r.get('protection')} | TP1:{r.get('target1')}")
        lines.append("")

    return "\n".join(lines)


def write_outputs(payload: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
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
    parser.add_argument("--min-quote-volume", type=float, default=50_000_000)
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
