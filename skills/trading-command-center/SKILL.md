---
name: trading-command-center
description: Orchestrate the user's crypto futures workflow by routing between market scanning, immediate-execution scanning, trade analysis, execution-plan generation, risk sizing, signal monitoring, position management, and trade review. Use when the user asks for a total trading assistant, command center, combined use of trading skills, what to do when flat or holding a position, which pair is closest to a signal, what can be entered now, how to turn a setup into entry/stop/take-profit/position size, how to monitor an executable plan, or how to coordinate binance-market-scanner, trading-analysis, trade-execution-planner, risk-manager, auto-signal-monitor, and trade-review.
---

# Trading Command Center

Use this skill as the workflow router for the user's crypto futures process. It coordinates these skills:

- `binance-market-scanner`: scan Binance USDT perpetual markets and save ranked results.
- `trading-analysis`: analyze trend, entry logic, stop/protection line, targets, holding, adding, reducing, and exit.
- `trade-execution-planner`: convert analysis into executable entry, stop, take-profit, risk, position size, monitor conditions, and order-parameter drafts.
- `risk-manager`: calculate position size, stop distance, leverage exposure, and liquidation-risk warnings.
- `auto-signal-monitor`: monitor public-market triggers from a complete trade plan.
- `trade-review`: review completed or in-progress trades and produce next-time rules.

Do not duplicate child-skill instructions. Load and use the relevant child skill when the workflow requires it.

## User Preference

The user prefers quality over speed for opportunity discovery. Unless the user explicitly asks for a quick scan, use a deeper Binance market scan with longer public-API timeouts, retries, and progress output. It is acceptable for scanning to take several minutes when it improves candidate quality.

## 用户实际执行链路

用户已搭建完整的自动执行系统，触发后自动下单，不需要人工确认：

```
plan 文件 (~/.hermes/trading-plans/<SYMBOL>-plan.json)
  → signal_monitor.py（Cron 每分钟检测价格）
  → 触发后写事件
  → trading-cron.sh（Cron 每2分钟）
  → binance_executor.py（5重安全门自动下单）
  → 通知用户
```

关键路径和文件：
- 计划目录：`~/.hermes/trading-plans/`
- 监控脚本：`~/.hermes/scripts/<symbol>-monitor-check.sh`
- 监控引擎：`~/.hermes/skills/auto-signal-monitor/scripts/signal_monitor.py`
- 执行器：`~/.hermes/scripts/binance_executor.py`（5门：仓位检查、金额上限、杠杆限制、重复单、隔离模式）
- 事件处理 Cron：`trading-cron.sh`（每2分钟，处理开仓/TP1/过期）
- 持仓管理：同一 Cron 内 manage 子命令

因此：生成 plan 文件 + 建监控 Cron = 接入自动执行链路。不要输出"仅通知不下单"或"手动确认"的提示。执行器自带安全保障。

## 固定保证金规则

用户仓位公式（固定保证金，非风险模型）：
- 保证金：10U 固定
- 杠杆：BTC 20x，其他 10x
- 数量：`qty = (10 × leverage) / entry_price`，按币种精度取整
- 最多同时 6 个持仓，逐仓模式

不要使用 `plan_calculator.py` 的 0.5% 风险模型输出做展示。仅数量计算直接用上述公式，trade-execution-planner 其余流程照常执行。

## Safety

- 扫描只用 Binance 公开行情接口，不登录、不读账户数据。
- 执行由 binance_executor.py 的 5 重安全门控制，技能层不额外加"手动确认"拦截。
- 如果用户请求绕过安全门或超出限额的操作，拒绝。

## 验证拦截规则（建监控前必做）

生成计划文件后、建 Cron 之前，先跑一次 `python3 ~/.hermes/skills/auto-signal-monitor/scripts/signal_monitor.py --plan ~/.hermes/trading-plans/<SYMBOL>-plan.json --dry-run`（只评估不写事件文件）。

验证不静默时：
- 回踩类（pullback/retest）→ 不建，删计划+事件，告知用户
- 突破类（breakout/breakdown）→ 正常建（触发是预期行为）
- 失效触发（invalidation）→ 不建，删计划+事件，告知用户

## 启动前检查（每次流程开头必做）

1. 查 `~/.hermes/trading-plans/` 现有计划文件（避免重复监控同一币种）
2. 查 Cron 列表（避免重复创建监控）
3. 查持仓数（最多6仓；持仓数≥6则不建计划；<6正常执行用户请求）

## State Router

First identify the user's state:

1. `FLAT`: no current position; user wants opportunities.
2. `PLANNING`: user is considering an entry, has a candidate pair, or wants executable prices.
3. `PLAN_READY`: entry, stop, targets, risk, and monitor conditions are defined.
4. `TRIGGERED`: a monitored plan has reached its trigger and needs revalidation.
5. `HOLDING`: user has an open position.
6. `EXITED`: trade is closed and user wants review.
7. `MONITORING`: user wants recurring or repeated watch logic.
8. `QUESTION`: user asks conceptual Skill/process questions.

If the state is unclear, infer from the message. Ask only when missing facts would make the answer unsafe.

## 默认工作流（一条线走完，中间不问）

```
启动前检查（现有plan/Cron/持仓）
→ 扫描（质量优先）
→ 质量门槛：所有候选最高分 < 60 → 输出"本轮无达标候选，不生成计划"，终止
→ 自动选最优候选（≤3个，不问用户选哪个）
→ 【必须】运行 fetch_klines.py 拉取候选币原始K线数据（≤3个币×4周期，约15秒）
→ 【必须】加载 trading-analysis 技能，基于 fetch_klines.py 的原始数据（不是扫描器结果），对≤3个候选币跑完整多周期分析（趋势/入场逻辑/保护线/目标区间）
→ 【必须】加载 trade-execution-planner 技能，仅对上述≤3个候选将分析结果转为执行计划（触发价/止损/TP/取消条件）
→ 固定保证金公式算数量
→ 生成 plan 文件（~/.hermes/trading-plans/）
→ 验证：跑一次 monitor-check.sh（见"验证拦截规则"）
→ 按验证拦截规则处理（静默→建Cron / 回踩失效→不建 / 突破→正常建）
→ 输出汇总表 + 每个候选的分析详情（数据时间/多周期状态/核心逻辑/警告/执行状态）
```

⚠️ 硬性规则：trading-analysis 和 trade-execution-planner 不可跳过、不可用扫描器输出代替、不可手写凑数。没有跑这两个技能 = 流程未完成。

⚠️ trading-analysis 执行标准（不可简化）：
- 必须对每个候选币（≤3个）单独执行 trading-analysis 的完整分析流程
- 必须加载并参考 trading-analysis 的 reference 文档（crypto-futures-system.md / entry-exit-position-management.md / volume-price-analysis.md）
- 必须按 trading-analysis 的输出格式输出：结论/事实/按框架解读/关键位置/操作场景/风险提醒
- 必须包含：量价关系独立分析、保护线推导逻辑（为什么放这个价位）、操作场景分支（如果A则B）
- 扫描器数据只是输入素材，不能代替分析过程。不能用"扫描器已经给了均线/量比，直接总结"来跳过
- 禁止把 trading-analysis 的输出缩写成几行摘要

中间不停下来问"你选哪个""要不要监控"。除非：
- 已有持仓（互斥冲突）→ 告知用户，等指示
- 已有同币种计划 → 告知用户，问是否替换
- 所有候选都不达标 → 如实报告，不硬凑

## Core Pipeline

```text
scan or symbol request
-> fetch_klines.py 拉取候选币原始K线（≤3个币×4周期）
-> trading-analysis（基于原始K线数据，不是扫描器结果）
-> trade-execution-planner
-> 固定保证金公式算数量
-> 生成 plan JSON 文件
-> 验证（见"验证拦截规则"：回踩/失效→不建，突破→正常建）
-> 创建监控 Cron（接入 signal_monitor + binance_executor 链路）
-> 触发后自动执行（executor 5门控制）
-> trade-review after exit
```

When the user explicitly asks what can be entered now, use the scanner's strict `--executable-now` mode first.

## Workflows

### FLAT: Find A Trade Candidate

Use when the user has no position and asks what is worth watching.

1. Use `binance-market-scanner`.
   - Default to a quality-first scan, not a minimal fast scan.
   - If Binance public endpoints are slow, wait longer and rely on progress output before downgrading.
2. Summarize strongest long and short watchlists.
3. Apply market filter from BTC/ETH.
4. Pick at most 3 candidates:
   - closest confirmed setup
   - best pullback candidate
   - strongest risk warning or avoid candidate
5. For selected candidates, use `trading-analysis` to define trigger, protection line, and target zones.
6. Use `trade-execution-planner` for any candidate that could become actionable.
7. 直接生成 plan 文件，验证静默后建监控 Cron（见"验证拦截规则"），不问用户要不要。
8. Output candidate status:
   - `WATCH_ONLY`: interesting but no concrete plan yet
   - `PLAN_READY`: plan file created, monitoring active
   - `EXECUTABLE_NOW`: current price inside entry band; executor will handle
   - `WAIT_TRIGGER`: setup valid, monitoring active, trigger not yet hit
   - `MISSED_ENTRY`: trigger happened but price moved beyond entry band
   - `NOT_EXECUTABLE`: invalid or missing required risk/price inputs

### FLAT: Find Immediately Executable Candidates

Use when the user has no position and asks what can be entered now.

1. Use `binance-market-scanner` with `--executable-now`.
2. Lead with `EXECUTABLE_NOW` candidates only.
3. If none, say so clearly and list closest `WAIT_TRIGGER` or `MISSED_ENTRY`.
4. For each candidate, generate plan file, verify silent, then create monitoring Cron（见"验证拦截规则"）.
5. Do not stop to ask for confirmation.

### PLANNING: Validate One Candidate

Use when the user names a symbol, entry idea, planned stop, or asks whether a signal can be entered.

1. Use `trading-analysis` for setup validity when levels are not already clear.
2. Use `trade-execution-planner` to convert the idea into entry/stop/TP/cancel.
3. Use 固定保证金公式 for quantity.
4. If valid, generate plan file, verify silent, then create monitoring Cron（见"验证拦截规则"）.
5. If any required field is missing, mark `WATCH_ONLY` or `NOT_EXECUTABLE` and state what is missing.

### PLAN_READY: Prepare Monitoring

Use when a plan has concrete entry, stop, target, and risk fields.

1. Confirm the plan contains entry, stop, targets, invalidation, and cancel condition.
2. Generate plan JSON to `~/.hermes/trading-plans/<SYMBOL>-plan.json`.
3. Verify script runs silent（见"验证拦截规则"）：
   - 静默 → 继续下一步
   - 回踩/失效类不静默 → 删计划文件 + 删事件文件 → 终止，告知用户
   - 突破类不静默 → 正常继续（触发是预期行为）
4. Create monitoring Cron (every 1m, no_agent=true, script mode).
5. 检查事件处理Cron（trading-cron.sh）是否在Cron列表中，不在则创建（every 1m, no_agent=true, deliver=all；⚠️调度器实际节奏≈配置+1分钟：1m配置≈实际2分钟，2m配置≈实际3分钟，2026-08-04实测）。
6. 监控触发后由 binance_executor.py 自动执行，无需人工确认。

### TRIGGERED: Revalidate Before Execution

Use when a monitor fires or the user says a plan has triggered.

1. Recheck current price context, BTC/ETH filter, funding/OI, and whether the plan expired.
2. Use `trade-execution-planner` to update status.
3. Executor 的 5 重安全门会做最终检查（仓位、金额、杠杆、重复单、逐仓）。
4. If invalidated/expired, delete plan file and pause monitoring Cron.

### HOLDING: Manage An Open Position

Use when the user has an open position or asks whether to hold, reduce, add, move stop, or exit.

1. Use `trading-analysis` first.
2. Use `risk-manager` if position size, entry, stop, leverage, liquidation price, or equity are provided.
3. Use `trade-execution-planner` only when converting a management decision into a concrete action plan.
4. Do not give a single absolute order instruction. Give conditions and manual action choices.

### EXITED: Review The Trade

Use when the position is closed or the user asks what went wrong/right.

1. Use `trade-review`.
2. If needed, use `trading-analysis` to reconstruct market context.
3. Extract one or two concrete next-time rules.
4. If the issue was poor execution, update the next plan requirements.

### MONITORING: Set Or Update A Watch Process

Use when the user wants live watching or repeated reminders.

1. If no complete trade plan exists, use `trading-analysis` and `trade-execution-planner` first.
2. Create plan file, verify silent, then create monitoring Cron（见"验证拦截规则"）.
3. Use the deployment pattern from `auto-signal-monitor` skill (Cron script mode, not background process).
4. Keep quiet when nothing triggers.

## Output Format

Answer in Chinese. Keep it tight.

**扫描+计划阶段最终输出（一张表完事）：**

```text
扫描范围：XX个币，耗时X秒
大盘过滤：BTC/ETH 状态一句话

| 币种 | 方向 | 触发价 | 止损 | TP1(50%) | TP2(50%) | 数量 | 状态 |
|------|------|--------|------|----------|----------|------|------|
| XXX  | 多   | ...    | ...  | ...      | ...      | ...  | 监控中 |

监控已启动：Cron ID xxx，每分钟检测
过期时间：24h后自动作废
```

不要在聊天里重复贴计划全文。plan 文件已生成，表里有全部关键数据。

分析过程如果用户没问，不要展开。用户问"为什么选这个币"再解释。

## Reference

Read `references/routing.md` when refining workflow decisions or explaining why a child skill was selected.
