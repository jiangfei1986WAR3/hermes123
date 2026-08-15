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
   2026-08-08 起引擎硬校验：plan 无/空 `rules[]` → stderr 报 `ERROR ... 缺少 rules 数组` + exit 2（包装脚本 grep ERROR 会推微信）。Cron 输出见此报错=死计划（常见于 Web 面板格式 `entry.trigger_price`+`monitor.*` 写法，HYPE 例），按标准格式重建即可
   计划形态规范：标准=单触发+失效线（一条 breakout + 一条 invalidation）。默认不写"突破+回踩"双触发（7-24~8-01 曾用，8-02 起收敛为单触发；回踩机会等价格企稳后单独建计划）。pullback_reclaim 的"现价已越过 reclaim=立即触发"陷阱已于 2026-08-06 修复（had_pullback 顺序判定，直接路过不再触发），双触发如需使用须先 dry-run 验证静默
   signal_monitor 规则语义（给用户讲 plan 操作场景分支时，必须按源码实际行为讲，别把能力说得比代码强——用户会逐条质问"这些 plan 都包含吗"）：
   - `min_volume_ratio` =「量比≥1.0＝不低于前20根均量」，是"防缩量破位"的弱保护，**不是"放量"**（放量通常量比>1.5）。别用"放量触发"这个词
   - `evaluate_market_filter`（源码 156-181 行）用**实时 last**（last>MA25 且 last>open 且 volRatio≥配置），**非已收盘 close 确认**，会短线抖动误拦截；即"改 4h 收盘 close"待办升级点（暂缓未做）
6. 有变动时：查成交记录 + `grep <SYMBOL> ~/.hermes/trading-executor.log` 交叉验证。调用：`api_get('/fapi/v1/userTrades', {'limit': 10}, signed=True)`（binance_executor **没有** get_client，直接 import api_get）；`t['time']` 是毫秒需换算

判断 plan 是否已开仓：plan.json 无 `actual_entry` 字段 = 未开仓（如 SOL 例）；state 文件为 `{}` = 该规则从未触发过；有 `actual_entry` 则开仓完成且 SL/TP 挂单应在位（`get_open_algo_orders` 应返回非空）

## 系统行为解读（看到这些不是故障）

| 现象 | 真相 |
|------|------|
| 挂单 SL/TP 价 ≠ plan 里的计划价 | executor 按**实际入场价平移**（滑点校准写回 plan），距离与原计划一致（如 1R/2R 保持）。正常 |
| 日志大量"已有持仓，不重复开仓" | 开仓后监控 Cron 每冷却期（600s）重复检测到触发 → 安全门拦截。**正常**，证明 5 重门在工作 |
| 查状态时 plan 文件不见了 | 止损/平仓后 executor 自动"删 plan + 撤残留挂单"（日志：`已清理计划文件`/`已撤销残留挂单`）。正常，不是错误 |
| plan 没了但持仓/挂单还在 | 修复前=计划过期直接删 plan（XRP 08-08 例，过期只删 plan 文件，持仓与挂单保留）；**修复后：过期时有持仓 → plan 保留**（日志 `计划已过期但有活跃持仓，保留计划文件`），无持仓才删。仍见"过期+plan 没了+持仓在"=修复前遗留仓，建议手动补保本 SL |
| 部分止盈后 SL 数量≠剩余持仓（XRP 例：TP1 后 96.2→48.1，SL 仍 96.2） | **移保本断链**。移保本机制（见下节）**只对 plan 文件存在的币生效**；XRP 的 plan 08-07 22:00 过期被删 → 退出 manage 循环 → 01:00 TP1 成交后无人更新挂单。识别：SL triggerPrice=原止损位且 qty>持仓、`updateTime=createTime`（从未被改过）。reduceOnly 兜底：触发时按可平量成交=全平，不反向开仓，风控不裸奔；代价=已实现利润可能被反弹回吐。**已修（08-08）：过期有持仓保留 plan + XRP 手动补保本 SL 48.1@1.0368**；再遇=修复前遗留或 plan 被手动删 |
| 事件目录反复出现/清空 | signal_monitor 写事件 → executor process-events 处理删除。处理中拦截的事件也会被清 |
| 开仓滑点 | 突破市价单正常 0.3-0.7%（如触发 57.25 成交 57.68）。SL/TP 同步平移，风控距离不缩水 |
| 余额变动核对 | 已实现盈亏 ≈ 余额变动（有浮仓时：余额变动 = 已实现 ± 浮亏变动）。如 ZEC 止损 -1.55U ≈ 余额 61.55→59.95。手算对不上时用 `api_get('/fapi/v1/income', {'limit': 100}, signed=True)` 拉 COMMISSION/FUNDING_FEE/REALIZED_PNL 一次闭合缺口（08-08 例：-2.86U 缺口 = 手续费 -1.41 + 资金费 -0.12 + 更早 HYPE 平仓 -2.29） |
| state 出现 `market_filter` 记录 | market_filter 只是评估拦截记录（写 state、不写事件），**不代表计划失效**；计划继续监控，触发时若大盘过滤不满足会被挡。WLD 8-06 例：state 有 market_filter 记录、plan 文件仍在、dry-run 正常 |
| state 有触发记录但无持仓 | executor 入场偏差门拒绝（现价偏离触发价 > 止损距离，防暴涨追高，日志 `入场偏差过大`/`deviation_check REJECTED`）或 market_filter 拦截（`MARKET_FILTER_BLOCKED`）。**正常拦截，不是故障**；别误报"触发丢了" |
| 开仓成交但 R 结构缩水 | 偏差门阈值 = **止损距离**（非固定百分比）。三种突破质量（2026-08-07 用户问"15m 收盘在 TP1 附近会怎样"时确认）：①收盘贴触发价 → 开仓 R 完好（理想）；②收盘在 TP1 附近（偏离<止损距离）→ **会开仓**但盈利空间被吃掉大半（TP1 名存实亡，约 0.4R）——质量损失非故障；③收盘远超触发价（偏离>止损距离）→ 偏差门拒绝。滑点校准=等距平移，止损距离永不缩水 |

## 移保本机制（TP1 成交后 SL 移到入场价）

- 执行链：`trading-cron.sh` 每分钟 `manage` → `manage_all_positions` 遍历 PLANS_DIR 下所有 `*-plan.json` → `manage_position`：查 `openAlgoOrders`，**TP1 条件单消失 + SL 仍在原位** → 撤旧 SL → 挂保本 SL（triggerPrice=入场价、qty=剩余仓位）→ 撤未触发 TP → 按剩余仓位重挂（源码 ~603-720 行）
- **只对 plan 文件存在的币生效**：plan 过期被删（或手动删）后该币退出管理循环，TP1 成交后 SL 不移保本、不减量（XRP 2026-08-08 例，详见 `references/position-management.md`）
- `TP1_HIT` 事件分支（process_events ~753 行）全系统**无任何生成方**（signal_monitor 不写），死代码路径；移保本只走 manage 路径
- 验证移保本是否生效：`get_open_algo_orders` 看 SL——成功=新 algoId、triggerPrice≈入场价、qty=剩余仓位；未执行=updateTime=createTime（从未被动过）
- 区分"部分止盈通知"与"移保本"：日志 `🟡 部分止盈`（detect_position_changes，只通知不调单）≠ `止损移到保本 ... ✅`（manage_position，真正调单）
- **断链漏洞已修（2026-08-08）**：PLAN_EXPIRED 分支（process_events ~762 行）改为先查持仓——**有持仓 → 保留 plan 文件**（与 INVALIDATION 分支一致），无持仓才删；平仓清理照旧删 plan，不留僵尸。副作用：plan 保留期间 signal_monitor 每分钟重复写 PLAN_EXPIRED 事件（executor 幂等处理、不通知、不碰交易），观察确认无害即可。语义：**过期=停止入场监控（signal_monitor 只写过期事件不再评估规则），持仓托管（移保本/通知/清理）持续到平仓**。实测：有持仓保留/无持仓删除两场景 PASS；测试技巧=构造 plan 时 SL/TP 写**不匹配现有挂单的价格**，manage_position 对它会静默无害，防止测试窗口误碰真实挂单
- 手动补保本 SL（用户要求时）：`api_delete('/fapi/v1/algoOrder', {'symbol':S,'algoId':旧SL algoId})` 撤旧 → `_place_conditional_order(S, 'BUY', 'STOP_MARKET', stop_price=round_price(S, 入场价), quantity=剩余, position_side='SHORT')` 挂新（XRP 08-08 例：撤 96.2@1.0523 → 挂 48.1@1.0368）

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

详见 `references/history-audit.md`（含 08-10 修正：旧"幻影单"判据对空单失效）与 `references/roundtrip-rebuild.md`（**首选方法**：userTrades 按 symbol+positionSide 重建 round trip + 闭合校验；重复计入/幻影判据/遗留仓三大陷阱）。

## 时间线还原技巧

一次触发会产生多个时间戳：事件写入（秒）→ executor 处理（日志）→ 成交（毫秒）→ plan 写回（mtime）。价格持续站触发价上方时，冷却期过后会**重复触发**写新事件——最早成交时间 + 最新事件时间不一致是正常的（安全门拦截了后续）。

## 观察哨兵（无 plan 的观察位监控，2026-08-06 用户确认采用）

用户想"盯某个价格位置"但还不是可执行交易计划时（如等 XRP 反弹到 1h MA7 再复查是否转弱），用独立观察脚本 + no_agent Cron，**不走** plan/验证/executor 链路：

1. 写独立 Python 脚本（模板 `templates/watch-check.py`，线上参照 `~/.hermes/scripts/xrp-watch-check.py`）：现价 >= 观察位 → print 通知文本；否则**静默退出（exit 0 且无输出）**；state 文件防重复通知（触发一次后不再发）；回落跌破重置位自动重置，允许再次观察；API 失败静默（exit 0——no_agent 下非零退出会发错误告警）
2. 建 Cron：`no_agent=true`、`deliver=all`、`every 1m`；⚠️ `script` 参数用**文件名**（相对 `~/.hermes/scripts/`），绝对路径会被拒绝；⚠️ 不要传 `repeat` 参数（传 `repeat='forever'` 报 TypeError `'<=' not supported between instances of 'str' and 'int'`），省略即默认 forever（2026-08-11 实测）
3. no_agent 交付语义：非空 stdout 原样发微信，空 stdout 完全静默——天然实现"触发才通知，不触发零打扰"
4. 触发通知后由用户决定是否进入正常 plan 流程；不用时删 Cron + 脚本 + state 三样

**观察列表演进方案（探讨中未实施）**：多观察位场景不建一堆独立哨兵，改用 `watchlist.json` + 单个聚合哨兵 + 每小时扫描更新（设计蓝图见 `references/observer-watchlist-design.md`，用户已认可方向，未写代码）。

## 遗留物识别

`~/.hermes/scripts/` 下无 Cron 调用、无 plan 的 `*-monitor-check.sh` = 死文件（脚本第一行 `[ ! -f "$PLAN" ] && exit 0` 自我保护，不会误触发）。清监控时脚本、plan、state、事件、Cron 五样一起清。

⚠️ **止损自动清理 ≠ 全清**：executor 止损/平仓后只删 plan.json + 事件 + 撤销挂单，**残留** state 文件 + 监控脚本 + 监控 Cron（ENA 08-08 例：止损后 state/脚本/Cron 仍在，用户要求清监控时手动补删）。故止损平仓 ≠ 清监控，两者要分清。**失效(invalidation)清理同理**：AAVE 08-11 例——涨破失效线 88.85 触发 invalid_8885，未开仓零成本出局，plan 被删但 state+Cron 残留（无害静默，可按需补清）

## 复盘/规则建议产出

系统级复盘产出"闸门/过滤"类规则建议前，必须先用实盘账本回测，见 `references/rule-backtest.md`（08-10 例："弱市禁多"看似合理，回测显示被拦组 +8.45U → 否决）。阈值敏感性 + 单笔支配检查是必做项。
