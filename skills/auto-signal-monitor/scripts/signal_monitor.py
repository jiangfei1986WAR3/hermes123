#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_URL = "https://fapi.binance.com/fapi/v1"


def fetch(path, timeout=12, tries=3):
    last_error = None
    for _ in range(tries):
        try:
            request = urllib.request.Request(
                BASE_URL + path,
                headers={"User-Agent": "auto-signal-monitor/1.0"},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except Exception as exc:
            last_error = exc
            time.sleep(0.5)
    raise last_error


def as_float(value):
    return float(value)


def kline_summary(symbol, interval, limit=80):
    rows = fetch(f"/klines?symbol={symbol}&interval={interval}&limit={limit}")
    closes = [as_float(row[4]) for row in rows]
    highs = [as_float(row[2]) for row in rows]
    lows = [as_float(row[3]) for row in rows]
    volumes = [as_float(row[5]) for row in rows]
    taker_buys = [as_float(row[9]) for row in rows]
    avg20 = sum(volumes[-21:-1]) / 20 if len(volumes) >= 21 else 0.0
    last = rows[-1]
    return {
        "open": as_float(last[1]),
        "high": as_float(last[2]),
        "low": as_float(last[3]),
        "close": as_float(last[4]),
        "volume": as_float(last[5]),
        "volRatio": (as_float(last[5]) / avg20) if avg20 else 0.0,
        "ma7": sum(closes[-7:]) / 7,
        "ma25": sum(closes[-25:]) / 25,
        "low20": min(lows[-20:]),
        "high20": max(highs[-20:]),
        "takerBuyRatio20": (sum(taker_buys[-20:]) / sum(volumes[-20:])) if sum(volumes[-20:]) else 0.0,
        "lastClosedClose": closes[-2],
        "lastClosedHigh": highs[-2],
        "lastClosedLow": lows[-2],
        "lastClosedVolume": volumes[-2],
        "lastClosedVolRatio": (volumes[-2] / avg20) if avg20 else 0.0,
    }


def symbol_snapshot(symbol, intervals):
    ticker = fetch(f"/ticker/24hr?symbol={symbol}")
    premium = fetch(f"/premiumIndex?symbol={symbol}")
    oi = fetch(f"/openInterest?symbol={symbol}")
    snapshot = {
        "symbol": symbol,
        "last": as_float(ticker["lastPrice"]),
        "mark": as_float(premium["markPrice"]),
        "changePct": as_float(ticker["priceChangePercent"]),
        "high24": as_float(ticker["highPrice"]),
        "low24": as_float(ticker["lowPrice"]),
        "quoteVolume": as_float(ticker["quoteVolume"]),
        "funding": as_float(premium["lastFundingRate"]),
        "openInterest": as_float(oi["openInterest"]),
    }
    for interval in intervals:
        snapshot[interval] = kline_summary(symbol, interval)
    return snapshot


def trigger_price(rule, data):
    interval = rule.get("timeframe", "15m")
    if rule.get("require_close", False):
        return data[interval]["lastClosedClose"]
    return data["last"]


def rule_volume_ok(rule, data):
    min_ratio = rule.get("min_volume_ratio")
    if min_ratio is None:
        return True
    interval = rule.get("timeframe", "15m")
    if rule.get("require_close", False):
        ratio = data[interval].get("lastClosedVolRatio", 0.0)
    else:
        ratio = data[interval].get("volRatio", 0.0)
    return ratio >= float(min_ratio)


def evaluate_breakout(rule, data):
    price = trigger_price(rule, data)
    raw_level = rule.get("price", rule.get("trigger_price"))
    if raw_level is None or float(raw_level) <= 0:
        raise KeyError(f"规则 {rule.get('id','?')} 的 price 无效（值={raw_level}），必须为正数")
    level = float(raw_level)
    side = rule.get("side", "above")
    crossed = price >= level if side == "above" else price <= level
    if crossed and rule_volume_ok(rule, data):
        return True, f"{rule.get('message', rule['id'])}; price={price:g}, level={level:g}"
    return False, ""


def evaluate_invalidation(rule, data):
    return evaluate_breakout(rule, data)


def evaluate_pullback_reclaim(rule, data):
    interval = rule.get("timeframe", "15m")
    candle = data[interval]
    pullback_low = float(rule["pullback_low"])
    pullback_high = float(rule["pullback_high"])
    reclaim = float(rule["reclaim_price"])
    invalidation = float(rule["invalidation_price"])
    touched_zone = candle["low20"] <= pullback_high and candle["high20"] >= pullback_low
    not_invalidated = data["last"] > invalidation and candle["lastClosedLow"] > invalidation
    reclaimed = data["last"] >= reclaim or candle["lastClosedClose"] >= reclaim
    if touched_zone and not_invalidated and reclaimed and rule_volume_ok(rule, data):
        return True, f"{rule.get('message', rule['id'])}; last={data['last']:g}, reclaim={reclaim:g}"
    return False, ""


def evaluate_market_filter(rule, snapshots):
    symbols = rule.get("symbols", [])
    timeframes = rule.get("timeframes", ["15m", "1h"])
    weak = []
    for symbol in symbols:
        data = snapshots.get(symbol)
        if not data:
            continue
        for timeframe in timeframes:
            candle = data.get(timeframe)
            if not candle:
                continue
            below_ma = data["last"] < candle["ma25"] if rule.get("weak_if_below_ma25", True) else False
            vol_ok = candle["volRatio"] >= float(rule.get("min_volume_ratio", 0))
            bearish = data["last"] < candle["open"]
            if below_ma and vol_ok and bearish:
                weak.append(f"{symbol} {timeframe}")
    if weak:
        return True, f"{rule.get('message', rule['id'])}: {', '.join(weak)}"
    return False, ""


def evaluate(plan):
    intervals = sorted(set(plan.get("intervals", ["15m", "1h"]) + ["15m", "1h"]))
    symbols = {plan["symbol"]}
    for rule in plan.get("rules", []):
        symbols.update(rule.get("symbols", []))
    snapshots = {symbol: symbol_snapshot(symbol, intervals) for symbol in symbols}
    primary = snapshots[plan["symbol"]]
    events = []
    for rule in plan.get("rules", []):
        rule_type = rule.get("type")
        rule_level = rule.get("level", "WATCH")
        if rule_level not in ("ALERT", "WATCH"):
            print(f"{datetime.now(timezone.utc).isoformat()} WARNING 规则 {rule.get('id','?')} 的 level='{rule_level}' 非法（只认 ALERT/WATCH），已跳过",
                  file=sys.stderr, flush=True)
            continue
        if rule_type == "breakout":
            ok, message = evaluate_breakout(rule, primary)
        elif rule_type == "invalidation":
            ok, message = evaluate_invalidation(rule, primary)
        elif rule_type == "pullback_reclaim":
            ok, message = evaluate_pullback_reclaim(rule, primary)
        elif rule_type == "market_filter":
            ok, message = evaluate_market_filter(rule, snapshots)
        else:
            print(f"{datetime.now(timezone.utc).isoformat()} WARNING 未知规则类型 '{rule_type}' (id={rule.get('id','?')})，已跳过",
                  file=sys.stderr, flush=True)
            ok, message = False, ""
        if ok:
            events.append({
                "id": rule["id"],
                "level": rule_level,
                "message": message,
                "rule_type": rule_type,
            })
    return snapshots, events


def load_state(path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def load_plan(path):
    return json.loads(path.read_text(encoding="utf-8"))


def discover_plan_paths(plans_dir):
    root = Path(plans_dir)
    if not root.exists():
        return []
    paths = []
    for path in sorted(root.glob("*.json")):
        name = path.name.lower()
        if name.endswith(".state.json") or name.endswith(".state.tmp.json"):
            continue
        paths.append(path)
    return paths


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def should_emit(event, state, cooldown):
    key = event["id"]
    now = time.time()
    last = float(state.get(key, 0))
    if now - last >= cooldown:
        state[key] = now
        return True
    return False


def beep(alerts, level):
    """Cross-platform alert sound: tries aplay/paplay on Linux, falls back to terminal bell."""
    sound = alerts.get("sound", "none")
    if sound == "none":
        return
    wav = alerts.get("wav_path")
    if sound == "wav" and wav and os.path.exists(wav):
        for player in ("aplay", "paplay", "afplay"):
            try:
                subprocess.Popen([player, wav], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except FileNotFoundError:
                continue
    # Fallback: terminal bell (works in most terminals)
    try:
        sys.stdout.write("\a" * (3 if level == "ALERT" else 1))
        sys.stdout.flush()
    except Exception:
        pass


def speak(text):
    """Cross-platform TTS: tries espeak/say/festival, silently skips if unavailable."""
    for cmd in (
        ["espeak", text],
        ["say", text],           # macOS
        ["festival", "--tts"],
    ):
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE if cmd[0] == "festival" else None,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if cmd[0] == "festival":
                p.communicate(input=text.encode())
            return
        except FileNotFoundError:
            continue


EVENTS_DIR = os.path.expanduser("~/.hermes/trading-events")


def write_event_file(plan, event):
    """Write a trigger event JSON to trading-events/ for the executor to pick up."""
    if event.get("level") != "ALERT":
        return
    os.makedirs(EVENTS_DIR, exist_ok=True)
    symbol = plan["symbol"]
    # Determine event type from rule's type field (not by guessing ID strings)
    rule_type = event.get("rule_type", "")
    rule_id = event.get("id", "")
    if rule_type == "invalidation":
        event_type = "INVALIDATION"
    else:
        event_type = "TRIGGER"
    event_data = {
        "type": event_type,
        "symbol": symbol,
        "rule_id": rule_id,
        "message": event.get("message", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    fname = f"{symbol}-{event_type}-{int(time.time())}.json"
    fpath = os.path.join(EVENTS_DIR, fname)
    Path(fpath).write_text(json.dumps(event_data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"EVENT_WRITTEN: {fpath}", flush=True)


def emit_alert(plan, event):
    alerts = plan.get("alerts", {})
    message = f"{plan['symbol']} {event['level']}: {event['message']}. Decision support only; manually confirm execution."
    print(message, flush=True)
    # Write event file for executor (ALERT level only)
    try:
        write_event_file(plan, event)
    except Exception as exc:
        print(f"event_write_error: {exc}", file=sys.stderr, flush=True)
    if os.name == "nt":
        try:
            beep(alerts, event["level"])
            if alerts.get("speech"):
                speak(message)
        except Exception as exc:
            print(f"sound_error: {exc}", file=sys.stderr, flush=True)


def run_once(plan, state_path):
    cooldown = int(plan.get("cooldown_seconds", 600))
    state = load_state(state_path)
    snapshots, events = evaluate(plan)
    # ★ 市场过滤器：BTC/ETH转弱时拦截入场信号，但放行失效信号
    market_filter_active = any(e.get("rule_type") == "market_filter" for e in events)
    emitted = []
    for event in events:
        if market_filter_active and event.get("rule_type") in ("breakout", "pullback_reclaim"):
            print(f"{datetime.now(timezone.utc).isoformat()} MARKET_FILTER_BLOCKED "
                  f"{plan['symbol']} {event['rule_type']}: 大盘转弱，拦截入场信号", flush=True)
            continue
        if should_emit(event, state, cooldown):
            emit_alert(plan, event)
            emitted.append(event)
    save_state(state_path, state)
    if not emitted:
        primary = snapshots[plan["symbol"]]
        print(
            f"{datetime.now(timezone.utc).isoformat()} DONT_NOTIFY "
            f"{plan['symbol']} last={primary['last']:g} mark={primary['mark']:g}; no trigger.",
            flush=True,
        )


def run_plan_path(plan_path):
    plan = load_plan(plan_path)
    # ★ 过期检查：expires_at 过了就不再评估，写 PLAN_EXPIRED 让执行器清理
    expires_at = plan.get("expires_at")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(expires_at)
            now = datetime.now(timezone.utc)
            # 兼容无时区的 expires_at（当作 UTC）
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if now >= expiry:
                os.makedirs(EVENTS_DIR, exist_ok=True)
                symbol = plan["symbol"]
                event_data = {
                    "type": "PLAN_EXPIRED",
                    "symbol": symbol,
                    "rule_id": "expiry",
                    "message": f"{symbol} 计划已过期 ({expires_at})",
                    "timestamp": now.isoformat(),
                }
                fname = f"{symbol}-PLAN_EXPIRED-{int(time.time())}.json"
                fpath = os.path.join(EVENTS_DIR, fname)
                Path(fpath).write_text(json.dumps(event_data, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"EVENT_WRITTEN: {fpath}", flush=True)
                print(f"{now.isoformat()} PLAN_EXPIRED {symbol}: 计划过期，已通知执行器清理", flush=True)
                return
        except (ValueError, TypeError) as exc:
            print(f"{datetime.now(timezone.utc).isoformat()} WARNING 解析 expires_at 失败: {exc}",
                  file=sys.stderr, flush=True)
    state_path = plan_path.with_suffix(".state.json")
    run_once(plan, state_path)


def run_directory_once(plans_dir):
    paths = discover_plan_paths(plans_dir)
    if not paths:
        print(f"{datetime.now(timezone.utc).isoformat()} DONT_NOTIFY no plan files in {plans_dir}", flush=True)
        return
    for path in paths:
        try:
            run_plan_path(path)
        except Exception as exc:
            print(f"{datetime.now(timezone.utc).isoformat()} ERROR {path.name}: {exc}", file=sys.stderr, flush=True)


def main():
    parser = argparse.ArgumentParser(description="Monitor Binance public-market signal plans.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--plan", help="Path to one monitor plan JSON.")
    source.add_argument("--plans-dir", help="Directory containing monitor plan JSON files.")
    parser.add_argument("--once", action="store_true", help="Run one check and exit.")
    parser.add_argument("--loop", action="store_true", help="Run repeatedly.")
    parser.add_argument("--interval-seconds", type=int, default=60, help="Loop interval.")
    args = parser.parse_args()

    if not args.once and not args.loop:
        args.once = True

    while True:
        try:
            if args.plan:
                run_plan_path(Path(args.plan))
            else:
                run_directory_once(args.plans_dir)
        except Exception as exc:
            print(f"{datetime.now(timezone.utc).isoformat()} ERROR {exc}", file=sys.stderr, flush=True)
        if args.once:
            break
        time.sleep(max(5, args.interval_seconds))


if __name__ == "__main__":
    main()
