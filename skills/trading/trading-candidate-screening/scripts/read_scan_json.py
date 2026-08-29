#!/usr/bin/env python3
"""binance-market-scanner 扫描 JSON 的结构化读取（防御封装）。

背景：results/topLong/topShort 是嵌套结构（r['long']['score']），summaryRows 是扁平键
（longScore/h1Close…）。对嵌套行用扁平键 .get() 会静默全 None 不报错——
2026-08-17 与 2026-08-29 两次踩坑（排名排序全靠 None，白跑一轮）后机械化。

用法：
  python3 read_scan_json.py                 # 自动取 market-scans 目录最新文件，Top15
  python3 read_scan_json.py latest 20       # 同上，Top20
  python3 read_scan_json.py <json路径> [N]  # 指定文件

输出：counts / 分数排名榜 / stability(jaccard+added+dropped) / BTC/ETH 大盘速查。
"""
import glob
import json
import os
import sys

SCAN_DIR = os.path.expanduser('/root/Documents/trae_projects/zhuandaqian/market-scans')
TF_KEYS = ('close', 'ma7', 'ma25', 'volRatio', 'takerBuyRatio20', 'rsi')


def _flat(r):
    """把一行（嵌套或扁平）拉平成统一字段，两结构自适应。"""
    d = {
        'symbol': r.get('symbol'),
        'state': r.get('state'),
        'last': r.get('last'),
        'chg': r.get('changePct'),
        'funding': r.get('funding'),
    }
    lg, sh = r.get('long') or {}, r.get('short') or {}
    # 嵌套行取 r['long']['score']；扁平行回退 longScore/shortScore
    d['long_score'] = lg.get('score') if isinstance(lg, dict) else r.get('longScore')
    d['short_score'] = sh.get('score') if isinstance(sh, dict) else r.get('shortScore')
    for tf in ('15m', '1h', '4h', '1d'):
        x = r.get(tf) or {}
        for k in TF_KEYS:
            if k in x:
                d[f'{tf}_{k}'] = x[k]
    return d


def main():
    args = sys.argv[1:]
    path = args[0] if args else 'latest'
    topn = int(args[1]) if len(args) > 1 else 15
    if not path or path == 'latest':
        files = sorted(glob.glob(SCAN_DIR + '/*_binance-usdt-perp-scan.json'), key=os.path.getmtime)
        if not files:
            sys.exit('no scan json found under ' + SCAN_DIR)
        path = files[-1]
    with open(path) as f:
        data = json.load(f)

    rows = [_flat(r) for r in data.get('results') or data.get('summaryRows') or []]
    if not rows:
        sys.exit('empty results/summaryRows in ' + path)
    print(f'文件: {os.path.basename(path)}  counts: {data.get("counts")}  共 {len(rows)} 行')

    ranked = sorted(rows, key=lambda d: max(d.get('long_score') or 0, d.get('short_score') or 0), reverse=True)[:topn]
    print(f"\n{'symbol':<14}{'state':<23}{'L':>4}{'S':>4}{'chg%':>8}  last")
    for d in ranked:
        print(f"{d['symbol']:<14}{str(d['state']):<23}"
              f"{d.get('long_score') or 0:>4}{d.get('short_score') or 0:>4}"
              f"{(d.get('chg') or 0):>8.2f}  {d.get('last')}")

    st = data.get('stability') or {}
    print('\nstability: jaccard=', st.get('jaccard'),
          ' added=', st.get('added'), ' dropped=', st.get('dropped'))

    print('\n=== BTC/ETH 大盘速查（1h） ===')
    for d in rows:
        if d.get('symbol') in ('BTCUSDT', 'ETHUSDT'):
            print(f"{d['symbol']}: chg={d.get('chg')}% 1h_close={d.get('1h_close')} "
                  f"1h_ma7={d.get('1h_ma7')} 1h_ma25={d.get('1h_ma25')} "
                  f"1h_vol={d.get('1h_volRatio')} 1h_buy={d.get('1h_takerBuyRatio20')}")


if __name__ == '__main__':
    main()
