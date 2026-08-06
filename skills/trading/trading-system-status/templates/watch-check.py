#!/usr/bin/env python3
"""观察哨兵模板:现价到观察位则通知一次,否则静默。
用法:改 WATCH_PRICE / RESET_PRICE / URL 后放入 ~/.hermes/scripts/,建 no_agent Cron(every 1m, deliver=all)。
no_agent 语义:非空 stdout 原样通知,空 stdout 完全静默;非零退出会发错误告警,故 API 失败必须 exit 0。"""
import json, os, sys, time, urllib.request

SYMBOL = "XRPUSDT"
WATCH_PRICE = 1.0590   # 观察位(如 1h MA7 附近),现价 >= 此值触发通知
RESET_PRICE = 1.0530   # 回落跌破此值(重新走弱)则重置,允许再次观察
STATE_FILE = os.path.expanduser(f"~/.hermes/trading-plans/{SYMBOL}-watch.state")

def get_price():
    url = f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={SYMBOL}"
    with urllib.request.urlopen(url, timeout=10) as r:
        return float(json.load(r)["price"])

def main():
    try:
        price = get_price()
    except Exception:
        sys.exit(0)  # 网络失败静默,下个周期再试

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
        print(f"🔔 {SYMBOL} 观察位触发\n"
              f"现价: {price}\n"
              f"条件: 价格 >= {WATCH_PRICE}\n"
              f"下一步: 复查结构(如是否重新转弱)后再决定是否进入 plan 流程")
    elif price < RESET_PRICE and notified:
        state["notified"] = False
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    # 其他情况静默

if __name__ == "__main__":
    main()
