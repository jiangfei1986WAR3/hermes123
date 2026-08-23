# market_filter 规则字段 + 历史模板位置(2026-08-22 WLFI 建计划实录)

## market_filter 规则精确结构(源码 signal_monitor.py 156-181 行)

```json
{
  "id": "market_filter_btc_eth",
  "level": "WATCH",
  "type": "market_filter",
  "symbols": ["BTCUSDT", "ETHUSDT"],
  "timeframes": ["15m", "1h"],
  "min_volume_ratio": 1.2,
  "message": "BTC/ETH放量强势下跌，暂停XX做多"
}
```

- `symbols` 缺省 [] → 循环体空转,**等于没有大盘过滤**(静默无拦截,不报错)。必须显式写 ["BTCUSDT","ETHUSDT"]
- `timeframes` 缺省 ["15m","1h"];`min_volume_ratio` 缺省 0,历史标准写 1.2
- 做多拦截条件(三条件同时满足):该币该周期 `last < ma25` 且 `last < open` 且 `volRatio ≥ min_volume_ratio`;做空镜像取反
- 拦截只写 state 记录 + 输出 WATCH 行(不入事件、不算不静默),触发时 executor 侧由 MARKET_FILTER_BLOCKED 门兜底
- 生成 plan 前先看 BTC/ETH 15m 是否放量下跌(量比>1.2 且买盘<0.48)——是则多单候选整批降级,别浪费 fetch_klines 预算

## 历史模板位置(live 目录空时找这里)

- plan JSON 模板:`/root/hermes-backup/trading-plans/*-plan.json`(XMR 突破多、TRX 突破多、ZEC 等完整字段示例)
- 监控包装脚本模板:`/root/hermes-backup/scripts/*-monitor-check.sh`

## 监控包装脚本模板(2026-08-22 WLFI 实测)

```bash
#!/usr/bin/env bash
PLAN="$HOME/.hermes/trading-plans/WLFIUSDT-plan.json"
MONITOR="$HOME/.hermes/skills/auto-signal-monitor/scripts/signal_monitor.py"
[ ! -f "$PLAN" ] && exit 0
OUTPUT=$(python3 "$MONITOR" --plan "$PLAN" 2>&1 | grep -v "DONT_NOTIFY")
if echo "$OUTPUT" | grep -qiE "ALERT|TRIGGER|EXPIRED|EVENT_WRITTEN|ERROR|WARNING"; then
    echo "$OUTPUT"
fi
```

- 自保护首行:`[ ! -f "$PLAN" ] && exit 0`(plan 被清理后静默)
- 关键词白名单含 ERROR/WARNING:硬校验失败(空 rules[] 等)会被推微信而非静默掩盖
- 建 Cron 前双验证:①`signal_monitor.py --plan ... --dry-run` 输出 `DONT_NOTIFY ... no trigger` + exit 0 = 静默;②`bash 脚本` 空输出 + exit 0 = 静默。两步都过才建

## WLFI 完整 plan 字段(低波动突破多模板,2026-08-22)

顶层必带:name/symbol/direction/setup_type/status/created_at/expires_at/market_filter_symbols/intervals/cooldown_seconds/alerts/entry(trigger_price)/entry_trigger/stop_loss/take_profits/risk(margin_usdt+leverage,不写 quantity)/monitor/rules。

- 触发规则:`breakout` + `side:"above"` + `require_close:true` + `min_volume_ratio:1.0` + timeframe 15m
- 失效规则:`invalidation` + `side:"below"` + `require_close:false`(实时,保守,勿改收盘确认)
- R 预检:触发 0.06360 / 止损 0.06220(平台低点下方,1.2×1h ATR)/ TP1 0.06550=1.36R / TP2 0.06680=2.29R / 风险额 2.2U
- expires_at 24h:stability jaccard 0.638 无跳变 warning 且候选连续两轮在榜 → 24h;名单跳变 warning → 12h
