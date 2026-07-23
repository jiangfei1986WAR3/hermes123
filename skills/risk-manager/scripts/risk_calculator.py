#!/usr/bin/env python3
"""Calculate futures position sizing and leverage risk."""

from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Any


def parse_leverages(value: str) -> list[float]:
    return [float(part.strip().rstrip("xX")) for part in value.split(",") if part.strip()]


def round_float(value: float, digits: int = 8) -> float:
    if not math.isfinite(value):
        return 0.0
    return round(value, digits)


def calculate(args: argparse.Namespace) -> dict[str, Any]:
    side = args.side.lower()
    if side not in {"long", "short"}:
        raise ValueError("--side must be long or short")
    if args.equity <= 0 or args.entry <= 0 or args.stop <= 0:
        raise ValueError("--equity, --entry, and --stop must be positive")

    if side == "long":
        stop_distance = (args.entry - args.stop) / args.entry
        if args.target:
            reward_distance = (args.target - args.entry) / args.entry
    else:
        stop_distance = (args.stop - args.entry) / args.entry
        if args.target:
            reward_distance = (args.entry - args.target) / args.entry

    if stop_distance <= 0:
        raise ValueError("stop must be below entry for long, above entry for short")

    risk_amount = args.equity * (args.risk_pct / 100)
    notional = risk_amount / stop_distance
    base_quantity = notional / args.entry
    stop_loss_at_position = notional * stop_distance

    leverage_rows = []
    for lev in parse_leverages(args.leverages):
        if lev <= 0:
            continue
        initial_margin = notional / lev
        if side == "long":
            liq_approx = args.entry * (1 - 1 / lev)
            liq_gap_pct = (args.entry - liq_approx) / args.entry
            stop_vs_liq = args.stop - liq_approx
        else:
            liq_approx = args.entry * (1 + 1 / lev)
            liq_gap_pct = (liq_approx - args.entry) / args.entry
            stop_vs_liq = liq_approx - args.stop
        leverage_rows.append(
            {
                "leverage": f"{round_float(lev, 2)}x",
                "initialMargin": round_float(initial_margin, 4),
                "usesEquityPct": round_float(initial_margin / args.equity * 100, 2),
                "liqApprox": round_float(liq_approx, 8),
                "liqGapPct": round_float(liq_gap_pct * 100, 2),
                "stopDistanceFromApproxLiq": round_float(stop_vs_liq, 8),
                "stopBeforeApproxLiq": stop_vs_liq > 0,
            }
        )

    result: dict[str, Any] = {
        "inputs": {
            "equity": args.equity,
            "side": side,
            "entry": args.entry,
            "stop": args.stop,
            "target": args.target,
            "riskPct": args.risk_pct,
        },
        "risk": {
            "stopDistancePct": round_float(stop_distance * 100, 4),
            "riskAmount": round_float(risk_amount, 4),
            "notionalPosition": round_float(notional, 4),
            "baseQuantity": round_float(base_quantity, 8),
            "plannedLossAtStop": round_float(stop_loss_at_position, 4),
        },
        "leverages": leverage_rows,
        "warnings": [],
    }

    if args.target:
        r_multiple = reward_distance / stop_distance
        result["target"] = {
            "rewardDistancePct": round_float(reward_distance * 100, 4),
            "rewardAmount": round_float(notional * reward_distance, 4),
            "rMultiple": round_float(r_multiple, 3),
        }

    if args.risk_pct > 2:
        result["warnings"].append("单笔风险超过2%，高于常规风控上限。")
    if any(row["usesEquityPct"] > 100 for row in leverage_rows):
        result["warnings"].append("至少一个杠杆档位所需初始保证金超过账户权益。")
    if any(not row["stopBeforeApproxLiq"] for row in leverage_rows):
        result["warnings"].append("至少一个杠杆档位的计划止损接近或越过粗略强平价。")
    if any(row["leverage"] in {"10.0x", "20.0x"} for row in leverage_rows):
        result["warnings"].append("10x/20x 超出多数确认型交易的稳健杠杆区间，必须降低仓位或等待更强确认。")

    return result


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--equity", type=float, required=True, help="Account equity or capital in USDT.")
    parser.add_argument("--entry", type=float, required=True)
    parser.add_argument("--stop", type=float, required=True)
    parser.add_argument("--target", type=float)
    parser.add_argument("--side", default="long", choices=["long", "short"])
    parser.add_argument("--risk-pct", type=float, default=0.5)
    parser.add_argument("--leverages", default="5,10,20")
    args = parser.parse_args()
    print(json.dumps(calculate(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
