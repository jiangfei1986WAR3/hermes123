---
name: trading-ops-reliability
description: Operational reliability patterns for the user's live crypto trading system — Cron-based monitoring deployment, cross-session duplicate prevention, silence rules for notification scripts, executor behavior at trigger time, and exchange-hosted order safety. Load this skill whenever setting up, modifying, debugging, or explaining the trading system's runtime behavior (monitors, crons, executor, notifications).
---

# Trading Ops Reliability

用户实盘 Binance 合约交易系统的运维规则与检查单。执行链（Cron→executor）是纯代码、不读本文件；本文件服务于 agent 的部署、调试、解释环节。

**结构**：本文件只留规则与检查单。事故完整经过在 `references/incident-log.md`（一行一条，按日期排查）；系统架构在 `references/system-architecture.md`；条件单触发机制案例在 `references/conditional-order-execution.md`；服务器灾难恢复在 `references/server-disaster-recovery.md`。

## Monitor Deployment: Cron Only, Never Background Processes

- **NEVER** use `terminal(background=true)` or nohup for long-running price monitors. They are session-scoped — closing the web page, disconnecting WeChat, or ending the TUI session kills them silently.
- **ALWAYS** use Hermes Cron (`no_agent=true`, script mode) for monitoring. Cron is managed by the daemon and survives all session closures.
- Pattern: create a wrapper script (`~/.hermes/scripts/<symbol>-monitor-check.sh`) that runs `signal_monitor.py` in single-shot mode, filters DONT_NOTIFY lines, and only outputs on ALERT/TRIGGER/EXPIRED/**EVENT_WRITTEN**. Then create a Cron with `schedule="* * * * *"`, `no_agent=true`, `deliver=all`. **⚠️ Use the 5-field cron `* * * * *`, NOT `every 1m`** — interval-type schedules idle every other tick and actually run at 120s (see the cadence entry below).
- **⚠️ Verification/validation runs MUST use `--dry-run`**: `signal_monitor.py --plan <plan> --dry-run` evaluates but writes NO event files and NO state. Running it WITHOUT `--dry-run` for a "check" writes real TRIGGER events → executor opens a real position the user never asked for (BNB 08-03 实亏、XLM 08-05 复发，均见 incident-log). **验证 = 只跑 `--dry-run` 一条命令；monitor-check.sh 是生产通道，验证阶段碰都不碰。**
- **⚠️ grep MUST include `EVENT_WRITTEN`**: `grep -qiE "ALERT|TRIGGER|EXPIRED|EVENT_WRITTEN|ERROR|WARNING"`. Without it, the event-file-written confirmation line is swallowed.
- **⚠️ NEVER overwrite existing monitor-check.sh with `write_file`**: check `[ -f ... ]` first. If the file exists, it may contain fixes newer than the skill template. Only create from template when the file does NOT exist.
- **⚠️ Cron `script` param must be relative to `~/.hermes/scripts/`** — pass just the filename (e.g. `uni-monitor-check.sh`), NOT an absolute or home-relative path. The script file must already exist under `~/.hermes/scripts/`.
- `signal_monitor.py` without `--loop` runs ONE check and exits — correct for Cron usage. `--loop` only for temporary manual debugging.

### Cron 频率修改验证与描述同步（2026-08-04 实测）

- 改 Cron schedule 后**必须实测验证实际节奏**：看 `~/.hermes/cron/output/<job_id>/` 输出文件时间戳序列（连续 3+ 个文件间隔是否稳定），不能只信 `cronjob list` 的 next_run/last_run——那只是调度器视图。
- **schedule 类型决定真实节奏（2026-08-25 实测定根因 + 已修）**：`every 1m`（interval 型）实测真实间隔 **120s**，慢一倍且是 100% 必然空转——`compute_next_run` 把 next_run 锚在 `last_run_at`（=**执行完成**时刻，比 tick 起点晚 ~0.55s），而 ticker 周期实测 60.07s（每轮只多走 0.07s）→ 下一个 tick 永远差 ~0.4s 判定"未到期" → 跳过 → 120s。修法：schedule 改 5 字段 cron **`* * * * *`**，croniter 吸附到整分钟边界（比 tick 早 13s）→ 每轮必点火＝真 60s。**旧结论「实际节奏 ≈ 配置 + 1 分钟」是把这个 bug 当固有特性的误判，已作废。** 详见 trading-system-status `references/cron-cadence-and-latency.md`
- 秒级粒度物理不可达：`parse_duration` 无秒单位（`every 30s` 直接 ValueError），且 `TICKER_INTERVAL_SECONDS = 60` 无配置项可覆盖 → 每 tick 最多点火一次，60s 是硬下限。
- 频率加密安全前提：脚本耗时 << 周期（trading-cron 三步实测 0.556s）+ 操作幂等。满足则频率变化零风险、可一行回退。
- 频率与微信限流**无关**：iLink 限流看"发送次数"（事件时才输出），不看"检查次数"。
- 改频率后全库同步旧描述（中英文都搜：`每2分钟|every 2m|every 2 minutes|[23] minutes|3分钟|3-4 分钟`，覆盖 trading-command-center、trading-ops-reliability(+references/)、binance-executor、trading-cron.sh、binance_executor.py——脚本注释也算）。甄别三类命中：①过时描述→改；②**历史记录（bug/incident 描述）→不改**；③**规律说明→不改**。改完 `bash -n`/`py_compile` + 实跑一次 + 再 grep 复查 + 推 GitHub。
- 工具坑：V4A 多文件补丁对含中文 UTF-8 的 `.sh` 报 "Binary file" → 该文件改用 replace 模式单独 patch。

## Cross-Session State Conflicts (CRITICAL)

- WeChat, TUI, and Desktop are **independent sessions** sharing the same Cron scheduler and filesystem.
- **Before ANY action on the monitoring system** (restart, create, modify, kill), you MUST check what other sessions have done recently:
  1. `cronjob action=list` — what Crons exist right now
  2. `session_search query="监控 OR monitor OR cron OR 后台进程" sort=newest limit=3` — did another session change the architecture recently?
  3. `pgrep -af "signal_monitor"` — any background processes running? (there should be NONE)
- **Never restart a background process without checking Cron first.** Another session may have killed it and migrated to Cron. Restarting it re-creates the exact problem that session just fixed (07-22 实例见 incident-log)。

### Diagnostic Rule
- If `pgrep -af "signal_monitor"` returns a process AND `cronjob action=list` shows a monitor Cron for the same symbol → **the background process is stale/wrong**. Kill it, do NOT report "monitoring is running normally" based on the background process. The Cron is the source of truth.
- **Cron 全部消失时的诊断**：`cronjob list` 返回 0 个 job 时，用 `ls -la ~/.hermes/cron/` 看 `jobs.json`（空列表 68 字节）和 `executions.db` 的 mtime 推断清空时刻，再 `session_search` 找执行者（用户可能在其他会话执行了"清空所有监控和计划"——包括 trading-cron）。**trading-cron 也被删时**：若空仓+按用户计划"清仓后清空监控"则属预期，下次找机会时按新参数重建；若用户不知情需追查。重建用 `schedule="* * * * *"`（**禁用 `every 1m`**，见上节节奏根因），建后等 2-3 个 tick 看 output 目录时间戳验证节奏（应稳定 60s，不是 120s）。

## 分析流程完整性：trading-analysis 全量加载不可跳过 (2026-08-04)

扫描选币 → fetch_klines → **必须** `skill_view(trading-analysis)` **并并行** `skill_view` 其 3 个 reference（crypto-futures-system.md / entry-exit-position-management.md / volume-price-analysis.md）。主技能与 references 缺一 = 流程未完成（技能硬性规则）。

⚠️ **"上次会话加载过"不算数，本轮必须重新加载**（08-04 凭记忆分析、整批 LINK/LTC/AVAX 计划被清除的教训）。用户会主动核对流程完整性，宁可全清不冒险。

- Before creating a monitor Cron for any symbol, **ALWAYS** run `cronjob action=list` to check for existing monitors on that symbol.
- If a monitor already exists, tell the user — do NOT create a duplicate. Two monitors can write duplicate TRIGGER events.
- Also check `~/.hermes/trading-plans/` for existing plan files for that symbol.

## Silence Rules for Cron Scripts

- Cron scripts must produce **zero output** when nothing happens. Any stdout triggers a WeChat notification via `deliver=all`.
- Rule: if the script has nothing actionable to report, print nothing. Steady-state observations ("waiting", "already done") are NOT actionable — only state *transitions* produce output.（历史违规两次：manage 无持仓返回 check 动作刷屏、TP1 稳态每分钟报 tp1_pending，均已修，见 incident-log）

## No Re-Analysis at Trigger Time

- The executor's 5 checks are **data-sanity checks** (direction, market deviation <10%, notional ±15%, TP direction, stop distance <20%), NOT market re-analysis.
- At trigger: the system does NOT re-pull K-lines, re-evaluate trends, or check for flash crashes. Trigger + valid data = immediate entry.
- This is a deliberate user decision: small positions (10U margin), max loss ~0.75U per trade, speed matters for breakout strategies.
- If the user asks "will it re-analyze before entering?", answer honestly: NO.
- User considered adding 5m K-line confirmation but chose to run without it first, planning to add later if false breakouts become frequent.

## Notification Coverage (updated 2026-07-23)

| Event | WeChat notification? | Mechanism |
|-------|---------------------|-----------|
| Price reaches trigger | ✅ | Monitor Cron → signal_monitor ALERT → deliver=all |
| Open position success | ✅ | trading-cron.sh → executor output → deliver=all |
| TP1 reduce 50% + breakeven | ✅ | trading-cron.sh manage → deliver=all |
| Plan expired cleanup | ✅ | trading-cron.sh process-events → deliver=all |
| **Stop-loss hit (exchange)** | ✅ | trading-cron.sh `watch` → position snapshot comparison |
| **TP2 full close (exchange)** | ✅ | trading-cron.sh `watch` → position snapshot comparison |
| **TP1 partial (exchange)** | ✅ | trading-cron.sh `watch` → detects quantity reduction |
| **Manual close** | ✅ | trading-cron.sh `watch` → position disappeared |

`watch` 机制（快照对比、原因判定、TP2 自动重挂、窗口期三层保护、延迟数字）：**`references/watch-mechanism.md`**。要点：

- watch 每 ≈2 分钟对比持仓快照（`~/.hermes/trading-state.json`），只依赖"仓位在→不在"，不依赖回调/INVALIDATION 事件
- **Cleanup on position disappearance (all 4 steps, in order)**: 删 plan 文件 → 删该币全部事件文件 → **cancel_all_orders(symbol) 撤全部残留 Algo 单**（防旧 TP2 污染下一笔同币交易）→ 存空快照
- TP1 后 manage 自动撤旧 TP 单、按剩余数量重挂（保本 SL 确认挂上后才执行，best-effort）
- 最大通知延迟 ~2-3 分钟；TP1→保本损挂上 ~2-3 分钟（条件单单动作 + 保本价=入场价无法预挂）
- 窗口期三层保护：TP2 单 + 保本损（补挂）+ 原始止损（全程 reduceOnly 不反手）。最坏有界、概率极低
- 首次运行创建空快照，不误报

## Cleanup Procedure (user says "清掉所有监控和计划")

1. `cronjob list` → identify monitor Crons (name contains "价格监控" or script contains `monitor-check`)
2. Remove each monitor Cron (⚠️ NEVER remove `trading-cron.sh` event-processing Cron)
3. `rm ~/.hermes/trading-plans/*-plan.json *-plan.state.json`
4. `rm ~/.hermes/scripts/*-monitor-check.sh`
   ⚠️ 删 Cron 后必须核对三处：scripts 目录（monitor-check.sh 易漏删）、`*-plan.state.json`、以及 Cron 列表本身。逐一 `ls` 验证，别只信 rm 结果。
5. Verify: re-check Cron list + plans directory, confirm clean
6. Output report: what was deleted, what was preserved

## Exchange-Hosted Orders: Safety Net Status

- SL/TP orders on Binance servers protect positions even if Hermes dies.
- Conditional orders ARE placed via the Algo Order API (since 2026-07-23). Exchange-hosted SL/TP are active. Cron `manage` is a supplementary layer (TP1 reduce + breakeven move), not the only protection.
- Margin mode (isolated) and leverage are set per-symbol at order time, regardless of Binance web UI settings.

### ✅ Conditional Orders via Algo Order API

该账户条件单曾报 `-4120` 被误诊为账户限制——实为 Binance **2025-11 API 迁移**：条件单（STOP_MARKET, TAKE_PROFIT_MARKET, STOP, TAKE_PROFIT, TRAILING_STOP_MARKET）改走独立 Algo Order 系统；`/fapi/v1/order` 不再接受。MARKET 和 LIMIT 仍用旧端点。

**Correct endpoints (verified working on this account):**

| Action | Endpoint | Key params |
|--------|----------|-----------|
| Place conditional | `POST /fapi/v1/algoOrder` | `algoType=CONDITIONAL`, `triggerPrice` (NOT `stopPrice`), `positionSide=LONG/SHORT`, `workingType=MARK_PRICE`, `quantity` |
| Query open conditionals | `GET /fapi/v1/openAlgoOrders` | `symbol` (optional) |
| Query one by id | `GET /fapi/v1/algoOrder` | requires `algoId` or `clientAlgoId` |
| Cancel conditional | `DELETE /fapi/v1/algoOrder` | `symbol` + `algoId` |

**Critical differences from the old order API:**
- Param renamed: `stopPrice` → `triggerPrice`. Must add `algoType: "CONDITIONAL"`.
- Hedge Mode (this account is `dualSidePosition: true`): `positionSide` MUST be `LONG`/`SHORT`, never `BOTH` (BOTH → -4061). Infer from close direction: closing a long = `SELL` + `positionSide=LONG`.
- Response returns `algoId` (not `orderId`). Query results use `orderType` and `triggerPrice` fields (not `type`/`stopPrice`).
- Conditional orders are invisible to `GET /fapi/v1/openOrders` — that only lists normal orders. Use `openAlgoOrders` to see SL/TP.
- The path is `/fapi/v1/algoOrder` (camelCase). `/fapi/v1/algo/order` and `/fapi/v2/order` both 404.

**Required behavior:**
- After every `execute_plan()`, verify SL/TP step statuses (`algo_id` field). If ERROR, notify user to place manually in the Binance APP.
- To check SL/TP status, query `get_open_algo_orders(symbol)` — NOT `get_open_orders`.

## Conditional Order Trigger Mechanics (verified 2026-08-02)

When explaining why SL/TP filled late, early, or at a worse price, use these verified facts (details + case data: `references/conditional-order-execution.md`):

- **Trigger ≠ fill**: conditional orders fire in two steps — mark price crosses the trigger, then a MARKET order sweeps the book. Trigger price is a fuse, not a price guarantee.
- **Mark price shaves peaks, not speed**: trigger certainty depends on **overshoot**, not dwell time. >5% overshoot → mark crosses within the spike minute; <1% overshoot → mark may never reach the trigger.
- **Stop-loss slippage is structural**: market-stop guarantees exit, not price.
- **Reconstruct fill timelines** with `/fapi/v1/markPriceKlines` (mark candles → trigger minute), 1m last-price candles + executor log (watch detection lags fills by ≤3-4 min), and PnL reverse-calc when avgPrice is unknown.

### 用户问"价格到了止损价为什么没止损"排查 (verified 2026-08-03)

排查顺序（BTC 实例：last 插针 63052+ 用户以为该止损，实际止损已触发）：
1. **先查 `userTrades`**（signed, limit 5）——大概率已经触发了（平仓方向记录 + realizedPnl 负数）。用户通常是看到了触发前瞬间的盘面
2. 对比 `premiumIndex`（mark）vs `ticker/price`（last）：止损单 `workingType=MARK_PRICE`，last 插针 ≠ mark 穿过 → 晚触发是设计行为（防插针），不是故障
3. `openAlgoOrders(symbol)` 里止损单消失 = 已触发；残留 TP 单由 watch ≤2min 清理，等不及可手动 `python3 ~/.hermes/scripts/binance_executor.py watch` 立即完成清理（删 plan、cancel 残留单、更新快照；幂等安全）
4. 触发后到 Hermes 状态更新/通知有 ≤2-3 分钟延迟，期间用户查持仓"还在"属正常，不是没止损

## System Resource Impact

- Monitor Cron: ~0 disk growth per day (silent mode writes nothing unless triggered)
- Trigger event file: ~1KB per trigger; estimated annual growth <1MB
- CPU/memory impact: negligible (each Cron run is a single API call, <1 second)

## WeChat iLink Rate Limiting (notification loss risk)

The WeChat iLink gateway has a **30-second cooldown** between sends. When multiple Crons fire near-simultaneously, messages queue up and exceed the rate limit → **silently dropped with no retry**.

- 已发生多次（07-24 RE 4 连丢、08-01 ADA 保本通知丢两起，见 incident-log）。这是**持续性风险**，不是偶发。
- Check `cronjob action=list` → `last_delivery_error` field on the event-processing job when the user says "没收到通知".
- **Mitigation status**: 无修复。网关丢消息不重试。trading-cron.sh 已把三步批成一条输出，但不同币的独立 Cron 仍会相撞。
- **Practical impact**: After any trigger event, if the user doesn't receive a WeChat notification within 5 minutes, assume it was rate-limited. The position and orders are still correct on the exchange — only the notification was lost. User can always ask "帮我查下监控状态" to get current state.

## Binance Hedge Mode API Quirks (from 2026-07-22 code audit)

Hedge Mode（dual-side positions）下的参数冲突，ENA 实盘踩过（完整审计见 binance-executor 技能 references/code-audit-2026-07-22）：

| Error Code | Trigger | Fix |
|------------|---------|-----|
| -1106 | `reduceOnly=true` + `positionSide=LONG/SHORT` | **All `reduceOnly` removed from codebase.** Hedge Mode 下 `positionSide` 本身即表明减仓。Applies to: TP orders, TP1 partial close, CLI close. |
| -4120 | 条件单走 `/fapi/v1/order` | **NOT an account restriction** — 2025-11 迁移，用 `POST /fapi/v1/algoOrder` + `algoType=CONDITIONAL` + `triggerPrice`。见 Algo Order API 节。 |
| -4136 | `MARKET` + `closePosition=true` | MARKET orders must use `quantity`, never `closePosition` |
| -1102 | `STOP_MARKET` without `quantity` or `closePosition` | Must send one of them |

**Scientific notation trap**: Binance filter strings like `"0.0000100"` become `"1e-05"` via `str(float(...))` → `decimals=0` → prices/quantities rounded to 0. Always parse precision from the **original string**. `round_price()`/`round_qty()` 已修（从 `tick_str`/`step_str` 原始字符串解析）。

**Integer quantity**: When `stepSize="1"`, `round_qty()` must return `int`, not `float`. Binance rejects `1142.0` but accepts `1142`.

**`avgPrice` is null on market orders**: market-order 响应常返回 `avgPrice: null`。任何需要实际成交价的逻辑（如 Gate 7 校准）**必须** fallback 到 `get_positions()[symbol].entry_price`。`float(order.get("avgPrice"))` 会崩；`or 0` 保护会静默跳过逻辑。

**Post-execution verification**: After `execute_plan()`, check individual step statuses. `success` is conditional on SL placement — SL 失败则 executor 自动市价平掉新仓并返回 `success: false`。TP failures are tolerated (SL still protects).

**`round_qty` float truncation (FIXED 2026-07-28)**: `math.floor(qty / step + 1e-9) * step`（epsilon 防 IEEE754 边界误截断）。Also affects manage_position TP re-placement (`remaining_qty - allocated`) — truncation would leave dust positions that can never be closed.

## Rule ID Naming = Event Routing (CRITICAL)

事件分类**已改走显式 type 字段**（07-26 UNI 漏单事故后）：`evaluate()` 给每个事件附 `rule_type`，`write_event_file()` 按 `rule_type == "invalidation"` 分类，rule ID 可自由命名。

**Naming convention (secondary safety net, keep following):**
- Entry/breakout rules: `<symbol>_breakout_trigger`, `<symbol>_entry` — must NOT contain "invalid"
- Invalidation rules: `<symbol>_invalidation`, `<symbol>_invalid_<price>` — MUST contain "invalid"
- Market filter rules: level=WATCH (never writes event files), ID is free-form

**Durable lesson**: never classify logic branches by substring-matching a free-form ID string. Always route on an explicit type/enum field.

**Verification after this kind of edit**: walk EVERY rule type through the new path (breakout→TRIGGER, invalidation→INVALIDATION, pullback_reclaim→TRIGGER, market_filter→no event file)，并确认下游（executor）读的 event-file `type` 字段未变；确认编辑没删掉后续引用的变量。

## Volume Ratio Silent Bypass (CRITICAL)

`signal_monitor.py`'s `rule_volume_ok()` returns `True` when `min_volume_ratio` is absent from the plan's rules. A plan without this field triggers on price alone, ignoring volume entirely.

- **✅ 2026-08-08 起不再静默**：signal_monitor 硬校验 `rules` 为空/缺失 → stderr 报 `ERROR ... 缺少 rules 数组` + exit 2（包装脚本 grep ERROR/WARNING 会推微信）。干 plan（Web 面板格式 `entry.trigger_price`+`monitor.*`）见报错即按标准格式重建。该修复用 `sys.exit()`，目录/--loop 循环已加 `except SystemExit` 隔离（单个坏计划不拖垮其他）——**给引擎新增"终止类"异常时记得同步检查所有循环调用方的捕获**（SystemExit/KeyboardInterrupt 不被 `except Exception` 捕获）。
- **验证**: before deploying a monitor Cron, confirm the plan JSON has a `rules` array with `min_volume_ratio` set (breakout ≥ 1.0, pullback ≥ 0.8).
- The volume ratio is calculated **in real-time** at each check (current candle volume / avg of prior 20 candles), NOT from the analysis-phase snapshot.

### Plan Validation Checklist (run before creating monitor Cron)

When generating a plan via trading-command-center workflow, the plan JSON MUST contain:
1. `rules` array (NOT just `monitor.trigger_condition` string)
2. Each entry rule must have `min_volume_ratio` field
3. `require_close: true` for breakout/pullback entries (15m candle close confirmation)
4. `timeframe: "15m"` matching the monitor's check interval
5. **Rule IDs must follow naming convention** (see "Rule ID Naming" section)
6. **盈亏比检查**：Top候选全部完成 `fetch_klines` 和深度分析后，由 `trade-execution-planner` 用结构止损与真实目标统一验算R；本运维技能不在深度分析前粗筛或裁决候选。计划文件层仍须包含完整触发/止损/TP，R算术与门槛以 `trading-plan-format` 和planner当前规则为准。

**位置否决与分数无关**：`rangePos > 1`（或 < 0）= 现价已在近 20 根区间之外，配合双周期 RSI 极值 = 位置否决。**向用户说明被否候选的理由，不要静默丢弃**——用户会问"为什么不选分最高的"。

**名单跳变处理**：扫描器 `stability.warning`（jaccard 偏低）说明短线资金切换快 → 缩短 plan `expires_at`（jaccard 0.286 实例 → expires 定 12h 而非 24h）并在输出中提示。

**评分取向（用户问"为什么回踩机会分数低"时解释用）**：突破加分与回踩加分**互斥**——突破时站上全部短均线拿满基础分=70-86；回踩时跌破短均线丢基础分只剩回踩加分=50-60；空头侧**没有**回踩加分项 → 反弹空分数必然 <50。按分数选候选=自动过滤掉健康回踩机会；要抓回踩须主动筛 46-60 分区间"突破后回踩 MA25 缩量企稳"结构（流程层未定，探讨中）。

**判别维度④：空在修复段（2026-08-15 XRP/UNI 轮）**：4h/1h MACD 金叉红柱放大 = 短线反弹修复进行中，此刻追空 = 空在修复段，反弹随时延续。反弹空也要等反弹到阻力区（1h 阻力/MA25 区，XRP 1.006-1.009、UNI 3.31-3.35）遇阻转弱才建——**"等反弹到位"是时机问题不是结构问题，标 WATCH_ONLY 带复查条件，不追不建**。

**下跌末段市场画像（同轮）**：大盘偏空（BTC/ETH 双 SHORT_WATCH）但空头候选全部"贴前低+动能衰减+超卖边缘"、多头候选全部"顶到压力位"= 破位空间已释放大半，市场在等方向。此形态下多轮全 WATCH_ONLY 是正确结果，如实报告"下跌末段、等节奏"，别因大盘偏空就放松空单标准。

**现行顺序：分数达标 → 选择最多3个Top候选 → Top候选全部 `fetch_klines` + `trading-analysis` → `trading-candidate-screening` 只作历史风险复核 → `trade-execution-planner` 统一裁决并生成计划**。本文件只维护运行可靠性和plan部署检查，不再维护候选淘汰顺序。

**Quick validation command**:
```bash
python3 -c "
import json, sys
p = json.load(open(sys.argv[1]))
rules = p.get('rules', [])
entry = next((r for r in rules if r.get('id')=='entry_trigger'), None)
assert entry, 'MISSING rules[].entry_trigger'
assert 'min_volume_ratio' in entry, 'MISSING min_volume_ratio'
assert entry.get('require_close'), 'MISSING require_close'
print(f'OK: vol_ratio>={entry[\"min_volume_ratio\"]}, require_close={entry[\"require_close\"]}')
" ~/.hermes/trading-plans/<SYMBOL>-plan.json
```

If validation fails, regenerate the plan with the full `rules` array. Do NOT deploy the monitor with a price-only plan.

### pullback_reclaim 规则陷阱（✅ 2026-08-06 已修复）

`evaluate_pullback_reclaim()` 触发判断用**实时价**；曾有"现价已越过 reclaim = 建完立即触发"陷阱（变相追高/追空，AVAX/XLM 例见 incident-log）。要点：

- **修复**：`had_pullback` 顺序判定——做多要求"最早收盘≥reclaim 之后出现过收盘<reclaim"（真回落过），做空镜像反之。直接路过不再触发；真回踩照常触发
- 建计划后必跑 `--dry-run`；回踩类非静默 → 按验证拦截规则不建
- 正确构造"等反弹到位再触发"的空单：`pullback_low/high` 设在最近20根K线区间**之上**（touched_zone=false 保持静默，价格真反弹进区后才激活）
- pullback_reclaim 不走 `require_close`（用 last/lastClosedClose 双通道），别依赖 require_close 字段控制它
- ⚠️ "构造正确"≠必静默：**dry-run 是唯一裁判**，任何"应该静默"的预期都以 dry-run 输出为准；镜像陷阱两个方向都存在（现价高于 reclaim=追高，低于=追空）
- **建计划前的历史回踩也算数（2026-08-18 LINK 例）**：had_pullback 读 closes20 历史序列，不区分回踩发生在建计划前/后。建计划前 20 根 K 线内已有"收盘≥reclaim→收盘<reclaim"循环、且建计划时现价已收复 reclaim → dry-run 立即 ALERT（LINK：21:00 收 9.486 已回踩，00:08 建计划时 9.518 收复 → 触发）。非引擎 bug——是计划诞生晚了、回踩机会已实现；此时按现价追入 R 常缩水至 <1.2R（9.518 追 TP1 9.63 仅 1.14R）。处置：按验证拦截规则删计划；等价格再次落回 pullback 区再重建才有意义

## fetch_klines.py 输出含 ANSI 色码 → read_file 判定 binary（2026-08-06）

`trading-analysis/scripts/fetch_klines.py` 的 stdout 带终端色码，重定向到文件后 `read_file` 报 `Binary file`，剥掉色码后**仍可能**被判 binary（残留控制字符）。别卡在 `read_file` 上反复重试：

```bash
python3 ~/.hermes/skills/trading-analysis/scripts/fetch_klines.py \
  --symbols A,B,C --timeframes 15m,1h,4h,1d --bars 100 > /tmp/kl.txt 2>&1
# 用 terminal 分段读，绕开 read_file 的 binary 判定
sed -n '1,110p' /tmp/kl.txt     # 第一个币
sed -n '111,321p' /tmp/kl.txt   # 其余
```

先 `wc -l` 拿总行数再决定分段边界。3 个币 × 4 周期约 320 行，两段读完。

## Config Change Audit Procedure (MANDATORY before any config change)

改 `trading-config.json` 任何值前的强制审计——完整流程 + max_positions 9 处位置清单 + 行为规则陷阱：**`references/config-audit.md`**。

要点（细节见 reference）：①三种形态全 grep（snake_case + 中文散文 + ⚠️英文散文 "max positions (N)" 无下划线，漏掉会静默跳过 binance-executor/SKILL.md）；②命中分四类——功能代码（动态读配置）不改、注释/文档改文字、**行为规则必须重写逻辑不是换数字**；③改前把分类清单给用户看（用户明确要求此步）；④永不凭记忆说"N 处"；⑤用上次同值变更的 git diff 交叉验证。
## Plan-Layer Duplicate Problem (user decision 2026-07-24: NO automated fix)

重复扫描可能：同币 plan 被静默覆盖、同币重复监控 Cron、扫描轮次间无全局协调。

**User's chosen mitigation**: say "清掉所有监控和计划" before each scan run. 刻意的简单性取舍——用户对技能复杂度的担忧大于偶发的手动清理。

**Do NOT add automated pre-scan checks to Skills unless user explicitly asks.** 执行层硬锁已防超开仓；plan 层混乱烦但不危险。

## Backup & Restore

1. Copy `~/.hermes/skills/<trading-skills>/` and `~/.hermes/scripts/` to a temp dir
2. **Never** include `trading-config.json` (contains API keys) or `trading-events/` (transient)
3. `trading-plans/` CAN be included (no secrets, useful for restoring active monitors after migration)
4. **Path quirk**: `binance-executor` 和 `trading-ops-reliability` 在 `skills/trading/` 子目录，不在 skills 根。restore 脚本必须处理
5. After restore: manually configure API keys + rebuild Cron jobs (ask Hermes "帮我重建交易监控 Cron")
6. Current backup repo: `github.com/jiangfei1986WAR3/hermes123`
7. **Local clone**: `/root/hermes-backup`（2026-08-15 起永久位置；**不要再用 `/tmp/hermes-backup`**——/tmp 重启即清空）。re-clone: `git clone git@github.com:jiangfei1986WAR3/hermes123.git /root/hermes-backup`
   - ⚠️ **remote 必须用 SSH 格式**（`git@github.com:...`）。HTTPS push 会 `could not read Username`（本机无 credential helper，但 SSH key 已绑定）。误用 HTTPS：`git remote set-url origin git@github.com:...` 一行改回
   - 重 clone 后 commit 前必须配身份：`git config --global user.name jiangfei1986WAR3 && git config --global user.email jiangfei1986WAR3@users.noreply.github.com`
   - commit 报 `invalid object ... Error building trees` = 本地对象库损坏，删掉重 clone 最干净
8. **Sanitized config backup**: `config/trading-config.example.json`（API key 用占位符）。改配置后重新生成 example，never copy the real config.
9. **推送纪律**：仓库是**快照**——含过时 plan、archive 脚本、技能自动更新的文档，生产与仓库大量差异属常态。推送前先 `diff -rq /root/.hermes/<dir> /root/hermes-backup/<dir>` 摸清差异面，**只 cp+git add 本次有意修改的文件**；无关差异留待下次自然带上。commit message 写清修复内容+根因+影响面。
   - **推送内容三档分类（08-18 实践，用户问"推送哪些合适"时照此答）**：①必推——新技能（唯一副本在 live，丢了就没了）、技能文档补丁（实战教训）、新监控脚本；②顺带推——**持仓中币的 plan.json**（含 actual_entry 校准记录，是持仓托管依据，服务器恢复时让移保本/通知链继续工作；推一次=快照，之后移保本写回有差异属正常）；③不推——`*-plan.state.json`（瞬时状态每分钟可变，无快照价值）、历史遗留死脚本（备份已有，不重复动）。盘点时给用户"必推/顺带推/不推"三档清单让用户拍板
   - **长期未推后的全量重同步**：先 `diff -rq` 出差异清单 → **先给用户看分类盘点、等用户明确说"推"才 push**。盘点必须分类（核心代码/技能文档/脚本/plans），不能只报原始数字——大头常是 Hermes 官方内置技能随版本升级自动更新（与交易无关）。全量同步：`rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='.curator_backups' --exclude='*.bak*' ~/.hermes/skills/ /root/hermes-backup/skills/`（scripts/ 同理），再 git add -A + commit + push。rsync 不带 --delete（仓库多出的历史快照无害）
   - ⚠️ **空目录陷阱**：git 不追踪空目录。对比顶层目录名会把生产里的**空壳目录**显示为"新增技能"。**按文件数核实**（`find <dir> -type f | wc -l`）或 `git show --stat <commit> | grep <name>`。查"某技能是什么/何时合并"用 `git log --oneline -- <path>` + `git show <commit>`

## Known Unfixed Items (user explicitly deferred — Do NOT proactively fix)

User reviewed all items and said: "先不用优化 等真的遇到以后再说". **Only fix if the user encounters the actual problem and asks.** 已修复 BUG 的完整档案在 `references/incident-log.md`。

- **P1: Plan File Not Deleted After Opening (BY DESIGN 2026-07-28)**: execute_plan 不删 plan 是**故意的**——INVALIDATION 再修复需要持仓期间 plan 存在（manage 移保本 + watch 判断通知类型都读它）。plan 由 watch 在仓位消失时清理（≤2min）。理论竞态（平仓后 watch 前残留 TRIGGER 重开）被"已有持仓"检查挡住。**Do NOT "fix" this by deleting the plan file after opening** — 会破坏移保本和通知准确性
- **P1: Cooldown Not Set in Generated Plans**: 缺 `cooldown_seconds` 时每分钟写 TRIGGER（持仓检查挡住重开，但浪费+堆事件）。Fix approach: 生成时强制 `cooldown_seconds: 600`
- **P2: Event Consumed on Execution Failure**: process_events 无论成败都删 TRIGGER 事件，开仓失败则机会永失。Fix approach: 仅 success=True 才删，失败留下重试（加最大重试计数）
- **P2: Two Position-Sizing Models Inconsistent (DEFERRED 2026-07-28, user decision)**: plan 层固定风险模型 vs executor 固定保证金模型（executor 忽略 plan.risk.quantity）。用户决定加本金时一起重设计，重议时推荐 Option C（固定风险+名义上限）
- **P2: Position-Full Queue Spam (user chose MANUAL 2026-07-26)**: 满仓时待触发监控持续写 TRIGGER（executor 拦截）。用户选手动"清掉没触发的监控和计划"。**Do NOT auto-clean monitors on position-full unless user explicitly asks.** Gate 6 偏差门已兜底危险情形（排队漂移>止损距离→拒开仓），现在只是烦不是险

## Pending Features (NOT implemented — do not build without explicit approval)

- **Auto-Scan Scheduler**（07-24 设计定稿，用户"后期再实现"）：每 2h 检查"有持仓 OR 有 plan 文件？"→ 都没有才跑完整扫描流程。**Critical: gate on plan FILES, NOT on Cron list**（过期监控 Cron 是僵尸，查 Cron 会永不触发）。扫描前清僵尸监控 Cron；BTC/ETH filter 不过则整轮跳过。开关：对话式 pause/resume + config `auto_scan` 双保险。待拍板：时段限制？无机会时静默还是通知？实现形态倾向轻量脚本预检+按需起 LLM 会话
- **Web 交易面板**（08-03 用户 DEFERRED："系统稳定盈利前不做，锦上添花"）。**别主动推销**。开工要点：独立 FastAPI 旁路服务（`~/.hermes/trading-web/`），只读 trading-plans/ + 子进程调 executor，零侵入现有链路；用户已接受"方案 A：解析文本输出，零改动"。待拍板：访问范围/找机会按钮确认步/盈亏曲线

## Multi-Bug-Fix Rigor Protocol (MANDATORY for trading system code changes)

User explicitly demands: "严谨 不能因为修改这个问题引入新的逻辑BUG". 完整协议在 **`references/code-change-protocol.md`**，改代码前必读。

三大块：①Per-Fix Protocol（枚举调用方→最小补丁→5+场景走查→单元级测试（含"临时 plan 故意写不匹配价防误撤真实挂单"安全技巧）→真实历史数据验证→全 plan dry-run 回归→文档同步→推送核对）；②Cross-Fix Verification（重读全文、两两交叉检查假设依赖、⚠️新异常类型 vs 调用方 except——except Exception 接不住 SystemExit、全生命周期走查）；③User Communication（类比先行、探讨先于写码、严重度如实报、表格追踪、改文档先交代性质、结论附可验证证据链、两类流程质疑的固定应对）。
## Post-Restart Health Check (网关/Hermes 重启后, verified 2026-08-03)

用户重启网关或更新 Hermes 后问"是否正常"，按此顺序查：

1. 进程：`ps aux | grep -iE "hermes|gateway"` + `systemctl list-units --type=service --state=running | grep hermes` + `ss -tlnp | grep 18789` — dashboard + gateway 都要在
2. `cronjob action=list` — **关键**：看 `last_run_at` 已恢复到当前时刻（调度器随 daemon 重启，必须确认 tick 恢复）
3. `tail ~/.hermes/logs/gateway.log` — 确认 `✓ weixin connected`（iLink 重启后第一条通知可能被 30s 限流吃掉，属正常）
4. 持仓/挂单在交易所侧，重启不影响：`positions` + `get_open_algo_orders` 复查数量即可
5. 日志扫描 `grep -iE "error|traceback" ~/.hermes/logs/*.log` — 区分真故障与无害项：dashboard 启动期 sqlite schema 竞态（自愈）、auxiliary 备用模型无 credit（预存状态）、tools.registry check_fn False（未配置项）都不是故障

Hermes 版本升级后确认流程 + "Installed gateway service definition is outdated" 处理（必须 `hermes gateway restart`；以重启日志为准不看 status 提示）：**`references/diagnostic-details.md`**。

## Server Health Check（用户问"服务器是否健康/整体状态"时）

1. 资源：`uptime`（8 核时负载 <1 健康）+ `free -h` + `df -h /`（可用 >20% 健康）
2. 服务：`systemctl list-units --type=service --state=running | grep -iE "hermes|cron|nginx"`
3. 网络：`curl -s -o /dev/null -w "%{time_total}" https://fapi.binance.com/fapi/v1/ping`（<1s 正常）
4. 日志错误分类（**计数高 ≠ 故障**）：`grep -cE "ERROR|Traceback" ~/.hermes/logs/*.log` 后，先用 `sed` 提取模块名再 `uniq -c` 分组看类型。本系统 ERROR 绝大多数是 `gateway.platforms.weixin: iLink sendmessage rate limited`（30s 冷却，丢通知不丢交易，已知无害）——若 100% 是它，服务器判定健康
5. 判定表：CPU/内存/磁盘/服务/网络全绿 + 错误全部为微信限流 = 健康，直接报结论，不用让用户担心日志数字

## Quick Diagnostic Checklist

When the user asks "is the monitor running?" or "check the system":

0. `session_search query="监控 OR monitor OR cron" sort=newest limit=3` — check if another session changed the architecture recently (PREVENTS conflicting actions)
1. `cronjob action=list` — verify monitor + event-processing Crons are enabled and running
2. `curl -s "https://fapi.binance.com/fapi/v1/ticker/price?symbol=<SYMBOL>"` — current price
3. `cat ~/.hermes/trading-plans/<SYMBOL>-plan.json` — plan details + expiry
4. **Cross-reference plan `expires_at` with running monitor Crons.** If all plans are expired but monitor Crons still run → harmless zombies (exit silently every minute). Tell the user and offer to clean them up. Same for **missing plan file entirely** (wrapper's `[ ! -f "$PLAN" ] && exit 0` makes it a silent zombie)
5. `pgrep -af "signal_monitor"` — should return NOTHING (if something shows up alongside a Cron, the process is stale — kill it)
6. `ls ~/.hermes/trading-events/` — should be empty unless a trigger just fired
7. **Check SL/TP orders for each open position**: `get_open_algo_orders(symbol)` — if ZERO orders exist, the position is unprotected ("裸奔"). Flag this to the user immediately and offer to re-place SL/TP.

   ⚠️ **NEVER use `/fapi/v1/openOrders` or `/fapi/v1/allOrders` to check SL/TP status.** These endpoints ONLY list normal orders. Algo conditional orders are **completely invisible** to them — they will ALWAYS return 0 for SL/TP. Using them leads to the false conclusion "no orders were ever placed" (07-30 误判事故，见 incident-log).

   **Correct check**: `python3 ~/.hermes/scripts/binance_executor.py positions` then for each symbol: query `GET /fapi/v1/openAlgoOrders?symbol=<SYMBOL>` (signed), or use the executor's `get_open_algo_orders(symbol)` helper.

   **核对保护单价格**: executor 挂单用「实际成交价 ± 计划距离」，不是计划绝对价。核对公式：SL ≈ 实际入场 + (计划SL − 计划触发价)，TP ≈ 实际入场 − (计划触发价 − 计划TP)。读 openAlgoOrders 的 `triggerPrice` 字段（`stopPrice` 恒为 null，字段名踩过坑）。

   **⚠️ Account 查询 endpoint 是 v2**：`GET /fapi/v2/positionRisk`、`GET /fapi/v2/balance`；`/fapi/v1/positionRisk` 返回 404。手写查询一律复制 executor 的 v2 路径，或直接复用 `binance_executor.py positions`。

8. **状态汇报前对每个活跃 plan 跑一次 `--dry-run`**（只评估不写事件）：输出 DONT_NOTIFY = 监控静默等待中（健康）；出现 ALERT/EVENT_WRITTEN 需立即处理。给用户的"监控状态"以 dry-run 输出为准。
9. **用户问"到触发价了为什么没进场"（BNB 08-05 例）**：先拉 15m K 线对比 high vs close——盘中插针触及触发价但收盘未站上（require_close=true）= 系统正确拒绝假突破，不是漏触发。回答时附 K 线行列表（时间/开/高/低/收）当证据，用户信服。
10. **清理后扫孤儿脚本**：`ls ~/.hermes/scripts/*-monitor-check.sh` 中无对应 plan 且无对应 Cron 的 = 历史残留死脚本（不运行、无害但会积累）。报告用户后一并删除——用户保守，先问再删。

Architecture Reassurance（"过期会不会影响持仓"）、Checking Position History（TP1/TP2 部分成交三查法 + 保本离场是正常生命周期）、单币 EXITED 清理四步、Stale Log Files 坑：**`references/diagnostic-details.md`**。

## Reference

- `references/incident-log.md` — 事故档案一行式（部署流程类/执行器修复史/监控引擎修复史/工具坑/用户决策），排查同类问题先查这里
- `references/system-architecture.md` — full trigger-to-execution flow diagram, post-entry management, multi-symbol monitoring, file locations, scanner data source
- `references/server-disaster-recovery.md` — server deployment topology (systemd unit / data paths), 阿里云镜像恢复语义（"老照片"陷阱 + 不随镜像走的项 + 恢复后体检清单）
- `references/conditional-order-execution.md` — 条件单触发机制案例数据（mark price 削峰、滑点结构、成交时间线重建）
