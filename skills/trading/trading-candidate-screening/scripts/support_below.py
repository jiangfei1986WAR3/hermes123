#!/usr/bin/env python3
"""破位位下方历史支撑验证(200日日线) —— resistance_above.py 的空头镜像。

用法:
  python3 support_below.py SYMBOL1,SYMBOL2 [--ref=SYMBOL=触发价]...

⚠ --ref 必须传**触发价**,不是破位位、不是现价。R 一律用触发价算(成交在触发价)。
  APT 2026-08-26 实测:破位位 0.5535 与触发价 0.55184 的 R 分子差 90%
  (0.0035 vs 0.00184),用破位位会把 0.16R 印成 0.30R+,放行不达标计划。

输出: 每币现价 + 参考位(默认现价,仅供人工比对)下方历史日线低点最近8档 + 密集度统计。

判读(配套 SKILL.md 模式6②;均为复核提示,不替代真实 R 计算):
  - `PROPOSED / NOT ACTIVE`: 参考位下方 <1% 内 >=2 档日线低点=贴脸支撑簇 这条
    快捷判据未经用户批准,只提示复核;同一支撑簇在不同止损距离下 R 可从 0.16R 到 1.2R+
  - 第一档支撑距参考位 < 1.2x止损距离 → TP1 <1.2R,先算 R 再决定出口
  - '200天内无更低点' = 下方真空 → TP 只能机械画(违 ZEC 禁手)
  - 破一档簇后必须重跑,禁止复用上一轮验证结果

只调币安公开行情接口,不签名不登录。
"""
import json
import sys
import urllib.request


def api_get(path, **params):
    qs = '&'.join(f'{k}={v}' for k, v in params.items())
    req = urllib.request.Request(
        f'https://fapi.binance.com{path}?{qs}',
        headers={'User-Agent': 'Mozilla/5.0'})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())


def main():
    argv = sys.argv[1:]
    syms = argv[0].split(',') if argv else []
    refs = {}
    for a in argv[1:]:
        if a.startswith('--ref='):
            sym, price = a[len('--ref='):].split('=')
            refs[sym] = float(price)
    for sym in syms:
        ks = api_get('/fapi/v1/klines', symbol=sym, interval='1d', limit=200)
        p = float(api_get('/fapi/v1/ticker/price', symbol=sym)['price'])
        ref = refs.get(sym, p)
        below = sorted(
            [(len(ks) - 1 - i, float(k[3])) for i, k in enumerate(ks)
             if float(k[3]) < ref],
            key=lambda x: -x[1])
        print(f'{sym} 现价 {p} | 参考位 {ref} 下方历史日线低点(最近8档):')
        if not below:
            print('  ★ 200天内无更低点 = 下方真空(TP 只能机械画 → 不建)')
            continue
        for d, l in below[:8]:
            print(f'  {d}天前: {l}   距参考 {(ref - l) / ref * 100:.2f}%')
        for pct in (1.0, 2.0):
            n = len([1 for _, l in below if (ref - l) / ref * 100 < pct])
            flag = (' ← 贴脸支撑簇(PROPOSED/NOT ACTIVE,仅提示复核)'
                    if (pct == 1.0 and n >= 2) else '')
            print(f'  参考位下方 {pct:.0f}% 内共 {n} 档{flag}')
        d1, l1 = below[0]
        warn = '' if sym in refs else '  ⚠ 未传 --ref:参考位=现价,下面 R 分子无效'
        print(f'  第一档支撑 {l1} 距参考位 {(ref - l1) / ref * 100:.2f}%'
              f' → TP1 若对齐它, R 分子=触发价-支撑={(ref - l1):.8g},'
              f' 须除以止损距离(触发价-止损)得 R{warn}')


if __name__ == '__main__':
    main()
