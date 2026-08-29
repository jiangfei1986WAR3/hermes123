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
   - `evaluate_market_filter`（源码 156-181 行）用**实时 last**，**非已收盘 close 确认**，会短线抖动误拦截；即"改 4h 收盘 close"待办升级点（暂缓未做）。方向语义**镜像对称**（源码 direction 参数）：拦空=last>MA25 且 last>open 且 volRatio≥配置（BTC/ETH 放量强势上涨）；拦多=last<MA25 且 last<open 且 volRatio≥配置（BTC/ETH 放量下跌）。多单 plan 的 market_filter 规则无需写条件方向——引擎按 plan 的 `direction` 自动选分支；08-29 SOL 回踩多按源码验证后部署
   - `pullback_reclaim` side=below（反抽空）的触发序列（源码 142-150 行 had_pullback 判定）：20 根窗口内须先有收盘 ≤ reclaim（首次跌破），再出现收盘 > reclaim（反抽），随后收盘 ≤ reclaim 才触发——「破位→反抽→再破位」三段，首个跌破收盘不触发（first_below > last_above）。破位发生在窗口外（>5h 前）时之前的反抽不算数，计划等**新的**跌破收盘+新反抽序列（TAC 08-29 建计划时 08:00 反抽已完成 3.5h，仍需等窗口内新序列）。touched_zone = low20 ≤ pullback_high 且 high20 ≥ pullback_low（窗口与带重叠即可，非要求触带）。建反抽空计划前 grep 源码核对序列，勿按直觉写触发条件
   - dry-run 输出 `WATCH: ...` 行（market_filter 评估记录）**不算不静默**：包装脚本 grep 只认 `ALERT|TRIGGER|EXPIRED|EVENT_WRITTEN|ERROR|WARNING`，WATCH 不入推送 → 可正常建 Cron。但它提示大盘过滤当前正在拦截（08-17 WLD 例：BTC 1h 放量下跌 → dry-run 报 `WATCH: 暂停WLD做多`，计划未失效，但大盘稳住前触发会被 filter 挡下——正是保护生效）
6. 有变动时：查成交记录 + `grep <SYMBOL> ~/.hermes/trading-executor.log` 交叉验证。调用：`api_get('/fapi/v1/userTrades', {'limit': 10}, signed=True)`（binance_executor **没有** get_client，直接 import api_get）；`t['time']` 是毫秒需换算

判断 plan 是否已开仓：plan.json 无 `actual_entry` 字段 = 未开仓（如 SOL 例）；state 文件为 `{}` = 该规则从未触发过；有 `actual_entry` 则开仓完成且 SL/TP 挂单应在位（`get_open_algo_orders` 应返回非空）

## 系统行为解读（看到这些不是故障）

| 现象 | 真相 |
|------|------|
| 挂单 SL/TP 价 ≠ plan 里的计划价 | executor 按**实际入场价平移**（滑点校准写回 plan），距离与原计划一致（如 1R/2R 保持）。正常 |
| 挂单 SL/TP 价 == plan 价，且 plan 带 actual_entry/slippage | **校准已写回的正常态**（勿误判"没平移"）：开仓后 plan 的 stop_loss/TPs 已是平移后值，与挂单一致=校准完成。复原平移前值：日志"入场偏差检查通过: 偏差 X ≤ 止损距离 Y"→ 原止损=触发价−Y；"滑点校准…平移 +delta"→ 原值=现值−delta（HYPE 08-17：触发59.3、Y=1.1→原止损58.2，TP 60.47/62.0 平移+0.133→60.603/62.133）。等距平移→开仓后 R=创建时 R |
| 日志大量"已有持仓，不重复开仓" | 开仓后监控 Cron 每冷却期（600s）重复检测到触发 → 安全门拦截。**正常**，证明 5 重门在工作 |
| 查状态时 plan 文件不见了 | 止损/平仓后 executor 自动"删 plan + 撤残留挂单"（日志：`已清理计划文件`/`已撤销残留挂单`）。正常，不是错误 |
| plan 没了但持仓/挂单还在 | 修复前=计划过期直接删 plan（XRP 08-08 例，过期只删 plan 文件，持仓与挂单保留）；**修复后：过期时有持仓 → plan 保留**（日志 `计划已过期但有活跃持仓，保留计划文件`），无持仓才删。仍见"过期+plan 没了+持仓在"=修复前遗留仓，建议手动补保本 SL |
| 部分止盈后 SL 数量≠剩余持仓（XRP 例：TP1 后 96.2→48.1，SL 仍 96.2） | **移保本断链**。移保本机制（见下节）**只对 plan 文件存在的币生效**；XRP 的 plan 08-07 22:00 过期被删 → 退出 manage 循环 → 01:00 TP1 成交后无人更新挂单。识别：SL triggerPrice=原止损位且 qty>持仓、`updateTime=createTime`（从未被改过）。reduceOnly 兜底：触发时按可平量成交=全平，不反向开仓，风控不裸奔；代价=已实现利润可能被反弹回吐。**已修（08-08）：过期有持仓保留 plan + XRP 手动补保本 SL 48.1@1.0368**；再遇=修复前遗留或 plan 被手动删 |
| 事件目录反复出现/清空 | signal_monitor 写事件 → executor process-events 处理删除。处理中拦截的事件也会被清 |
| 开仓滑点 | **禁凭印象报百分比**——先跑 `scripts/slippage_audit.py`。按多空方向校正：做多成交价高于触发价、做空成交价低于触发价才是不利滑点。整体分布只能作基准，必须单独核对当前交易：触发价、实际成交价、方向、slippage、写回后的 SL/TP，以及滑点折算吃掉的 R。FARTCOIN 2026-08-26 实例：0.2105→0.2139，+1.615%，为当时账本第2高；其写回止损未恢复原始结构位置，TP1 从约1.96R压缩至约1.32R，不能笼统说"平移后R不变所以影响不大"。SL/TP同步平移可能保留成交后距离，却可能把止损推入结构内部并抬高实际名义止损风险，详见 `references/entry-slippage-audit.md`。替代结算方案 D1（保留结构位+反推缩小仓位）与现状等距平移的 6 笔真实账本平行回测见 `references/d1-vs-shift-backtest-20260827.md`——结论"更稳非更优"，PROPOSED / NOT ACTIVE。用户问"收盘确认能否改实时"或"TP1 减半哪来的"，直接引用 `references/require-close-vs-live-trigger-20260827.md`（口径已与用户对齐，禁擅改触发哲学） |
| 余额变动核对 | 已实现盈亏 ≈ 余额变动（有浮仓时：余额变动 = 已实现 ± 浮亏变动）。如 ZEC 止损 -1.55U ≈ 余额 61.55→59.95。手算对不上时用 `api_get('/fapi/v1/income', {'limit': 100}, signed=True)` 拉 COMMISSION/FUNDING_FEE/REALIZED_PNL 一次闭合缺口（08-08 例：-2.86U 缺口 = 手续费 -1.41 + 资金费 -0.12 + 更早 HYPE 平仓 -2.29） |
| 日志报 `⚪ 已平仓` 且盈亏数字偏小 | **分类和金额都可能错，别按日志记账**：`detect_position_changes` 在下一轮 Cron（可延迟 ~60s）才发现持仓消失，用**当时 markPrice** 估算盈亏，不是成交价。CYS 2026-08-27 例：10:24:38 止损单成交 0.7571（写回止损 0.7604）真实 `realizedPnl -4.8421`，10:25:30 检测时价已反弹 0.7707 → 日志写 `⚪ 已平仓 / -3.10U`，既低估 1.74U 又没标 🔴 止损。**判定是否止损成交**：`api_get('/fapi/v1/allOrders', {'symbol':S,'startTime':start}, signed=True)` 见 `SELL MARKET` + `reduceOnly=True` + 成交价越过止损位 = 条件单触发（`/fapi/v1/algoHistOrders`、`/fapi/v1/algoOrders` 路径不存在会 404，历史条件单查 allOrders）。钱一律以 userTrades + income 为准 |
| state 出现 `market_filter` 记录 | market_filter 只是评估拦截记录（写 state、不写事件），**不代表计划失效**；计划继续监控，触发时若大盘过滤不满足会被挡。WLD 8-06 例：state 有 market_filter 记录、plan 文件仍在、dry-run 正常 |
| state 有触发记录但无持仓 | executor 入场偏差门拒绝（现价偏离触发价 > 止损距离，防暴涨追高，日志 `入场偏差过大`/`deviation_check REJECTED`）或 market_filter 拦截（`MARKET_FILTER_BLOCKED`）。**正常拦截，不是故障**；别误报"触发丢了" |
| 开仓成交但 R 结构缩水 | 偏差门阈值 = **止损距离**（非固定百分比）。三种突破质量（2026-08-07 用户问"15m 收盘在 TP1 附近会怎样"时确认）：①收盘贴触发价 → 开仓 R 完好（理想）；②收盘在 TP1 附近（偏离<止损距离）→ **会开仓**但盈利空间被吃掉大半（TP1 名存实亡，约 0.4R）——质量损失非故障；③收盘远超触发价（偏离>止损距离）→ 偏差门拒绝。滑点校准=等距平移，止损距离永不缩水 |

## 移保本机制（TP1 成交后 SL 移到入场价）

- 执行链：`trading-cron.sh` 每分钟 `manage` → `manage_all_positions` 遍历 PLANS_DIR 下所有 `*-plan.json` → `manage_position`：查 `openAlgoOrders`，**TP1 条件单消失 + SL 仍在原位** → 撤旧 SL → 挂保本 SL（triggerPrice=入场价、qty=剩余仓位）→ 撤未触发 TP → 按剩余仓位重挂（源码 ~603-720 行）
- **只对 plan 文件存在的币生效**：plan 过期被删（或手动删）后该币退出管理循环，TP1 成交后 SL 不移保本、不减量（XRP 2026-08-08 例，详见 `references/position-management.md`）
- `TP1_HIT` 事件分支（process_events ~753 行）全系统**无任何生成方**（signal_monitor 不写），死代码路径；移保本只走 manage 路径
- 验证移保本是否生效：`get_open_algo_orders` 看 SL——成功=新 algoId、triggerPrice≈入场价、qty=剩余仓位；未执行=updateTime=createTime（从未被动过）
- 区分"部分止盈通知"与"移保本"：日志 `🟡 部分止盈`（detect_position_changes，只通知不调单）≠ manage_position 的移保本日志 `TP1 已由币安执行，执行移保本`（08-28 HYPE 22:57 实测，该行紧随其后出现 🟡 部分止盈）。最终验证一律以 `get_open_algo_orders` 为准（新 algoId + triggerPrice≈入场价 + qty=剩余仓位）
- **提前移保本（不等 TP1）已被用户探讨并否定（2026-08-27）**：减半落袋是剩余仓位保本资格的"购票成本"，顺序不可拆；保本扳机只绑结构位（TP1=阻力簇下沿），禁绑算术浮盈金额（CYS 反事实：开仓后 04:00 回踩 0.7683 会被提前保本扫出、原止损 0.7604 活到今天）。"TP1 半仓是否覆盖止损"公式：半仓落袋=(TP1_R÷2)×止损额，覆盖条件 TP1≥2R。口径见 `references/require-close-vs-live-trigger-20260827.md`。手动提前减仓/移止损欢迎（用户操作者权限），系统不自动执行
- **TP1 半仓 vs 全平全账本回测（2026-08-28，用户拍板维持现状）**：40 笔触 TP1 交易 Σ实际 +101.61 vs Σ全平反事实 +99.71，差 +1.91U≈手续费量级；中位单笔全平侧略优 +0.34U、均值被 BEAT/WIF 极值主导且剔任一极值结论翻转 = 无稳定优势，半仓价值在剩余仓保本零风险而非期望收益。数据与口径见 `references/tp1-half-vs-full-backtest-20260828.md`
- **断链漏洞已修（2026-08-08）**：PLAN_EXPIRED 分支（process_events ~762 行）改为先查持仓——**有持仓 → 保留 plan 文件**（与 INVALIDATION 分支一致），无持仓才删；平仓清理照旧删 plan，不留僵尸。副作用：plan 保留期间 signal_monitor 每分钟重复写 PLAN_EXPIRED 事件（executor 幂等处理、不通知、不碰交易），观察确认无害即可。**2026-08-16 实测补充**：该副作用并非无声——监控包装脚本（`*-monitor-check.sh`）grep 到 EXPIRED 行 → no_agent Cron 非空 stdout → 每分钟尝试推微信 → 触发 iLink 限流（30s cooldown，挤占真实通知配额）。处置：过期后该币价格监控 Cron 已无入场监控职责，可停用（**保留 plan 文件**——持仓托管由事件处理 Cron 的 manage 负责，不受影响）。语义：**过期=停止入场监控（signal_monitor 只写过期事件不再评估规则），持仓托管（移保本/通知/清理）持续到平仓**。实测：有持仓保留/无持仓删除两场景 PASS；测试技巧=构造 plan 时 SL/TP 写**不匹配现有挂单的价格**，manage_position 对它会静默无害，防止测试窗口误碰真实挂单。**停用后验证托管链（08-17 XRP 例，用户会问"停了监控持仓没人管吗"）**：① `grep -n "def manage_all_positions" binance_executor.py` → 815 行起遍历 PLANS_DIR 所有 `*-plan.json`，plan 文件在=该币被照管；② 手动跑 `python3 binance_executor.py manage` 返回 `[]` = 正常覆盖、TP1 未到、无待办动作。事件处理 Cron 的限流报错在监控 Cron 停用后**自然消失**（EXPIRED 源头没了，trading-cron.sh 输出回空）；若停用后仍报限流=另有输出源，需另查。**过期处置实操节奏（08-29 WLD 第二例）**：计划 `expires_at` 到点前几分钟主动问用户/或到点后查 `cronjob list` 见 `last_delivery_error` 出现 iLink rate limited = EXPIRED 刷屏已开始（WIF、WLD 两例均在过期后 1-2 分钟内出现）；立即 `action=pause`（⚠️ `action=update` 传 prompt 不具备暂停功能，enabled 仍 true——暂停必须用 `pause` 动作，08-29 实测）。验证三件套：① 等 1-2 个 Cron 周期后 trading-events 目录清空；② 日志出现 `计划已过期但有活跃持仓，保留计划文件（移保本持续有效）`；③ 持仓与 SL/TP 挂单原样在位（交易所条件单独立执行，与本地监控无关）。停用价格监控后 executor 日志的"计划过期"行也不再新增（写事件的是 signal_monitor，源头已停）验证刷屏止住的口径（2026-08-27 WIF 实测）：pause 后 `cronjob list` 的 `last_delivery_error` 会继续显示最近一次限流报错——那是**停用前的历史快照，不是新故障**，勿重复排查；真判据是①等 1-2 个 Cron 周期后 trading-events 目录清空、②trading-executor.log 不再出现"计划过期"行、③后续 last_status 保持 ok 且无新增限流时间戳回答用户口径：入场监控（signal_monitor）与持仓托管（trading-cron.sh→manage）是**两条独立链**；SL/TP 是交易所条件单，独立于本地进程执行；停用只停"入场监控+过期刷屏"
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
5. 拉全量历史须**按天分片**:startTime/endTime 跨度过大 → 400;不带 startTime 只返回近期约 85 条。⚠️ **limit 不带 startTime = 从窗口最旧端截断**：userTrades 升序返回（旧→新），`{'limit':25}` 拿到的是近期窗口里最旧的 25 条——08-28 实盘例：查询结果最后一条停在 06:18，当日 12:14/15:13/18:10 的开仓全"消失"，极易误判为缓存/数据陈旧；实为截断非缓存（binance_executor 只对 symbol info 有 `_symbol_info_cache`，userTrades 无缓存层）。查当日或最新成交一律带 `startTime`。⚠️ **带 startTime 也照样从窗口最旧端截断**：升序返回下 `limit` 截的是窗口内最旧的 N 条——08-28 夜 23:12 查当日 HYPE TP1 成交，`{'startTime':当日00:00,'limit':10}` 拿到 00:31-15:13 的 10 条，22:56 的最新成交"消失"。**查最新几笔**：startTime 贴近目标时刻（前 10-30 分钟）或 limit 给足（≥50）

详见 `references/history-audit.md`（含 08-10 修正：旧"幻影单"判据对空单失效）与 `references/roundtrip-rebuild.md`（**首选方法**：userTrades 按 symbol+positionSide 重建 round trip + 闭合校验；重复计入/幻影判据/遗留仓三大陷阱）。

## 时间线还原技巧

一次触发会产生多个时间戳：事件写入（秒）→ executor 处理（日志）→ 成交（毫秒）→ plan 写回（mtime）。价格持续站触发价上方时，冷却期过后会**重复触发**写新事件——最早成交时间 + 最新事件时间不一致是正常的（安全门拦截了后续）。

⚠️ 时间换算踩坑（08-27）：本机时区=CST，`datetime.fromtimestamp(epoch)` 默认**按本地时区解释**——不要再手动 `+8*3600`（曾双重加 8 导致 K 线时间错位 8 小时、"开仓后最低点"误取开仓前触发 K 线的低点）。跨 API 比时间统一用 UTC epoch 毫秒直接比，不经时区字符串。

## 查历史交易的计划价格（plan 已删时）

用户问"这笔已平仓交易的触发价/止损价/实际开仓价是多少"时，plan.json 已被 executor 删，去 **trading-history 账本**（`~/.hermes/trading-history/YYYYMMDD_HHMMSS_符号.json`）找完整 plan 全文，不要在 plan 目录找。

⚠️ 账本 JSON 是双层嵌套：完整 plan 包在外层 `{"plan": {...}}` 里，所有字段都在 `.plan` 下——直接 `json.load(f).get('entry'/'stop_loss'/...)` 会静默全返回 None 不报错，先取 `data['plan']` 再读字段（2026-08-27 FARTCOIN 例）。

⚠️ 账本字段"写回后 vs 原始"的坑（2026-08-26 XMR 例）：
- `entry.trigger_price` = **原始触发价，不平移**，直接读（XMR 436.0）
- `stop_loss` / `take_profits` = **滑点平移后的值**，不是原始计划值（XMR 写回 429.78，原始 424.50）
- `actual_entry` = 实际入场价（XMR 441.28）、`slippage` = 滑点（+5.28）

反推原始值 + 三重印证：
1. 原止损 = 写回 stop_loss − slippage（429.78 − 5.28 = 424.50）
2. 原 TP = 写回 TP − slippage（等距平移）
3. 三重印证：原止损 = 触发价 − 止损距离（日志"入场偏差检查通过: 偏差 X ≤ 止损距离 Y"的 Y）= invalidation 规则 price（436 − 11.5 = 424.50 ✓）

同一币多笔交易时账本目录有多个文件（`cat *XMR*.json` 会拼出多个 JSON），按文件名时间戳对应到具体那笔（XMR 有 08-15 和 08-25 两笔，本次平仓的是 08-25）。

## 观察哨兵（无 plan 的观察位监控，2026-08-06 用户确认采用）

用户想"盯某个价格位置"但还不是可执行交易计划时（如等 XRP 反弹到 1h MA7 再复查是否转弱），用独立观察脚本 + no_agent Cron，**不走** plan/验证/executor 链路：

1. 写独立 Python 脚本（模板 `templates/watch-check.py`，线上参照 `~/.hermes/scripts/xrp-watch-check.py`）：现价 >= 观察位 → print 通知文本；否则**静默退出（exit 0 且无输出）**；state 文件防重复通知（触发一次后不再发）；回落跌破重置位自动重置，允许再次观察；API 失败静默（exit 0——no_agent 下非零退出会发错误告警）
2. 建 Cron：`no_agent=true`、`deliver=all`、`schedule="* * * * *"`（⚠️ **禁写 `every 1m`**——interval 型有 0.4s 锚点错位，实测真实间隔 120s 慢一倍，根因见 `references/cron-cadence-and-latency.md`）；⚠️ `script` 参数用**文件名**（相对 `~/.hermes/scripts/`），绝对路径会被拒绝；⚠️ 不要传 `repeat` 参数（传 `repeat='forever'` 报 TypeError `'<=' not supported between instances of 'str' and 'int'`），省略即默认 forever（2026-08-11 实测）
3. no_agent 交付语义：非空 stdout 原样发微信，空 stdout 完全静默——天然实现"触发才通知，不触发零打扰"
4. 触发通知后由用户决定是否进入正常 plan 流程；不用时删 Cron + 脚本 + state 三样

**观察列表演进方案（探讨中未实施）**：多观察位场景不建一堆独立哨兵，改用 `watchlist.json` + 单个聚合哨兵 + 每小时扫描更新（设计蓝图见 `references/observer-watchlist-design.md`，用户已认可方向，未写代码）。

## 遗留物识别

`~/.hermes/scripts/` 下无 Cron 调用、无 plan 的 `*-monitor-check.sh` = 死文件（脚本第一行 `[ ! -f "$PLAN" ] && exit 0` 自我保护，不会误触发）。清监控时脚本、plan、state、事件、Cron 五样一起清。

⚠️ **止损自动清理 ≠ 全清**：executor 止损/平仓后只删 plan.json + 事件 + 撤销挂单，**残留** state 文件 + 监控脚本 + 监控 Cron（ENA 08-08 例：止损后 state/脚本/Cron 仍在，用户要求清监控时手动补删）。故止损平仓 ≠ 清监控，两者要分清。**失效(invalidation)清理同理**：AAVE 08-11 例——涨破失效线 88.85 触发 invalid_8885，未开仓零成本出局，plan 被删但 state+Cron 残留（无害静默，可按需补清）

## 跨窗口/跨渠道结论对照（用户说"另一边结果不一样"时）

用户习惯微信/Web/TUI 多端对照。发现两端结论不一致时，先查证再归因，禁先辩护：

1. **先找另一边的记录**：`session_search` 发现模式——query 用"扫描 计划 达标"/"扫描 机会 计划"，`sort=newest`；browse 找最近活跃会话；再 `around_message_id` scroll 逐段还原：扫描时间、建了什么计划、用户后续动作（含删除）。超大结果持久化到 `/tmp/hermes-results/*.txt`，用 python `json.load` 提取 user/assistant 摘要再读。
2. **并排对比表**：两边扫描时间、大盘判断、每候选判定与计划，一列一边（脚本生成防错位）。
3. **根因三分类（诚实归因，优先认自己的问题）**：
   - 行情位移：两次扫描时间不同，RSI/价格已变，同一规则下结论自然不同
   - 会话隔离：各窗口聊天记录互不相通（memory/技能共享、聊天记录不共享）——另一窗口建/删过计划而本窗口不知道是正常的，如实说"当时不知道"
   - 自己漏了评估档：当场承认漏了哪一步（8-16 例：只验直接破位空、没验反抽空档），并立刻补验
4. **"不是 BUG"要用证据说**：确定性规则（禁手/R 门槛/大盘过滤）两边判定一致 = 系统没坏，才能说；禁止空口安慰。
5. **不重建用户刚在另一窗口删掉的计划**：先问，不自作主张。
6. **持仓 plan 的 R 门槛溯源**：发现持仓币 TP1 R<1.2R 时，先溯源建 plan 的会话（session_search 币名 → scroll 长会话至 plan created_at 时刻）查当时 R 计算原文再下结论；两种读法（机械 1.2R 门槛 / ZEC 先例"TP1 对齐第一阻力时非机械 1.2R、TP1 距≥止损距即可"）都摆给用户定口径，禁自行替用户判定（08-17 例：同日 TUI 00:50 否 WLD 1.03R、微信 12:16 放 HYPE 1.06R"压线"）。见 `references/cross-channel-reconciliation.md` 08-17 段
7. **用户让复核另一窗口建的 plan（不是结论打架，是主动核验）**：① session_search 找建计划会话——query 用**币名+触发价数字**（如 "SOL 104.45 回踩 收复 做多 计划"，纯币名搜不到时加价格数字），`sort=newest`，再 `around_message_id` scroll 到建计划时刻读当时的分析原文；② **独立复算五件套**（禁照抄原窗口声称）：fetch_klines 现结构、resistance_above/support_below 验 TP 锚是否真实 200 日簇、userTrades 验模式5（出场价 vs 现价的**方向**决定是否构成追高接回）、dry-run 验触发语义、R/数量/风险额 Python 复算；③ 输出复算表 + 瑕疵分级：**致命=改/删计划，不致命=维持+告知**；④ 默认不动另一窗口的 plan（除非用户明示）。四个高频复核发现见 `references/cross-window-plan-review-20260829.md`（TP1/TP2 同簇距离<1%=TP2 形同虚设、pullback_low 未被近期触碰=等新回踩的保守语义、原窗口的 ATR 缓冲表述可能对不上实际值——以复算为准、**TP 数组顺序=成交顺序/移保本扳机，TP[0] 必须距触发最近**——同日复核别窗口后本窗口自建又写反，两次教训定为复核必查项）

完整案例（8-16 两窗口 NEAR/DOGE 反抽空对比 + session_search 检索技巧）见 `references/cross-channel-reconciliation.md`。

## 流程完整性质疑应对（用户问"是不是偷懒跳过环节"）

用户会质疑"这轮跑得快/输出短=跳了环节"（8-16 已是第三次）。禁止空口保证，用证据回答：

1. 立即列本轮时间线：每步产出物自带时间戳（扫描文件名带时间、fetch_klines 输出"分析时间"、dry-run 的 UTC 时间戳、Cron ID、plan mtime）
2. 环节清单逐项对照：启动前检查 → 深扫（列全参数）→ 读结果 → fetch_klines（脚本在 `~/.hermes/skills/trading-analysis/scripts/`；`--json` 输出=**顶层 list**（[{symbol, analysis_time, timeframes:{15m,1h,4h,1d}, ticker_24h, funding, open_interest}]），每周期**扁平键** `current_price/ma7/ma25/ma99/ma_state/macd_dif/macd_dea/macd_hist/rsi/rsi_state/boll_upper|middle|lower/atr`，勿按嵌套 `close/ma/macd` 字典猜字段名，会读出全 None 浪费调用。⚠️ json 模式**缺**量比/主动买盘/支撑阻力/K线形态/区间高低（08-17 实测全 None）——完整分析须用**文本模式**（重定向 /tmp 文件，terminal `sed -n` 分段读，绕开 read_file 的 ANSI binary 判定））→ 禁手检查 → R 预检 → plan → dry-run → 脚本 → Cron
   ⚠️ fetch_klines.py 对非 ASCII 符号会崩（中文名币，08-28 龙虾USDT 例：`'ascii' codec can't encode characters`，URL 未做百分号编码）→ 改用 `binance_executor.api_get('/fapi/v1/klines', {'symbol': '<中文符号>', 'interval': '15m', 'limit': 100})` 手算 MA7/MA25/RSI/量比完成同口径分析（requests 自动处理 unicode）；扫描器本身能正常拉此类币，candidate-screening 的簇脚本同病
   ⚠️ **扫描器能拉到≠K线可分析（08-29 TUTU 例）**：个别币扫描结果正常但 klines/ticker 均返回 HTTP 400、exchangeInfo 仍显示 TRADING（疑似下架前/暂停状态）→ 该候选**数据不可得 = NOT_EXECUTABLE**，禁凭扫描器快照硬分析；`api_get` 直查复核一次即可定论，不用深挖
3. 速度合法来源说清：**同会话内前几轮已加载过的技能/参考文档可复用**——省的是文件读取时间，不是分析环节；候选币数差异、API 响应快慢也是因素。用户要求每轮强制重读技能文件时照做（多 2-3 分钟），由用户拍板
4. 若真漏了某步（只验一档触发位/漏反抽空档），当场承认+立刻补验，不混在"速度快"里蒙混

## 自动补丁通知解释（用户问"Self-improvement review: Patched SKILL.md 这是什么"）

用户看到自我改进 review 自动 patch 技能的通知时，会问机制/改了什么。应对：

1. 查证改动：`ls -la` 看 SKILL.md mtime；再 diff 备份仓库 `/root/hermes-backup` 同名文件（备份=上一快照，diff 即本次改动全量；git status 干净说明备份未同步，正说明改动是 live 目录新发生的）
2. 影响面分层：执行代码（executor/monitor/cron）零改动（mtime 不变）vs 技能文档只影响未来会话的分析/回答；规则阈值未被改
3. 逐条核对 diff 与近期对话一致（防夹带私货），引用对话里的具体数据佐证（开仓价/滑点/案例日期）
4. 提示：改动未进 git 备份仓库，push 前须用户说"推"才 push（用户惯例）
5. 机制定位：正是"只碰技能文档、不碰执行代码"的补丁动作——与用户之前"会不会偷偷改代码"的关切直接对应

### Memory updated 通知（用户问"又修改记忆了？？？"）

Self-improvement 也会改记忆文件 `~/.hermes/memories/MEMORY.md`（用户同样警觉，08-29 例）。应对：

1. 读当前 MEMORY.md，与**会话开头系统提示里的记忆快照**逐条 diff——通常只动 1 条；输出"27 条中仅 1 条改动 + 新旧对照全文"
2. ⚠️ **单位陷阱（08-29 被用户当场抓包）**：系统提示的"2,184/2,200 chars"是**字符**数，`ls -la` 显示的是**字节**数（UTF-8 中文 3 字节/字，2,200 字符≈4,200 字节）——两个单位禁混比，报"翻倍"前先用 `python3 -c` 算出真实字符增量（08-29 例：真实增量仅 +16 字符，我却报成"几乎翻倍"，错在拿字符数比字节数）
3. 用户说"改回"→ memory 工具 `action=replace`，old_text 用改动后条目全文、content 用会话开头快照原文，改完报 usage 应回到原值（如 2,184/2,200）
4. 内容核对防夹带：改动必须与近期对话逐条对应；无关条目一字未动要明说

## 复盘/规则建议产出

系统级复盘产出"闸门/过滤"类规则建议前，必须先用实盘账本回测，见 `references/rule-backtest.md`（08-10 例："弱市禁多"看似合理，回测显示被拦组 +8.45U → 否决）。阈值敏感性 + 单笔支配检查是必做项。
