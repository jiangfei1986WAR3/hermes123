#!/usr/bin/env python3
"""Calculate crypto futures execution-plan sizing and command drafts."""

import argparse
import json
import math
from typing import List


def parse_targets(raw: str) -> List[float]:
    if not raw:
        return []
    return [float(part.strip()) for part in raw.split(",") if part.strip()]


def round_down(value: float, decimals: int) -> float:
    factor = 10**decimals
    return math.floor(value * factor) / factor


def main() -> int:
    parser = argparse.ArgumentParser(description="Build sizing details for a futures execution plan.")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--side", choices=["long", "short"], required=True)
    parser.add_argument("--entry", type=float, required=True)
    parser.add_argument("--stop", type=float, required=True)
    parser.add_argument("--equity", type=float, required=True)
    parser.add_argument("--risk-pct", type=float, default=0.5)
    parser.add_argument("--leverage", type=float, default=10)
    parser.add_argument("--tp", default="", help="Comma-separated take-profit prices")
    parser.add_argument("--qty-decimals", type=int, default=3)
    parser.add_argument("--reduce-percents", default="", help="Comma-separated reduce percentages for targets")
    args = parser.parse_args()

    if args.equity <= 0:
        raise SystemExit("equity must be positive")
    if args.risk_pct <= 0:
        raise SystemExit("risk-pct must be positive")
    if args.leverage <= 0:
        raise SystemExit("leverage must be positive")
    if args.entry <= 0 or args.stop <= 0:
        raise SystemExit("entry and stop must be positive")
    if args.side == "long" and args.stop >= args.entry:
        raise SystemExit("for long plans, stop must be below entry")
    if args.side == "short" and args.stop <= args.entry:
        raise SystemExit("for short plans, stop must be above entry")

    targets = parse_targets(args.tp)
    reduce_percents = parse_targets(args.reduce_percents)

    risk_amount = args.equity * args.risk_pct / 100
    stop_distance = abs(args.entry - args.stop)
    stop_distance_pct = stop_distance / args.entry * 100
    raw_quantity = risk_amount / stop_distance
    quantity = round_down(raw_quantity, args.qty_decimals)
    notional = quantity * args.entry
    initial_margin = notional / args.leverage

    target_rows = []
    for idx, target in enumerate(targets, start=1):
        reward = (target - args.entry) if args.side == "long" else (args.entry - target)
        r_multiple = reward / stop_distance
        reduce_percent = reduce_percents[idx - 1] if idx <= len(reduce_percents) else None
        target_rows.append(
            {
                "label": f"TP{idx}",
                "price": target,
                "r_multiple": round(r_multiple, 3),
                "reduce_percent": reduce_percent,
            }
        )

    entry_side = "BUY" if args.side == "long" else "SELL"
    exit_side = "SELL" if args.side == "long" else "BUY"
    quantity_str = f"{quantity:.{args.qty_decimals}f}"

    commands = [
        f"binance futures leverage --symbol {args.symbol.upper()} --leverage {int(args.leverage)}",
        (
            f"binance futures order --symbol {args.symbol.upper()} --side {entry_side} "
            f"--type STOP_MARKET --stopPrice {args.entry:g} --quantity {quantity_str}"
        ),
        (
            f"binance futures order --symbol {args.symbol.upper()} --side {exit_side} "
            f"--type STOP_MARKET --stopPrice {args.stop:g} --closePosition true"
        ),
    ]

    for row in target_rows:
        if row["reduce_percent"] is None:
            continue
        reduce_qty = round_down(quantity * row["reduce_percent"] / 100, args.qty_decimals)
        commands.append(
            f"binance futures order --symbol {args.symbol.upper()} --side {exit_side} "
            f"--type TAKE_PROFIT_MARKET --stopPrice {row['price']:g} --quantity {reduce_qty:.{args.qty_decimals}f}"
        )

    result = {
        "symbol": args.symbol.upper(),
        "side": args.side,
        "entry": args.entry,
        "stop": args.stop,
        "risk": {
            "equity_usdt": args.equity,
            "risk_percent": args.risk_pct,
            "risk_amount_usdt": round(risk_amount, 6),
            "stop_distance": round(stop_distance, 8),
            "stop_distance_percent": round(stop_distance_pct, 4),
        },
        "position": {
            "quantity": quantity,
            "raw_quantity": raw_quantity,
            "notional_usdt": round(notional, 6),
            "leverage": args.leverage,
            "estimated_initial_margin_usdt": round(initial_margin, 6),
        },
        "take_profits": target_rows,
        "status": "EXECUTABLE_AFTER_CONFIRMATION" if quantity > 0 else "NOT_EXECUTABLE",
        "command_drafts": commands,
        "notes": [
            "Command drafts are for manual confirmation only.",
            "Check exchange quantity precision, existing positions, open orders, margin mode, and account mode before live execution.",
        ],
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
