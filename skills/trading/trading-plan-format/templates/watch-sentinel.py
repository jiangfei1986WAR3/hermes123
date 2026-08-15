#!/usr/bin/env python3
"""观察哨兵模板:盯"非交易条件"的价格位置,触发才通知一次,否则静默。
部署:no_agent=true 的 Cron(每分钟),script 参数用相对 ~/.hermes/scripts/ 的文件名。
语义:非空 stdout = 通知原样发送;空 stdout = 完全静默;非零退出 = 错误告警(所以网络失败要 exit 0)。
防刷屏:state 文件标记 notified,触发一次后不再通知;价格回落到 RESET_PRICE 下方复位,允许再次观察。
与执行链路完全隔离:不 import binance_executor、不写事件文件,物理上不可能下单。

用法:复制本文件到 ~/.hermes/scripts/<name>-watch-check.py,改 SYMBOL/WATCH_PRICE/RESET_PRICE/STATE_FILE,
再建 Cron(no_agent=true, every 1m, deliver=all)。"""
import json, os, sys, time, urllib.request

SYMBOL = "XRPUSDT"
WATCH_PRICE = 1.0590   # 观察位(触发条件: 现价 >= 该值)
RESET_PRICE = 1.0530   # 回落跌破该值(条件消失)则重置,允许再次触发
STATE_FILE = os.path.expanduser(f"~/.hermes/trading-plans/{SYMBOL}-watch.state")

def get_price():
    url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={SYMBOL}"
    with urllib.request.urlopen(url, timeout=10) as r:
        return float(json.load(r)["price"])

def main():
    try:
        price = get_price()
    except Exception:
        sys.exit(0)  # 网络失败静默,下个周期再试(no_agent 模式非零退出会发错误告警)

    state = {}
    if os.path.exists(STATE_FILE):
        try:
            state = json.load(open(STATE_FILE))
        except Exception:
            state = {}

    notified = state.get("notified", False)

    if price >= WATCH_PRICE and not notified:
        state["notified"] = True
        state["price"] = price
        state["time"] = int(time.time())
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
        print(f"🔔 {SYMBOL} 观察触发\n现价: {price}\n观察位: {WATCH_PRICE}\n下一步: 人工复查后再决定是否建 plan")
    elif price < RESET_PRICE and notified:
        state["notified"] = False
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    # 其他情况静默

if __name__ == "__main__":
    main()
