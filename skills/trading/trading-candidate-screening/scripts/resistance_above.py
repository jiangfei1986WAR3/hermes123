#!/usr/bin/env python3
"""突破位上方历史阻力验证(200日日线)。

用法:
  python3 resistance_above.py SYMBOL1,SYMBOL2 [--ref SYMBOL=PRICE]...

输出: 每币现价 + 参考位(默认现价)上方历史日线高点前8(天数+价格)。

判读:
  - 高点密集在参考位上方 <2% = 贴脸阻力簇 → 模式6:TP1对齐第一档R崩,不建
  - '200天内无更高点' = 真空/历史新高区 → 结构最强,但真空≠可建:
    仍须过追高禁手(4h RSI>=80 + 日线布林上轨外,PAXG 08-10 / LINK 08-21 判据)
  - 层层簇:突破一个簇后必须重跑本脚本验证新突破位上方(08-21 POL:
    0.0907 簇突破后上方还有 0.0915-0.092 簇),禁止复用上一轮验证结果

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
        above = sorted(
            [(len(ks) - 1 - i, float(k[2])) for i, k in enumerate(ks)
             if float(k[2]) > ref],
            key=lambda x: x[1])
        print(f'{sym} 现价 {p} | 参考位 {ref} 上方历史日线高点(前8):')
        if above:
            for d, h in above[:8]:
                print(f'  {d}天前: {h}')
        else:
            print('  ★ 200天内无更高点 = 真空/历史新高区(真空≠可建,仍须过追高禁手)')


if __name__ == '__main__':
    main()
