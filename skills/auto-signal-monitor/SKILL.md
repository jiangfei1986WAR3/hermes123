---
name: auto-signal-monitor
description: Convert crypto futures trade plans into recurring public-market signal monitors with concise text alerts, optional local beep/WAV/text-to-speech notifications, and manual-execution reminders. Use when the user wants to monitor Binance USDT perpetual pairs for breakout, pullback, invalidation, BTC/ETH market-filter, funding/OI, or volume conditions without logging in or placing orders.
---

# Auto Signal Monitor

Use this skill to turn a trading-analysis plan into a monitored signal checklist. This skill is for alerts only.

## Safety

- Use only public Binance market endpoints.
- Never log in, read account data, place orders, set stops, close positions, or operate funds.
- Treat all alerts as decision support. The user manually confirms and executes.
- If the user asks for automatic trading, decline execution and offer signal monitoring, paper trading, or bot design instead.

## Workflow

1. If no trade plan exists, use `trading-analysis` first to define:
   - symbol, direction, timeframe
   - breakout trigger
   - pullback/reclaim trigger
   - invalidation/protection line
   - BTC/ETH market filter
   - alert frequency and whether sound is wanted
2. Convert the plan into a JSON monitor plan. Use `references/plan-schema.md`.
3. For quick one-off checks, run `scripts/signal_monitor.py --plan <plan.json> --once`.
4. For repeated local monitoring with sound, prefer the directory supervisor: `scripts/signal_monitor.py --plans-dir <plans-dir> --loop --interval-seconds 60`.
5. Save each new pair setup as one `*.json` file in the plans directory. The supervisor auto-detects new files on the next loop and ignores `*.state.json`.
6. For Codex heartbeat monitoring, create/update an app heartbeat automation and include the same plan rules in its prompt. Heartbeats may not guarantee local sound; use the script for reliable audible alerts.
7. Alert only when a trigger, near-trigger, invalidation, or market-filter risk appears. Keep quiet status short.

## Candle-Aligned Scheduling

- Separate the live-price layer from the closed-candle confirmation layer. Refresh mark price on every run, but only treat the latest fully closed candle as confirmation data.
- For monitors that confirm on `15m` candles and check every five minutes, align heartbeat runs to minutes `01,06,11,16,21,26,31,36,41,46,51,56` of each hour. This reads new `15m` candles about one minute after the standard `00,15,30,45` closes while preserving five-minute live-price checks.
- Between two `15m` closes, reuse the same closed-candle close, volume ratio, and taker-buy ratio; only live mark price and other live fields change.
- If exact minute alignment is unavailable, state the expected post-close delay and keep using the latest fully closed candle.

## Entry-Band States

- Use `PRICE_BREAK_ONLY` when live price crosses the trigger before a closed-candle confirmation.
- Use `OVEREXTENDED_LIVE` when live price moves beyond the entry-band ceiling before confirmation. Warn not to chase, but do not permanently invalidate the setup; allow a return to the entry band before candle close.
- Use `MISSED_ENTRY` only when the latest fully closed confirmation candle closes beyond the entry-band ceiling, or when a previously confirmed trigger is later observed outside the band without an allowed retest rule.
- Keep `TRIGGERED` dependent on the plan's closed-candle, volume, order-flow, market-filter, and current-entry-band requirements.

## Alert Levels

- `DONT_NOTIFY`: no meaningful trigger.
- `WATCH`: near a trigger or setup forming; optional soft sound.
- `ALERT`: trigger/invalidation/risk-filter condition met; use sound or text-to-speech if enabled.

Use a cooldown to avoid repeated alerts when price hovers around a level.

## ⚠️ 部署方式：必须用 Cron，禁止后台进程

**后台进程（terminal background=true / nohup）是 session_scoped，会话关闭（关网页、微信断开）进程就死。绝对不要用后台进程做长期监控。**

正确做法：用 Hermes Cron（no_agent=true, script 模式）每分钟调用单次检查：

1. 将计划 JSON 保存到 `~/.hermes/trading-plans/<SYMBOL>-plan.json`
2. 创建包装脚本 `~/.hermes/scripts/<symbol>-monitor-check.sh`：

```bash
#!/usr/bin/env bash
PLAN="$HOME/.hermes/trading-plans/<SYMBOL>-plan.json"
MONITOR="$HOME/.hermes/skills/auto-signal-monitor/scripts/signal_monitor.py"
[ ! -f "$PLAN" ] && exit 0
OUTPUT=$(python3 "$MONITOR" --plan "$PLAN" 2>&1 | grep -v "DONT_NOTIFY")
if echo "$OUTPUT" | grep -qiE "ALERT|TRIGGER|EXPIRED"; then
    echo "$OUTPUT"
fi
```

3. 创建 Cron：

```
cronjob action=create name="<SYMBOL> 价格监控" schedule="every 1m"
  script="<symbol>-monitor-check.sh" no_agent=true deliver=all
```

4. 验证：`bash ~/.hermes/scripts/<symbol>-monitor-check.sh`，未触发时应无输出（静默）

**Cron 由守护进程管理，不依赖任何会话，关网页/断微信都不影响。**

## Script Usage（单次检查 / 调试用）

单次检查（Cron 每分钟调用的就是这个）：

```bash
python3 ~/.hermes/skills/auto-signal-monitor/scripts/signal_monitor.py --plan ~/.hermes/trading-plans/BTCUSDT-plan.json
```

手动调试（加 --loop 只用于临时测试，不要用于长期监控）：

```bash
python3 ~/.hermes/skills/auto-signal-monitor/scripts/signal_monitor.py --plan ~/.hermes/trading-plans/BTCUSDT-plan.json --loop --interval-seconds 60
```

## Output Rules

When reporting a monitor setup, include:

- monitored symbol and direction
- exact trigger levels
- invalidation/protection levels
- market-filter condition
- alert mode: text only, beep, WAV, or speech
- clear reminder: no automatic execution

When an alert fires, keep it concise:

```text
UNIUSDT ALERT: 15m volume breakout above 3.00; BTC/ETH filter acceptable. Decision support only; manually confirm execution.
```
