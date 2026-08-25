---
name: trading-plan-format
description: 交易计划 plan JSON 格式规范与验证部署。生成 plan、排查监控不触发、建观察哨兵时用。
---

# Trading Plan Format & Deployment

用户交易系统 plan JSON 文件（signal_monitor → binance_executor 链路的输入）的格式规范、验证、部署与复盘数据拉取。与 trading-command-center / trade-execution-planner / auto-signal-monitor 配合，但本技能管"文件层"的硬约束。

## 规则类型白名单（引擎只认这 4 种，写错 = 死计划）

signal_monitor.py 的 `rules[].type` 只有以下 4 种，其他任何写法都会被**静默跳过**（监控照跑、永不触发、无任何报错）：

| type | side 语义 | 用途 |
|------|-----------|------|
| `breakout` | `above`=向上突破做多；`below`=向下破位做空 | 突破/破位触发（配 require_close） |
| `invalidation` | above/below | 计划失效条件 |
| `pullback_reclaim` | above/below | 回踩收复（需 pullback_low/high/reclaim_price/invalidation_price） |
| `market_filter` | 无 | 大盘过滤 |

❌ 坑（2026-08-06 TRUMP 例）：空单破位写成 `type:"breakdown"` → dry-run 报 `WARNING 未知规则类型 ... 已跳过`。空单破位正确写法 = `type:"breakout"` + `side:"below"` + `require_close: true`。历史 12 个空单计划（LINK/BTC/SUI/AVAX/TAO/UNI 等）全是 `breakout`+`below`，生成空单计划时参照历史模板，不要自创类型名。

⚠️ 失效线语义（用户确认 2026-08-06，勿改）：invalidation 保持 `require_close: false` 实时触发——宁可错杀不放过。8-06 ADA 案例：20:56 瞬时插针跌破失效线 0.1910 → 计划立即作废（executor 20:58 清理 plan），价格随后回到 0.1915 失效线上方。用户知情后明确选择保守（不改成收盘确认），未来不要"好心"把失效线改成 require_close:true。对照：breakout 触发线保留 require_close:true（收盘确认，用户偏好）。

## R 预检（出口任何触发/止损/TP 组合前必做，2026-08-06 ADA 例）

给用户的方案必须先验算 R 再出口：`R1 = (TP1 - trigger) / (trigger - stop)`，**TP1 ≥ 1.2R 才合格**（TP2 参考 ≥ 2R）。禁止随口报未验算的价位组合——8-06 ADA 例：出口"触发 0.1950/止损 0.1911/TP1 0.1964"实际 TP1 仅 0.36R，被用户事后抓包。R 不合格的候选宁可不建（标 WATCH_ONLY 写明复查条件），不要硬凑。常见 R 不合格场景：下方/上方目标空间不足（止损必须放结构位而目标太近，如 8-07 FIL/DOGE 破位空）、低价高波动币回踩止损 >1ATR 吃掉 TP1 空间（COTI 例）。

**浅止损救 R（2026-08-15 XMR 例）**：突破单第一阻力太近导致深结构止损（4h 低点）TP1<1.2R 时，先试浅止损——放在最近 1h swing low 下方（必须是真实结构位、不切穿价格行为；距离 ≥1× 该周期 ATR 防扫损）。XMR：触发 403.16/止损 398.4（07:00 1h 低点 398.34 下方，1.4×1h ATR）/TP1 408.97=1.22R ✅；若用 4h 低 394.6 做止损则 0.66R ❌。浅止损仍不达标 → WATCH_ONLY。贴线 R（1.2~1.25R）可建但输出时注明：突破市价单滑点会侵蚀 R（62 笔实盘不利滑点中位 0.165%、均值 0.275%，长尾可达 1%+；勿引用旧的"0.3-0.7%"口径），成交价上移后 TP1 可能实际 <1.2R——系统接受此风险（偏差门只挡偏离>止损距离的极端情况，不挡中间地带）。

## pullback_reclaim 实盘验证（2026-08-07 ENA 首例 ✅）

8-07 ENA 回踩计划完整走通全链路，是 pullback_reclaim 首次实盘开仓，参数模式可复用：

- 适用场景：突破刚发生但短线过热（ENA 突破 0.0938 后 15m RSI 75/4h 73）→ 不追突破，改建回踩计划
- 参数：pullback_low/high = 突破位上方（0.0940/0.0950）、reclaim_price = 突破位上方阻力（0.0955）、invalidation_price = 突破位下方（0.0928）；突破后上方无结构位时 TP 用 R 倍数（TP1≈1.1R/TP2≈2.2R 可接受）
- 结果：20:30 回踩收复触发 → 20:32 开仓 0.09551，**滑点仅 0.001%**（回踩类触发近限价成交，远好于突破市价单——后者 62 笔实盘不利滑点中位 0.165%、均值 0.275%）
- dry-run 时现价已在 reclaim 上方（0.0966）→ 静默正确（had_pullback 顺序判定拦"直接路过"），验证通过即可建
- 纪律：突破后超买时"建回踩计划"优于"等回踩 WATCH_ONLY"——系统替你蹲守，触发即执行

### pullback_reclaim 源码语义（2026-08-15 LINK 例，读 signal_monitor.py 确认）

- 规则字段（全在规则内）：`pullback_low/pullback_high/reclaim_price/invalidation_price` + `side` + `timeframe`；`require_close` 对 reclaim 判定无效——`reclaimed = 实时价 last ≥ reclaim 或 15m 已收盘 close ≥ reclaim`，实时摸到 reclaim 即触发
- `had_pullback`（做多）：closes20 里"最早收盘 ≥ reclaim 之后出现过收盘 < reclaim"才算真回踩，直接路过不触发（dry-run 静默的依据）
- `touched_zone`（源码）：`low20 <= pullback_high and high20 >= pullback_low`——近20根K线窗口内低/高触碰过区即算，**不是"当前价在区内"**。回踩/反抽发生在最近20根内（15m×20=5小时）→ 同参数重建大概率仍非静默，需换更深的区或等窗口滑出
- **深回踩静默构造（08-18 SOL 例 ✅）**：把 pullback 区设在 low20 最低点**之下**（近20根尚未触及的位置）→ touched_zone=False 强制静默，价格真回踩进区后才激活。SOL：现价 75.93、low20 最低 75.59 → 区设 75.30-75.45 → dry-run 静默 → 建 Cron 成功。选浅区（已被触及，靠 reclaimed=False 静默）还是深区（touched_zone=False 强制静默）取决于想等的回踩深度
- **"机会已完成"删计划后，若按现价追入 R 仍达标**（01:12 FIL 例：现价追入止损不变 TP1 仍 1.6R）：把"换参数重建可追"的选择权交给用户并给现价追入 R 数字，不自动建、不劝；用户答"算了不凑数"=接受放弃（用户定调 08-18）
- `reclaimed` 用 `lastClosedClose`（最近**已收盘**K线收盘价，未收盘K不算）：当前K线未收盘大跌时，上一根已收盘K仍可能满足 reclaimed → dry-run 瞬时 ALERT，当前K收盘后信号消失（2026-08-18 LINK 例：01:00 未收盘跌至 9.488 但 00:45 已收盘 9.558≥9.51 → 触发；FIL 例已收盘持久满足=机会真已完成）。dry-run 非静默先看当前K是否已收盘，再分"瞬时态"vs"机会已完成"（后者按验证拦截规则删）
- ⚠️ 规则内 invalidation_price 只在 pullback_reclaim 自身评估时检查：价格直接暴跌穿过失效线、未经历回踩流程时**不写任何事件**，plan 挂着不失效 → 回踩计划必须**额外加一条独立 invalidation 规则**兜底（LINK 例：规则内失效 9.20 + 独立 `invalidation` 9.20 below require_close=false 双保险）

### 空头镜像：反抽受阻空（2026-08-16 SUI 例 ✅）

side="below" 与回踩多同构，用于**破位空候选被禁手挡时的替代方案档**：

- 触发场景：直接破位空被判死刑（急跌超卖禁手 / TP1 贴前低 R<1.2 挤压）→ **必补验反抽空档再放弃**（8-16 上午窗口漏验此档、下午窗口补验建 SUI，被用户抓过一次）
- 参数模式：`pullback_low/high` = 阻力区（SUI：1h 阻力上方 0.6781/0.6797）、`reclaim_price` = 阻力位本身（0.6776，反抽后回落跌破=受阻确认）、`invalidation_price` = 更高档阻力上方（0.6822，= stop_loss）
- 语义：价格**先涨进 pullback 区**（超卖修复）→ 再回落跌破 reclaim 才触发；**不反抽直接阴跌则永不触发**（had_pullback 顺序判定）——"宁错过不追地板"是设计意图，输出时跟用户讲清
- 实盘结果（8-16 傍晚 SUI 全链路走通）：17:41 触发 → 17:43 开仓 -147.5 @ 0.6754，**滑点 -0.32%（空单向下滑=有利）**；executor 按实际入场平移挂单（SL 0.6822→0.68 / TP1 0.6713→0.6691 / TP2 0.663→0.6608，qty 73.7+73.7），R 距离不变——建计划→反抽→受阻回落→开仓→滑点校准平移全链路验证通过
- **止损结局（8-17 凌晨 SUI 同单）**：23:47 涨破 SL 0.68 止损，-0.69U（147.5×0.0046）。开仓后贴线挣扎 6 小时（三次逼近 SL 仅 0.27-0.35% 又回落）最终被扫——紧止损（结构逼出来的 1.8×ATR）被正常波动扫掉是**设计内代价**：赢 1.37R 赔率 / 输 0.69U 小亏快认错。输出时提前跟用户讲清"可能被扫，被扫=证伪点到了"，止损兑现后按同一口径复盘（不报怨"差一点"）
- R 验算顺序（SUI 8-16 三档全验）：①触发短线低点 0.6736 → TP1 贴 4h 前低 0.6713 仅 0.34% R 崩 ✗ ②触发 4h 前低 0.6713 + 贴阻力浅止损 → 1.14R ✗ ③反抽空 → TP1 1.37R / TP2 3.17R ✓
- 反例（KAITO 8-16，反抽空 1.65R 数值达标仍不建）：4h RSI **14.9** 历史极值 + funding 负 + TP1 对齐历史新低下方真空 → 反抽大概率变 V 反，"受阻回落"难成立 → WATCH_ONLY 带复查条件（4h RSI 修复 35+ 且反抽到阻力区再验）
- ⚠️ 用户刚在别的窗口删过同类型计划时，先问再建，不擅自重建（8-16 NEAR/DOGE 例）
- market_filter 自动跟随 `direction`：short → BTC/ETH 放量转强拦空单

## 触发质量三档（executor 偏差门行为，2026-08-07 用户问询澄清）

触发 ≠ 好入场。偏差门量化规则：**现价偏离触发价 > 止损距离 → 拒绝开仓**（executor 校验6，防暴涨追高）。三档：

| 触发时价格位置 | 系统行为 | 结果 |
|---|---|---|
| 贴触发价（理想） | 开仓，R 结构完好 | ✅ |
| TP1 附近（偏离 < 止损距离） | **开仓但 R 缩水**（滑点校准平移后 TP1 只剩 0.4R 级） | ⚠️ 中间地带不拦截 |
| 远超触发价（偏离 > 止损距离） | 偏差门拒绝，只留触发记录无持仓 | 🚫 放弃不追 |

例：ADA 触发 0.1948/止损 0.1911（距离 0.0037）——15m 收盘 0.1964 放行（偏离 0.0016，R 崩）vs 收盘 0.1990 拒绝（偏离 0.0042 > 0.0037）。解释"收盘站稳触发价"时用此表。

## executor 读取字段（写 plan 时必带）

signal_monitor 管触发（rules），binance_executor 管下单，两者读同一 plan 文件。executor 字段：

- `entry_trigger` 或 `entry.trigger_price`：触发价
- `stop_loss`、`take_profits`: [{price, reduce_percent}]（reduce_percent 默认 50）
- 方向校验：空单要求 TP < entry < stop；多单要求 stop < entry < TP（反了直接报错拒单）
- `expires_at`：ISO 时间戳（带时区，如 `2026-08-07T19:30:00+08:00`）；过期后 signal_monitor 写 PLAN_EXPIRED，executor 自动清理
- **不要写 quantity**：executor 按 margin(10U)×leverage÷entry 自算并取整（BTC 20x 其他 10x）

## 生成后必验证（建 Cron 前）

```bash
python3 /root/.hermes/skills/auto-signal-monitor/scripts/signal_monitor.py --plan ~/.hermes/trading-plans/<SYMBOL>-plan.json --dry-run
```

- 出现 "未知规则类型" 警告 = 格式错，修正后再建 Cron
- 静默（no trigger / DONT_NOTIFY）= 正常等待触发
- 触发已发生 = 按验证拦截规则处理（回踩/失效类 → 不建；突破类 → 正常建）

## Cron 部署要点

- create 时 `script` 参数必须用**相对 `~/.hermes/scripts/` 的文件名**（如 `bchusdt-monitor-check.sh`）；绝对路径直接报错 `Script path must be relative to ~/.hermes/scripts/`
- no_agent=true 交付语义：**非空 stdout 原样通知；空 stdout 完全静默；非零退出码发错误告警** —— 脚本里网络失败要 `exit 0` 静默，别让瞬断触发误报
- monitor-check.sh 第一行 `[ ! -f "$PLAN" ] && exit 0` 自我保护（plan 被删/失效后监控静默，不误报）
- **过期机制（用户常问"过期/作废什么意思"）**：`expires_at` 到了仍未触发 → 停止蹲守、executor 删 plan，零损失（没开仓=没成本）；不能续期，想继续必须重新走全流程（K 线会过期，结构要重新验证——类比超市优惠券有活动窗口期）。12h vs 24h 按 stability jaccard 定（名单跳 → 12h）。**读取位置**：扫描 JSON 根键 `stability`（jaccard/prevAt/added/dropped/warning；`warning:"名单跳变异常"` 即跳变 → 12h，prevAt 为对照的上一轮扫描时间）。跳变名单中新增/掉出的币本身即市场切换信号，建计划后提醒勿重仓；候选币**不在**跳变名单=稳定在榜，反而加分（2026-08-15 XMR 例：jaccard 0.435 跳变 → 12h，XMR 两次扫描稳定在榜 ✅）
- 计划失效时 executor 自动清理 plan 文件；监控 Cron 可留可删，脚本有保护不会误触发

## 观察哨兵模式（无 plan 的纯通知监控）

系统原生只有"plan 监控（触发→自动执行）"，没有"只通知不开仓"模式。盯非交易条件（反弹位、回踩位、费率极端）时建独立小脚本 + no_agent Cron：

- 脚本直查币安公开价对比观察位；**触发才 print（=通知），未触发零输出（=静默）**
- state 文件防重复通知：触发后写 `notified=true`；价格回落跌破重置线后复位，允许再次观察
- 与执行链路完全隔离（不 import binance_executor、不写事件文件），物理上不可能下单
- 模板：`templates/watch-sentinel.py`（复制改观察位/重置线/币种即可）
- 观察哨兵只提醒"该人工复查了"，复查后是否建 plan 是独立决策

## 清理五样

清监控 = 删 Cron + plan + state + 脚本 + 事件残留，缺一留残留。

## 复盘数据拉取（成交记录）

- userTrades 全量拉取必须**按天分片**（startTime/endTime 窗口过大直接 400），逐日循环拼接；`time` 字段是毫秒，事件/state 是秒
- 判断"真实成交"以 `realizedPnl != 0` 为准；日志"持仓变动"事件可能含认知操作（早期 bug 期开即平零盈亏单），统计盈亏/笔数别用日志口径
- 平仓成交常拆成同秒多条，按时间+symbol 聚合为一笔完整交易

## References

- `templates/watch-sentinel.py` — 观察哨兵脚本模板
