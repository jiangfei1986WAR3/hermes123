# Diagnostic Details（诊断细节：持仓历史查询 + 架构说明）

从主 SKILL.md Quick Diagnostic 段拆出（2026-08-17 瘦身）。主文档保留诊断步骤 0-10；本文件是具体查询方法。

## Architecture Reassurance (user often asks "过期会不会影响持仓？")

Price monitor Crons and position management are **completely independent**:

| Component | Depends on | Affects |
|-----------|-----------|---------|
| Price monitor Crons (1m) | plan.json files | **Opening** new positions only |
| Core trading-cron.sh (配置1m/实际2m) | Exchange API (live positions) | **Managing** existing positions (TP1, breakeven, watch) |

Deleting expired monitor Crons or plan files has **ZERO impact** on existing positions. The core cron queries Binance directly — it never reads plan files for position management. Always explain this clearly when the user worries about cleanup affecting their trades.

## Checking Position History (TP1/TP2 partial fills)

When the user asks "did TP1 already fire?" or "was part of the position closed?" or "有没有减仓":

**Method 1: Binance trade history API (most reliable)**
```python
from binance_executor import api_get
from datetime import datetime, timezone
trades = api_get('/fapi/v1/userTrades', {'symbol': 'NEARUSDT', 'limit': 50}, signed=True)
for t in trades:
    ts = datetime.fromtimestamp(t['time']/1000, tz=timezone.utc)
    print(f"{ts:%m-%d %H:%M} | {t['side']:4} | qty:{t['qty']:>8} | px:{t['price']:>8} | pnl:{t.get('realizedPnl','0')}")
```
- `signed=True` is REQUIRED (400 error without it)
- SELL on a short = opening; BUY on a short = reducing/closing
- `realizedPnl` > 0 on a BUY (for shorts) confirms profitable partial close

**Method 2: Local execution history**
1. `python3 ~/.hermes/scripts/binance_executor.py positions` — current quantity vs original plan quantity
2. `cat ~/.hermes/trading-history/<timestamp>_<SYMBOL>.json` — execution record with original qty and TP levels
3. Compare: if current qty ≈ 50% of original → TP1 filled. If qty = 0 → fully closed (TP2 or SL)

**Method 3: Check Algo orders**
`get_open_algo_orders(symbol)` — if TP1 Algo order is gone from openAlgoOrders, it already executed

**Key insight**: position quantity reduction is the definitive proof of TP1 fill. The exchange Algo order executes independently of Hermes; the `watch` command detects the quantity change and notifies. But if the user asks before the next `watch` cycle, compare current qty against the execution history's original qty.

**After confirming a reduce, ALWAYS check for stale orders:**
```python
from binance_executor import get_open_algo_orders
algo = get_open_algo_orders('NEARUSDT')
# Verify: each order's quantity ≤ remaining position quantity
# If any order qty > remaining position → stale order, needs cancellation
```

**Breakeven exit (realizedPnl ≈ 0) is a NORMAL lifecycle step, not a loss** (verified 2026-08-01 ADA trade):
- Lifecycle: open 571 → TP1 fills (0.1764, +0.342U) → `manage_position` moves SL to entry (breakeven) → price drops back → breakeven SL fills remaining 286 @ entry price, `realizedPnl = 0`.
- When reading `userTrades`: a SELL at exactly entry price with `realizedPnl = 0` = breakeven exit after TP1. Report it as "保本离场" (protective breakeven worked), NOT as a stop-loss loss or mystery.
- This is the designed payoff of the TP1+breakeven system: TP1 profit banked, remainder exits free. Don't alarm the user over a PnL≈0 close.

## Single-pair cleanup after a position fully closes (EXITED)

- Delete `~/.hermes/trading-plans/<SYMBOL>-plan.json` + `<SYMBOL>-plan.state.json`
- Remove the symbol's monitor Cron (`cronjob action=remove`, name contains "价格监控")
- Archive the wrapper script: `mv ~/.hermes/scripts/<symbol>-monitor-check.sh ~/.hermes/scripts/archive/` (keep archive/ as the graveyard; scripts dir should only hold live monitors + executor + trading-cron.sh)
- Watch `write_file` sibling-modification warnings: another session (Web) may create/delete the same files — `rm` may report "No such file" because the sibling already removed it; that's fine, verify final state with `ls` instead of trusting the rm result.

## Pitfall: Stale Log Files
- `~/.hermes/trading-logs/signal-monitor.log` is written by the old `--loop` background process. After migrating to Cron, **this log stops updating**. Do NOT use it to judge whether monitoring is active. Check Cron output (`~/.hermes/cron/output/<job_id>/`) or `cronjob action=list` last_run_at instead.

## Hermes 版本升级后确认 (verified 2026-08-04)

用户升级 Hermes 后问"更新了什么/是否正常"，按此流程：

1. `hermes --version` 确认版本号 + `hermes version` 看 "Up to date"；升级日志 `~/.hermes/logs/update.log`（只有构建输出，无 changelog）
2. **查 changelog 的正确姿势**：本地安装目录是 git 浅克隆（`git log` 只有 1 条，无历史），不要浪费时间找本地 changelog。直接：
   ```bash
   curl -sL --max-time 20 "https://api.github.com/repos/NousResearch/hermes-agent/releases" -o /tmp/hermes-release.json
   # 解析 data[0].body（最新 release 正文，按 ## 分节）
   ```
   然后按**用户实际使用的功能**挑相关 section 总结（微信网关/Cron/DeepSeek模型/交易脚本），别整篇贴
3. **升级对交易系统零影响的三重确认**：①交易 skills 是用户级（升级日志 "Skills are up to date" 即未动）；②executor/monitor 脚本独立于 Hermes 版本；③Cron job 随 daemon 重启自动恢复——`cronjob list` 看 last_run_at 已到当前时刻即可
4. **升级后别误判计划消失为故障**：升级重启窗口内，计划可能因**失效线触发**被自动清理（2026-08-04 实例：SHIB/DOGE 22:33 失效清理，与升级无关）。先查 `grep -iE "计划失效|已清理" ~/.hermes/trading-executor.log` 确认时间线再下结论

### ⚠️ "Installed gateway service definition is outdated" 提示 (2026-08-04)

升级后 `hermes gateway status` 常见此提示。含义：systemd unit 文件（`~/.config/systemd/user/hermes-gateway.service`）还是旧版定义，新版 Hermes 自带更新的 unit。

- **处理：必须用 `hermes gateway restart`**（官方提示 "auto-refreshes the unit"），它会重装新版 unit 定义并重启进程
- ❌ `systemctl --user restart hermes-gateway` **不会**刷新 unit 文件（只重启进程），outdated 提示保留
- ⚠️ **重启后提示可能仍在（2026-08-04 实测）**：`hermes gateway restart` 日志出现 `Updated gateway user service definition to match the current Hermes install` 即定义已更新成功，outdated 提示是状态检测标志未刷新，属无害残留，下次升级/重启自然消失。别因提示仍在反复重启折腾——以重启日志那行为准，不看 status 提示
- 影响：不处理也能用（旧定义兼容运行），下次 `hermes gateway restart` 自动刷新；对交易系统零影响（独立脚本）
- 类比：门卫还在用旧版值班手册，需要重新上岗（重启）才换新手册
