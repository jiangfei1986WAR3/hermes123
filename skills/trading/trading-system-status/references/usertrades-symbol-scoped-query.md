# userTrades 符号级查询(2026-08-22 DOT 例)

## 现象

查 DOTUSDT 完整来回时,先跑 `api_get('/fapi/v1/userTrades', {'limit': 50}, signed=True)` 过滤 symbol:
- 只回 2 笔 08-20 23:16 的开仓 BUY(pnl=0)
- 次日 08-21 15:14/16:03 的平仓 SELL 全部"失踪" → 差点误判"平仓成交丢失/挂单没成交"

## 根因

`limit=N` 返回的是**全账户最近 N 笔**(跨所有币种),不是"该币最近 N 笔"。窗口边缘截断会漏掉某币的后续腿。

## 正确姿势

```python
from binance_executor import api_get
import datetime
# startTime = 开仓日前一天 16:00 UTC(即北京时间当天 00:00),毫秒
start = int(datetime.datetime(2026,8,19,16,0,0, tzinfo=datetime.timezone.utc).timestamp()*1000)
trades = api_get('/fapi/v1/userTrades', {'symbol':'DOTUSDT','startTime':start}, signed=True)
```

一次拿全 5 笔闭环:BUY 120.3 = SELL 120.3,pnl = 0/0/+1.26/+0.11/+2.28,真实落账、无幻影单。

## 适用场景

- 持仓变动交叉验证(判断平仓是否真实成交)
- 完整交易笔数统计(roundtrip 重建的源数据)
- 任何"查某币成交过程"的需求——一律符号级查询,`limit` 只作辅助
