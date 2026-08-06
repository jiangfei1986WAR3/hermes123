---
name: trading-system-status
description: 查用户交易系统监控和持仓状态时用。例行检查命令+系统行为解读+持仓变动交叉验证。
---

# Trading System Status Check

用户频繁查询"监控和持仓状态"（通常每小时多次）。按固定套路一次查完，不要漏项。

## 例行检查命令序列

1. `cronjob action=list` — 监控 Cron 是否都在（事件处理 + 每币一个价格监控）；`last_status: ok` 即健康
2. `ls ~/.hermes/trading-plans/ ~/.hermes/trading-events/` — plan 文件、state、待处理事件
3. `python3 ~/.hermes/scripts/binance_executor.py positions` + `balance` — 持仓与余额
4. 有持仓时：`get_open_algo_orders('<SYMBOL>')`（binance_executor 模块）确认 SL/TP 挂单在位。字段名是 `orderType`/`triggerPrice`/`quantity`/`algoStatus`——读 `type`/`stopPrice`/`origQty` 会全返回 None，误判挂单丢失
5. 无触发时：`python3 ~/.hermes/skills/auto-signal-monitor/scripts/signal_monitor.py --plan <plan> --dry-run`（引擎在 skills 目录，**不在** `~/.hermes/scripts/`）看现价 vs 触发价距离
   ⚠️ dry-run 若输出 `未知规则类型 '...' 已跳过`：signal_monitor 只认 breakout / invalidation / pullback_reclaim / market_filter 四类；空单破位规则必须写 `"type":"breakout"` + `"side":"below"`（写成 `"breakdown"` 会被静默跳过，计划永不触发，2026-08-06 TRUMP 例）
   计划形态规范：标准=单触发+失效线（一条 breakout + 一条 invalidation）。默认不写"突破+回踩"双触发（7-24~8-01 曾用，8-02 起收敛为单触发；回踩机会等价格企稳后单独建计划）。pullback_reclaim 的"现价已越过 reclaim=立即触发"陷阱已于 2026-08-06 修复（had_pullback 顺序判定，直接路过不再触发），双触发如需使用须先 dry-run 验证静默
6. 有变动时：查成交记录 + `grep <SYMBOL> ~/.hermes/trading-executor.log` 交叉验证。调用：`api_get('/fapi/v1/userTrades', {'limit': 10}, signed=True)`（binance_executor **没有** get_client，直接 import api_get）；`t['time']` 是毫秒需换算

判断 plan 是否已开仓：plan.json 无 `actual_entry` 字段 = 未开仓（如 SOL 例）；state 文件为 `{}` = 该规则从未触发过；有 `actual_entry` 则开仓完成且 SL/TP 挂单应在位（`get_open_algo_orders` 应返回非空）

## 系统行为解读（看到这些不是故障）

| 现象 | 真相 |
|------|------|
| 挂单 SL/TP 价 ≠ plan 里的计划价 | executor 按**实际入场价平移**（滑点校准写回 plan），距离与原计划一致（如 1R/2R 保持）。正常 |
| 日志大量"已有持仓，不重复开仓" | 开仓后监控 Cron 每冷却期（600s）重复检测到触发 → 安全门拦截。**正常**，证明 5 重门在工作 |
| 查状态时 plan 文件不见了 | 止损/平仓后 executor 自动"删 plan + 撤残留挂单"（日志：`已清理计划文件`/`已撤销残留挂单`）。正常，不是错误 |
| 事件目录反复出现/清空 | signal_monitor 写事件 → executor process-events 处理删除。处理中拦截的事件也会被清 |
| 开仓滑点 | 突破市价单正常 0.3-0.7%（如触发 57.25 成交 57.68）。SL/TP 同步平移，风控距离不缩水 |
| 余额变动核对 | 已实现盈亏 ≈ 余额变动（有浮仓时：余额变动 = 已实现 ± 浮亏变动）。如 ZEC 止损 -1.55U ≈ 余额 61.55→59.95 |

## 持仓变动必须交叉验证（勿单看持仓数量下结论）

持仓数量是"结果"，看不出"过程"（0.101 可能是原始仓，也可能是 TP1 减半后剩余）。判断任何变动：
1. `userTrades` 成交记录（时间/方向/数量/价格/realizedPnl）— 过程的直接证据
2. executor 日志（`处理触发事件`/`开仓完成`/`持仓变动: 🔴 已止损`）
3. plan 文件 mtime 与写回字段（actual_entry/slippage）
4. 事件文件 timestamp 与 state 文件（rule 触发 epoch 秒）

四者对得上才下结论。注意 `userTrades` 的 `time` 是**毫秒** epoch，事件/state 是**秒**，对照时先换算。

## 统计"完整交易"笔数(开→平计数)

用户问"总共完整交易了多少笔"时:
1. 开仓账本 = `~/.hermes/trading-history/*.json`(文件名 `YYYYMMDD_HHMMSS_符号`),executor 每笔"开仓完成"存一份;无对应平仓事件的开仓 = 在持
2. 最终平仓事件 = 日志 `持仓变动: 🔴已止损/🟢已止盈/⚪已平仓`(🟡部分止盈不算)
3. **日志事件 ≠ 真实成交**:早期系统(2026-07-22~08-03)有"幻影单"bug——开仓瞬间被同秒同量 pnl=0 的 SELL 对冲,executor 照记开仓/止盈/止损,资金零变动。只数日志会多报约 1/3
4. 真实成交以 `api_get('/fapi/v1/userTrades', signed=True)` 的 `realizedPnl≠0` 为准(BUY=开仓 pnl=0,SELL=平仓);某币 开数量=平数量 且 pnl 全 0 → 幻影单
5. 拉全量历史须**按天分片**:startTime/endTime 跨度过大 → 400;不带 startTime 只返回近期约 85 条

详见 `references/history-audit.md`(2026-08-06 审计:33 开 / 18 真实自动 / 12 幻影 / 2 手动 / 1 在持)。

## 时间线还原技巧

一次触发会产生多个时间戳：事件写入（秒）→ executor 处理（日志）→ 成交（毫秒）→ plan 写回（mtime）。价格持续站触发价上方时，冷却期过后会**重复触发**写新事件——最早成交时间 + 最新事件时间不一致是正常的（安全门拦截了后续）。

## 观察哨兵（无 plan 的观察位监控，2026-08-06 用户确认采用）

用户想"盯某个价格位置"但还不是可执行交易计划时（如等 XRP 反弹到 1h MA7 再复查是否转弱），用独立观察脚本 + no_agent Cron，**不走** plan/验证/executor 链路：

1. 写独立 Python 脚本（模板 `templates/watch-check.py`，线上参照 `~/.hermes/scripts/xrp-watch-check.py`）：现价 >= 观察位 → print 通知文本；否则**静默退出（exit 0 且无输出）**；state 文件防重复通知（触发一次后不再发）；回落跌破重置位自动重置，允许再次观察；API 失败静默（exit 0——no_agent 下非零退出会发错误告警）
2. 建 Cron：`no_agent=true`、`deliver=all`、`every 1m`；⚠️ `script` 参数用**文件名**（相对 `~/.hermes/scripts/`），绝对路径会被拒绝
3. no_agent 交付语义：非空 stdout 原样发微信，空 stdout 完全静默——天然实现"触发才通知，不触发零打扰"
4. 触发通知后由用户决定是否进入正常 plan 流程；不用时删 Cron + 脚本 + state 三样

## 遗留物识别

`~/.hermes/scripts/` 下无 Cron 调用、无 plan 的 `*-monitor-check.sh` = 死文件（脚本第一行 `[ ! -f "$PLAN" ] && exit 0` 自我保护，不会误触发）。清监控时脚本、plan、state、事件、Cron 五样一起清。
