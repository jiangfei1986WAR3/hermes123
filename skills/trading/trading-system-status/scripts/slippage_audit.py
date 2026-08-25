#!/usr/bin/env python3
"""入场滑点审计（2026-08-25 实测可用）。

用户问"滑点是不是大了 / 能优化吗"时先跑这个，别凭印象也别引用文档里的旧百分比。

核心：滑点必须按**多空方向**校正才叫"不利滑点"——做多成交更高=吃亏，做空成交更低=吃亏。
只看 executor 日志 `滑点校准 ... 平移 +X` 的正负号会把空单判反。

数据源：~/.hermes/trading-history/*.json（executor 每笔"开仓完成"写的账本快照）
用法：  python3 slippage_audit.py [--worst N]
"""
import argparse
import glob
import json
import os
import statistics

HIST = os.path.expanduser("~/.hermes/trading-history")


def load_rows():
    """返回 (sym, dirn, trig, act, adverse_pct, dist_1R, r_lost, usd) 列表。

    dist_1R/r_lost/usd 在账本缺 stop_loss 或 risk.quantity 时为 None（老记录常缺）。
    plan 里的 stop_loss 是**平移后**值，原始止损距离需用 shift 反推。
    """
    rows = []
    for f in sorted(glob.glob(os.path.join(HIST, "*.json"))):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        p = d.get("plan", d)
        sym = p.get("symbol")
        dirn = (p.get("direction") or "").lower()
        trig = p.get("entry_trigger") or (p.get("entry") or {}).get("trigger_price")
        act = d.get("actual_entry") or p.get("actual_entry") or d.get("entry_price")
        if not (sym and trig and act):
            continue
        shift = act - trig
        raw_pct = shift / trig * 100
        adverse = raw_pct if dirn == "long" else -raw_pct  # 正=对我们不利
        sl, qty = p.get("stop_loss"), (p.get("risk") or {}).get("quantity")
        dist = r_lost = usd = None
        if sl and qty:
            sl0 = sl - shift                      # 还原平移前止损
            dist = abs(trig - sl0)
            if dist > 0:
                adverse_px = shift if dirn == "long" else -shift
                r_lost = adverse_px / dist
                usd = adverse_px * qty
        rows.append((sym, dirn, trig, act, adverse, dist, r_lost, usd))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worst", type=int, default=12, help="列出最差 N 笔")
    a = ap.parse_args()

    rows = load_rows()
    if not rows:
        print(f"没读到账本记录，检查 {HIST}")
        return
    adv = [r[4] for r in rows]
    rr = [r for r in rows if r[6] is not None]

    print(f"开仓账本 {len(rows)} 笔（可算 R 的 {len(rr)} 笔，其余缺 stop_loss/quantity）\n")
    print(f"{'币种':<11}{'方向':<6}{'触发价':>12}{'成交价':>12}{'不利滑点%':>11}{'吃掉R':>9}")
    print("-" * 62)
    for sym, dirn, trig, act, ad, dist, r, u in sorted(rows, key=lambda x: -x[4])[: a.worst]:
        rs = f"{r:+.3f}" if r is not None else "  n/a"
        print(f"{sym:<11}{dirn:<6}{trig:>12.4f}{act:>12.4f}{ad:>+11.2f}{rs:>9}")
    print(f"  ... (仅列最差 {a.worst} 笔)")
    print("-" * 62)

    print(f"不利滑点(正=吃亏): 均值 {statistics.mean(adv):+.3f}%  中位 {statistics.median(adv):+.3f}%")
    print(f"  >0.7%: {sum(1 for x in adv if x > 0.7)}/{len(adv)}   "
          f">1.0%: {sum(1 for x in adv if x > 1.0)}/{len(adv)}   "
          f"占便宜(负): {sum(1 for x in adv if x < 0)}/{len(adv)}")
    n_adv = sum(1 for x in adv if x > 0)
    print(f"  方向偏性: {n_adv}/{len(adv)} 笔偏不利"
          f"（随机应≈50%，明显偏高=结构性成因，见 references/entry-slippage-audit.md）")
    if rr:
        rs = [r[6] for r in rr]
        us = [r[7] for r in rr]
        print(f"\n折算 R: 均值 {statistics.mean(rs):+.3f}R  中位 {statistics.median(rs):+.3f}R  最差 {max(rs):+.3f}R")
        print(f"累计隐性成本: {sum(rs):+.2f}R ≈ {sum(us):+.2f} USDT")
        print(f"若延迟砍半可挽回约 {abs(sum(us)) / 2:.2f} USDT / {abs(sum(rs)) / 2:.2f}R")


if __name__ == "__main__":
    main()
