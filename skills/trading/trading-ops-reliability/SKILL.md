---
name: trading-ops-reliability
description: Operational reliability patterns for the user's live crypto trading system — Cron-based monitoring deployment, cross-session duplicate prevention, silence rules for notification scripts, executor behavior at trigger time, and exchange-hosted order safety. Load this skill whenever setting up, modifying, debugging, or explaining the trading system's runtime behavior (monitors, crons, executor, notifications).
---

# Trading Ops Reliability

Hard-won operational lessons from running the user's live Binance futures trading system. These complement the functional trading skills (auto-signal-monitor, binance-executor, trading-command-center) with deployment and reliability knowledge.

## Monitor Deployment: Cron Only, Never Background Processes

- **NEVER** use `terminal(background=true)` or nohup for long-running price monitors. They are session-scoped — closing the web page, disconnecting WeChat, or ending the TUI session kills them silently.
- **ALWAYS** use Hermes Cron (`no_agent=true`, script mode) for monitoring. Cron is managed by the daemon and survives all session closures.
- Pattern: create a wrapper script (`~/.hermes/scripts/<symbol>-monitor-check.sh`) that runs `signal_monitor.py` in single-shot mode, filters DONT_NOTIFY lines, and only outputs on ALERT/TRIGGER/EXPIRED/**EVENT_WRITTEN**. Then create a Cron with `schedule="every 1m"`, `no_agent=true`, `deliver=all`.
- **⚠️ Verification/validation runs MUST use `--dry-run`**: `signal_monitor.py --plan <plan> --dry-run` evaluates but writes NO event files and NO state. Running it WITHOUT `--dry-run` for a "check" writes real TRIGGER event files into `trading-events/`, which trading-cron.sh picks up within 2 minutes → executor opens a real position the user never asked for. (Incident 2026-08-03: the 验证拦截 run for BNB wrote a TRIGGER event; trading-cron opened BNB long 0.16 @ 592.41 — the exact trade the validation had just rejected.) The `--dry-run` flag is a pure additive switch: Cron mode without the flag is byte-identical to before.
- **⚠️ grep MUST include `EVENT_WRITTEN`**: `grep -qiE "ALERT|TRIGGER|EXPIRED|EVENT_WRITTEN"`. Without it, the event-file-written confirmation line is swallowed. The `auto-signal-monitor` skill template has been fixed, but always verify.
- **⚠️ NEVER overwrite existing monitor-check.sh with `write_file`**: check `[ -f ... ]` first. If the file exists, it may contain fixes newer than the skill template. Only create from template when the file does NOT exist. (Incident 2026-07-26: `write_file` with stale template removed `EVENT_WRITTEN` from a previously-fixed script, regressing it.)
- **⚠️ Cron `script` param must be relative to `~/.hermes/scripts/`** — pass just the filename (e.g. `uni-monitor-check.sh`), NOT an absolute path (`/root/.hermes/scripts/...`) or home-relative path (`~/...`). Absolute/home paths are rejected with `"Script path must be relative to ~/.hermes/scripts/"`. The script file must already exist under `~/.hermes/scripts/`.
- `signal_monitor.py` without `--loop` runs ONE check and exits — this is correct for Cron usage. The `--loop` flag is only for temporary manual debugging.

## Cross-Session State Conflicts (CRITICAL)

- WeChat, TUI, and Desktop are **independent sessions** sharing the same Cron scheduler and filesystem.
- **Before ANY action on the monitoring system** (restart, create, modify, kill), you MUST check what other sessions have done recently:
  1. `cronjob action=list` — what Crons exist right now
  2. `session_search query="监控 OR monitor OR cron OR 后台进程" sort=newest limit=3` — did another session change the architecture recently?
  3. `pgrep -af "signal_monitor"` — any background processes running? (there should be NONE)
- **Never restart a background process without checking Cron first.** Another session may have killed it and migrated to Cron. Restarting it re-creates the exact problem that session just fixed.

### Incident Log
- **2026-07-22**: WeChat session saw no process → restarted `signal_monitor.py --loop` as background process. TUI session had already killed it and migrated to Cron (every 1m). TUI had to kill the WeChat process again. Root cause: WeChat agent didn't check `cronjob action=list` or recent sessions before acting. User was frustrated ("你好好查查", "你去看看").

### Diagnostic Rule
- If `pgrep -af "signal_monitor"` returns a process AND `cronjob action=list` shows a monitor Cron for the same symbol → **the background process is stale/wrong**. Kill it, do NOT report "monitoring is running normally" based on the background process. The Cron is the source of truth.

## Duplicate Prevention

- Before creating a monitor Cron for any symbol, **ALWAYS** run `cronjob action=list` to check for existing monitors on that symbol.
- If a monitor already exists, tell the user — do NOT create a duplicate. Two monitors can write duplicate TRIGGER events.
- Also check `~/.hermes/trading-plans/` for existing plan files for that symbol.

## Silence Rules for Cron Scripts

- Cron scripts must produce **zero output** when nothing happens. Any stdout triggers a WeChat notification via `deliver=all`.
- Known bug (fixed): `manage_position()` returning `{"actions": [{"action": "check", "msg": "无持仓"}]}` when no position exists caused WeChat spam every 2 minutes. Fix: return empty actions list when no position.
- Known bug (fixed 2026-07-24): `manage_position()` returning `tp1_pending` ("TP1 Algo单待触发") or `tp1_already_handled` ("止损已移过") every 2 minutes → WeChat spam. Fix: these are normal steady-states, changed to `pass` (no output). Only actual state transitions (breakeven move executed, error) produce output.
- Rule: if the script has nothing actionable to report, print nothing. Steady-state observations ("waiting", "already done") are NOT actionable — only state *transitions* produce output.

## No Re-Analysis at Trigger Time

- The executor's 5 checks are **data-sanity checks** (direction, market deviation <10%, notional ±15%, TP direction, stop distance <20%), NOT market re-analysis.
- At trigger: the system does NOT re-pull K-lines, re-evaluate trends, or check for flash crashes. Trigger + valid data = immediate entry.
- This is a deliberate user decision: small positions (10U margin), max loss ~0.75U per trade, speed matters for breakout strategies.
- If the user asks "will it re-analyze before entering?", answer honestly: NO.
- User considered adding 5m K-line confirmation but chose to run without it first, planning to add later if false breakouts become frequent.

## Notification Coverage (updated 2026-07-23)

The `trading-cron.sh` (deliver=all) notifies on events the executor processes. Exchange-hosted conditional orders execute without any Hermes callback, so position-change detection was added.

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

### Position Change Detection (`watch` command) — IMPLEMENTED 2026-07-23

`binance_executor.py watch` compares current positions against a saved snapshot (`~/.hermes/trading-state.json`):

```
Every ~2 minutes (trading-cron.sh step 3; configured every 1m, actual cadence ≈2m):
  ① Query current positions from Binance API
  ② Read previous snapshot from trading-state.json
  ③ Compare:
     - Position disappeared → determine cause (SL/TP/manual) → notify
     - Position quantity reduced >20% → partial TP → notify
     - No change → silent
  ④ Save current positions as new snapshot
```

**Cause determination logic:**
- Current price ≤ stop_loss × 1.002 → "🔴 已止损"
- Current price ≥ TP1 × 0.998 → "🟢 已止盈"
- Otherwise → "⚪ 仓位已平（可能手动）"

**Cleanup on position disappearance (all 4 steps, in order):**
- Deletes the plan file (`<SYMBOL>-plan.json`)
- Deletes all event files for that symbol from `trading-events/`
- **Cancels ALL residual Algo orders for that symbol** (`cancel_all_orders(symbol)`) — prevents stale TP2 orders from accumulating and corrupting the next trade on the same symbol
- Saves updated (empty) position snapshot

**Why residual order cleanup matters (discovered 2026-07-24 via RE trade):**
After TP1 fills and SL moves to breakeven, the TP2 Algo order remains on the exchange. When breakeven-SL closes the remaining position, nobody cancels TP2. If the user later trades the same symbol, the stale TP2 can fire unexpectedly, reducing the new position without the system knowing. User had to manually cancel in the Binance APP. Now automated.

**Stale TP2 quantity mismatch after partial reduce (discovered 2026-07-25 via NEAR trade):**
A *related but distinct* problem: after TP1 reduces the position (e.g. 55→28), the TP2 Algo order still carries the **original** quantity (27). Now SL=28 + TP2=27 = 55, but only 28 remains. Both are `reduceOnly=true` so no reverse position can open, but:
- If TP2 fires first (27 closed), only 1 remains for SL — the last 1 unit closes at a potentially bad price
- If SL fires first (all 28 closed), TP2 becomes a stale orphan that can interfere with the NEXT trade on this symbol
- The `watch` cleanup only fires on position **disappearance**, NOT on partial reduce — so between TP1 and final close, the mismatched TP2 sits uncorrected

**✅ FIXED 2026-07-25 (user explicitly approved and requested implementation):** After TP1 reduce + breakeven move succeeds in `manage_position()`, the code now automatically:
1. Finds all remaining TAKE_PROFIT_MARKET Algo orders for the symbol
2. Cancels them all (best-effort, try/except per order)
3. Re-places TP2+ orders with quantities proportional to the **remaining** position (not original)
4. Last TP absorbs rounding error: `remaining_qty - allocated` ensures total = exact remaining position
5. Logs each re-placed TP; failures only log warnings, never block the already-placed breakeven SL

**Safety design**: TP refresh runs ONLY after breakeven SL is confirmed placed. If SL placement fails, TP refresh never runs. All TP operations are best-effort (wrapped in try/except). Worst case = no TP orders (position still protected by breakeven SL), never a crash or orphaned state.

**Code location**: `manage_position()` in `binance_executor.py`, after the `log.info(f"止损移到保本...")` line. Pushed to GitHub repo (commit c460bf2).

**Key design decisions:**
- Does NOT depend on Binance callbacks (none exist)
- Does NOT depend on INVALIDATION events (they can pile up unprocessed)
- Only depends on: "position was there, now it's not" — universally reliable
- Max notification delay: **~2-3 minutes.** trading-cron configured `every 1m`, actual cadence **≈2m** (verified 2026-08-04 after 1m change: 23:56→23:58→00:00→00:02, stable 2m). Compute worst-case delays as 2m scheduling + ~1m execution.
- TP1 成交→保本损挂上：实际 **~2-3 分钟**（2 分钟 manage 轮询 + ~1 分钟执行；2026-08-03 UNI 实测 2'53"：TP1 23:35:44 → 保本 23:38:37.232，错过 23:35:36 tick 8 秒）。条件单是单动作（触发只执行一个市价单，不会自动改 SL）；保本价=入场价，TP1 前无法预挂（会立即触发），逻辑上必须等 TP1 成交后
- **窗口期三层保护**：TP2 单（利润继续）+ 保本损（~2-3 分钟补挂）+ 原始止损（全程生效，reduceOnly 不反手）。最坏 = 窗口内价格反向穿过原始止损（需极端行情，如 UNI 从 TP1 涨 4.7%），剩余仓按原始止损离场（≈1.44U 亏 vs 保本 0U）——有界、可量化、概率极低。历史 8/8 保本移动无事故
- **30s 轮询方案评估（2026-08-03，用户决定不改）**：脚本三步实测总耗时 0.556s（30s 周期不会重叠），API ≈12 次/分钟（远低于限流），通知频率不变（静默设计）。但收益趋近 0（窗口已有原始止损兜底），按"能跑就不改"保持现状；仓位变大或保本延迟真造成过损失再改
- First run after deployment: creates empty snapshot, no false notifications

## Cleanup Procedure (user says "清掉所有监控和计划")

When user requests clearing all monitors and plans:
1. `cronjob list` → identify monitor Crons (name contains "价格监控" or script contains `monitor-check`)
2. Remove each monitor Cron (⚠️ NEVER remove `trading-cron.sh` event-processing Cron)
3. `rm ~/.hermes/trading-plans/*-plan.json *-plan.state.json`
4. `rm ~/.hermes/scripts/*-monitor-check.sh`
   ⚠️ 删 Cron 后必须核对三处：scripts 目录（monitor-check.sh 易漏删，2026-08-03 清 IDOL 时漏了 idolusdt 脚本）、`*-plan.state.json`、以及 Cron 列表本身。逐一 `ls` 验证，别只信 rm 结果。
5. Verify: re-check Cron list + plans directory, confirm clean
6. Output report: what was deleted, what was preserved

## Exchange-Hosted Orders: Safety Net Status

- SL/TP orders on Binance servers protect positions even if Hermes dies.
- **As of 2026-07-23**: conditional orders ARE placed via the Algo Order API (see section below). Exchange-hosted SL/TP are active. Cron `manage` is a supplementary layer (TP1 reduce + breakeven move), not the only protection.
- Margin mode (isolated) and leverage are set per-symbol at order time, regardless of Binance web UI settings.

### ✅ Conditional Orders via Algo Order API (resolved 2026-07-23)

Earlier this account returned `-4120 "Order type not supported for this endpoint. Please use the Algo Order API endpoints instead."` for all conditional order types via `/fapi/v1/order`. This was **misdiagnosed as an account restriction** — it is actually Binance's **2025-11 API migration**: conditional orders (STOP_MARKET, TAKE_PROFIT_MARKET, STOP, TAKE_PROFIT, TRAILING_STOP_MARKET) moved to a separate Algo Order system. The old `/fapi/v1/order` endpoint no longer accepts them. MARKET and LIMIT still use the old endpoint.

**Correct endpoints (verified working on this account):**

| Action | Endpoint | Key params |
|--------|----------|-----------|
| Place conditional | `POST /fapi/v1/algoOrder` | `algoType=CONDITIONAL`, `triggerPrice` (NOT `stopPrice`), `positionSide=LONG/SHORT`, `workingType=MARK_PRICE`, `quantity` |
| Query open conditionals | `GET /fapi/v1/openAlgoOrders` | `symbol` (optional) |
| Query one by id | `GET /fapi/v1/algoOrder` | requires `algoId` or `clientAlgoId` |
| Cancel conditional | `DELETE /fapi/v1/algoOrder` | `symbol` + `algoId` |

**Critical differences from the old order API:**
- Param renamed: `stopPrice` → `triggerPrice`. Must add `algoType: "CONDITIONAL"`.
- Hedge Mode (this account is `dualSidePosition: true`): `positionSide` MUST be `LONG`/`SHORT`, never `BOTH` (BOTH → -4061 "position side does not match"). Infer from close direction: closing a long = `SELL` + `positionSide=LONG`.
- Response returns `algoId` (not `orderId`). Query results use `orderType` and `triggerPrice` fields (not `type`/`stopPrice`).
- Conditional orders are invisible to `GET /fapi/v1/openOrders` — that only lists normal orders. Use `openAlgoOrders` to see SL/TP.
- The path is `/fapi/v1/algoOrder` (camelCase). `/fapi/v1/algo/order` and `/fapi/v2/order` both 404 — those are wrong.

**Executor status**: `binance_executor.py` was updated 2026-07-23 — `_place_conditional_order()` now posts to `/fapi/v1/algoOrder`, new `get_open_algo_orders()` helper added, `cancel_all_orders()` cancels both normal + Algo orders, and `manage_position()` reads `triggerPrice`/`algoId` and cancels via the Algo endpoint. SL/TP now place successfully at entry.

**Required behavior:**
- After every `execute_plan()`, still verify SL/TP step statuses (now `algo_id` field). If ERROR, notify user to place manually in the Binance APP.
- To check SL/TP status, query `get_open_algo_orders(symbol)` — NOT `get_open_orders`.
- Exchange-hosted SL/TP now protect positions even if Hermes dies (see Safety Net section).

## Conditional Order Trigger Mechanics (verified 2026-08-02)

When explaining why SL/TP filled late, early, or at a worse price, use these verified facts (details + case data: `references/conditional-order-execution.md`):

- **Trigger ≠ fill**: conditional orders fire in two steps — mark price crosses the trigger, then a MARKET order sweeps the book. Trigger price is a fuse, not a price guarantee.
- **Mark price shaves peaks, not speed** (BEAT 8/2 same-minute data: last 6.365 vs mark 6.066, ~4.7% shaved). Trigger certainty depends on **overshoot**, not dwell time: >5% overshoot → mark crosses within the spike minute, fills even on a 2-min flash-back; <1% overshoot → mark may never reach the trigger (7/31 TP1 death: last 4.299 vs TP 4.282).
- **Stop-loss slippage is structural**: market-stop guarantees exit, not price. 7/31 reverse-calc: planned SL 4.022, actual fill ≈3.97 (1.3% deeper).
- **Reconstruct fill timelines** with `/fapi/v1/markPriceKlines` (mark candles → trigger minute), 1m last-price candles + executor log (watch detection lags fills by ≤3-4 min), and PnL reverse-calc when avgPrice is unknown.

### 用户问"价格到了止损价为什么没止损"排查 (verified 2026-08-03)

排查顺序（BTC 实例：last 插针 63052+ 用户以为该止损，实际止损 21:51:59 已触发 @63051.50，-1.33U）：
1. **先查 `userTrades`**（signed, limit 5）——大概率已经触发了（平仓方向记录 + realizedPnl 负数）。用户通常是看到了触发前瞬间的盘面
2. 对比 `premiumIndex`（mark）vs `ticker/price`（last）：止损单 `workingType=MARK_PRICE`，last 插针 ≠ mark 穿过 → 晚触发是设计行为（防插针），不是故障
3. `openAlgoOrders(symbol)` 里止损单消失 = 已触发；残留 TP 单由 watch ≤2min 清理，等不及可手动 `python3 ~/.hermes/scripts/binance_executor.py watch` 立即完成清理（删 plan、cancel 残留单、更新 trading-state.json 快照；幂等安全）
4. 触发后到 Hermes 状态更新/通知有 ≤2-3 分钟延迟（watch 周期实际 ≈2m，配置 1m），期间用户查持仓"还在"属正常，不是没止损

## System Resource Impact

- Monitor Cron: ~0 disk growth per day (silent mode writes nothing unless triggered)
- Trigger event file: ~1KB per trigger
- Estimated annual growth: <1MB
- CPU/memory impact: negligible (each Cron run is a single API call, <1 second)

## WeChat iLink Rate Limiting (notification loss risk)

The WeChat iLink gateway has a **30-second cooldown** between sends. When multiple Crons fire near-simultaneously (e.g. RE trigger + open + TP1 + watch all within seconds), messages queue up and exceed the rate limit → **silently dropped with no retry**.

**Observed (2026-07-24)**: RE opened, TP1 filled, and watch detected the change all within ~2 minutes. 4 notifications attempted; all 4 hit `iLink sendmessage rate limited; cooldown active for 30.0s` and were lost. User only learned about the position by asking manually.

**Recurred 2026-08-01 (twice)**: event-processing Cron reported `last_delivery_error: ... iLink sendmessage rate limited` at 21:28 and 21:58 — the ADA breakeven-close notification was lost. Confirms this is a persistent risk, not a one-off. Check `cronjob action=list` → `last_delivery_error` field on the event-processing job when the user says "没收到通知".

**Mitigation status**: No fix implemented yet. The gateway drops rate-limited messages without retry. Possible future fixes:
- Message queue with 30s spacing in the WeChat adapter
- Consolidate multiple notifications into one message (trading-cron.sh already batches steps 1-3 into one output, but separate Crons for different symbols can still collide)

**Practical impact**: After any trigger event, if the user doesn't receive a WeChat notification within 5 minutes, assume it was rate-limited. The position and orders are still correct on the exchange — only the notification was lost. User can always ask "帮我查下监控状态" to get current state.

## Binance Hedge Mode API Quirks (from 2026-07-22 code audit)

Hard-won API parameter conflicts when the account uses Hedge Mode (dual-side positions). These bit us during live ENA execution:

| Error Code | Trigger | Fix |
|------------|---------|-----|
| -1106 | `reduceOnly=true` + `positionSide=LONG/SHORT` on any order type | **All `reduceOnly` removed from codebase.** In Hedge Mode, `positionSide` alone tells Binance the order reduces a position. Applies to: TP orders, TP1 partial close, CLI close. |
| -4120 | `STOP_MARKET`/`TAKE_PROFIT_MARKET`/`STOP`/`TAKE_PROFIT`/`TRAILING_STOP_MARKET` via standard `/fapi/v1/order` | **NOT an account restriction** — Binance's 2025-11 migration moved conditional orders to the Algo Order system. Use `POST /fapi/v1/algoOrder` with `algoType=CONDITIONAL` + `triggerPrice` (not `stopPrice`). See "Conditional Orders via Algo Order API" section. The old 3-combo retry on `/fapi/v1/order` is obsolete. |
| -4136 | `MARKET` + `closePosition=true` | MARKET orders must use `quantity`, never `closePosition` |
| -1102 | `STOP_MARKET` without `quantity` or `closePosition` | Must send one of them |

**Scientific notation trap**: Binance filter strings like `"0.0000100"` become `"1e-05"` via `str(float(...))`, breaking decimal parsing → `decimals=0` → prices/quantities rounded to 0. Always parse precision from the **original string**, not from `str(float_value)`. Both `round_price()` and `round_qty()` are **fixed** (2026-07-22): parse from `tick_str`/`step_str` original strings. When `decimals==0` (e.g. ENA stepSize="1"), `round_qty()` returns `int` — Binance rejects `1142.0` but accepts `1142`.

**Integer quantity**: When `stepSize="1"`, `round_qty()` must return `int`, not `float`. Binance rejects `1142.0` but accepts `1142`.

**`avgPrice` is null on market orders**: The market-order response frequently returns `avgPrice: null` (order submitted, not yet fully matched). Any logic that needs the actual fill price (e.g. post-fill stop re-validation, gate 7) MUST fall back to `get_positions()[symbol].entry_price` when `avgPrice` is null/0. `float(order.get("avgPrice"))` crashes; `float(order.get("avgPrice") or 0)` silently yields 0 and skips the logic. Verified on the AAVE execution record (`"avg_price": null`).

**Post-execution verification**: After `execute_plan()`, check individual step statuses (`stop_loss`, `take_profits`). As of 2026-07-28, `success` is conditional on SL placement — if SL fails, the executor auto-closes the position and returns `success: false`. TP failures are tolerated (SL still protects). The old unconditional `success=true` bug is fixed.

**`round_qty` float truncation (FIXED 2026-07-28)**: `math.floor(qty / step) * step` suffers from IEEE 754 boundary errors: `0.3 / 0.1 = 2.9999999999999996` → floor → 2 → result 0.2 instead of 0.3. ~50% of inputs hit this. Fixed with `math.floor(qty / step + 1e-9) * step`. The epsilon (1e-9) is billions of times smaller than any real stepSize, so it never pushes a genuine fractional value over the boundary. Also affects `manage_position()` TP re-placement (`remaining_qty - allocated`) where truncation leaves dust positions that can never be closed.

Full audit with 10 bugs ranked by severity: see `binance-executor` skill references (code-audit-2026-07-22).

## Rule ID Naming = Event Routing (CRITICAL — caused missed trade 2026-07-26)

`signal_monitor.py`'s `write_event_file()` classifies events by rule ID content:

```python
if "invalid" in rule_id:
    event_type = "INVALIDATION"   # → executor DELETES the plan
else:
    event_type = "TRIGGER"        # → executor OPENS a position
```

**Naming convention (MUST follow when generating plan JSON):**
- Entry/breakout rules: `<symbol>_breakout_trigger`, `<symbol>_entry` — must NOT contain "invalid"
- Invalidation rules: `<symbol>_invalidation`, `<symbol>_invalid_<price>` — MUST contain "invalid"
- Market filter rules: level=WATCH (never writes event files), ID is free-form

**Incident (2026-07-26)**: UNI plan used rule ID `uni_breakout_trigger`. Old code had `"break" in rule_id.lower()` as an additional INVALIDATION matcher → "breakout" matched "break" → trigger event misclassified as INVALIDATION → executor deleted the plan instead of opening. UNI was at 3.85, went to 3.88+. Missed trade.

**Fix applied (final, robust)**: classification no longer guesses from the rule ID at all. `evaluate()` now attaches `"rule_type": rule_type` to each event, and `write_event_file()` classifies with `event.get("rule_type") == "invalidation"` → INVALIDATION, else TRIGGER. The rule ID can be named freely; only the rule's declared `type` field (`"breakout"` / `"invalidation"` / `"pullback_reclaim"` / `"market_filter"`) drives routing.

**Intermediate fix (superseded)**: an earlier patch merely removed `"break" in rule_id.lower()`, leaving `"invalid" in rule_id` as the matcher. That works but is still fragile (relies on ID naming). The type-field approach below is the durable solution.

**Durable lesson**: never classify logic branches by substring-matching a free-form ID string. Any new rule type or naming habit silently breaks it. Always route on an explicit type/enum field. The naming convention above remains a useful secondary safety net but is no longer the primary mechanism.

**Verification after this kind of edit**: walk EVERY rule type through the new path (breakout→TRIGGER, invalidation→INVALIDATION, pullback_reclaim→TRIGGER, market_filter→no event file because level=WATCH), and confirm downstream consumers (executor) read the unchanged event-file `type` field. Also confirm no variable used later was deleted by the edit (a `rule_id` reference survived and had to be re-added).

## Volume Ratio Silent Bypass (CRITICAL)

`signal_monitor.py`'s `rule_volume_ok()` returns `True` when `min_volume_ratio` is absent from the plan's rules. A plan without this field triggers on price alone, ignoring volume entirely.

- Plans generated by trade-execution-planner may omit the `rules` array (only writing `monitor.trigger_condition` as a string). When this happens, the monitor skips all rule-based checks including volume.
- **Verification**: before deploying a monitor Cron, confirm the plan JSON has a `rules` array with `min_volume_ratio` set (breakout ≥ 1.0, pullback ≥ 0.8).
- The volume ratio is calculated **in real-time** at each check (current candle volume / avg of prior 20 candles), NOT from the analysis-phase snapshot. The threshold is fixed in the plan; the measured ratio is live.

### Plan Validation Checklist (run before creating monitor Cron)

When generating a plan via trading-command-center workflow, the plan JSON MUST contain:
1. `rules` array (NOT just `monitor.trigger_condition` string)
2. Each entry rule must have `min_volume_ratio` field
3. `require_close: true` for breakout/pullback entries (15m candle close confirmation)
4. `timeframe: "15m"` matching the monitor's check interval
5. **Rule IDs must follow naming convention**: entry rules must NOT contain "invalid"; invalidation rules MUST contain "invalid" (see "Rule ID Naming" section above)
6. **盈亏比检查（2026-08-03 BTC 复盘教训）**：TP1 距离 ≥ 止损距离（硬性 ≥1R），破位/突破类目标空间 ≥2R 才建计划。低波动大盘币（BTC/ETH，ATR 小）破位后下方空间常贴着支撑位（1R 上下）——执行再完美也难盈利（案例：BTC 破位空止损 0.71% 目标 0.83% → 1.16R，止损离场 -1.33U；同日 TAO 2.7R 正常获利）。候选筛选阶段就应排除盈亏比不足的标的

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

## Config Change Audit Procedure (MANDATORY before any config change)

When the user asks to change any value in `trading-config.json` (e.g. max_positions, margin, leverage):

1. **Search ALL scripts AND skills** for references to the old value. Use BOTH the snake_case token AND every natural-language phrasing — different files phrase it differently:
   ```
   # snake_case token (config key + code + most docs)
   search_files pattern="max_positions" path=~/.hermes/scripts
   search_files pattern="max_positions" path=~/.hermes/skills
   # Chinese prose (command-center + ops-reliability docs)
   search_files pattern="最多.*仓|持仓.*[0-9]|≥[0-9]则" path=~/.hermes/skills
   # ⚠️ English prose form — binance-executor/SKILL.md uses "max positions (N)"
   #    (NO underscore). A grep for only max_positions SILENTLY SKIPS this file.
   search_files pattern="max positions" path=~/.hermes/skills
   ```
   **Pitfall (hit 2026-07-30 during 2→6 change)**: the first audit grep covered only `max_positions` + Chinese phrases and missed `binance-executor/SKILL.md` line 13 ("max positions (2)" — English, no underscore). The change was nearly shipped with that file still saying "(2)". Always run the English-prose grep too.
2. **Categorize each hit** into one of four types:

   | Type | Example | Action | Risk |
   |------|---------|--------|------|
   | **Functional code** (reads config dynamically) | `CFG.get("max_positions", 1)` | NO change needed — auto-reads new value | Zero |
   | **Code comment** | `# 检查是否有其他持仓（最多1个）` | Update text | Zero |
   | **Documentation/description** | Skill SKILL.md "最多同时1个持仓" | Update text | Zero |
   | **Behavioral rule** (logic embedded in Skill text) | "有仓位则不开新计划" | ⚠️ Must rewrite the LOGIC, not just swap the number | **HIGH — naive number swap introduces logic bug** |

3. **Present the full categorized list to the user BEFORE making changes.** User explicitly requires this audit step.
4. **Never state "N places need changing" from memory** — always check code first. A prior session incorrectly said "3 places" when the actual count was 8, causing user frustration ("描述我记得修改了很多地方啊").
5. **Cross-check against the LAST change of this same value via git history** (user's instinct, proven right 2026-07-30). The previous change's commit diff is the ground-truth list of which files this value touches:
   ```bash
   cd /tmp/hermes-backup && git log --oneline --all | grep -i "max_positions\|持仓"
   git diff <prev_commit>^..<prev_commit>   # shows every file the last change touched
   ```
   Compare your current audit list against that diff. Any file in the old diff that's missing from your current list = a location your grep missed (usually the English-prose one). This caught `binance-executor/SKILL.md` when the grep alone didn't.

### Known Complete Location List: max_positions (verified 2026-07-30)

When changing max_positions to N, these are ALL 9 locations (1 functional + 8 documentation):

| # | File | Line | Type | Content to change |
|---|------|------|------|-------------------|
| 1 | `~/.hermes/trading-config.json` | 6 | **Functional** | `"max_positions": N` — the ONLY functional change |
| 2 | `skills/trading-command-center/SKILL.md` | ~52 | Doc | "最多同时 N 个持仓，逐仓模式" |
| 3 | `skills/trading-command-center/SKILL.md` | ~66 | **Behavioral rule** | "查持仓数（最多N仓；持仓数≥N则不建计划；<N正常执行用户请求）" |
| 4 | `skills/trading/binance-executor/SKILL.md` | ~13 | Doc (⚠️ English prose "max positions (N)", no underscore) | "max positions (N)" |
| 5 | `skills/trading/trading-ops-reliability/references/system-architecture.md` | ~19 | Doc | "Check no conflicting position (max_positions=N)" |
| 6 | `skills/trading/trading-ops-reliability/references/system-architecture.md` | ~60 | Doc | "Up to N positions can be open at a time (max_positions=N config)..." |
| 7 | `skills/trading/trading-ops-reliability/SKILL.md` | ~312 | Doc/example | "最多N仓" in the WRONG-example explanation |
| 8 | `skills/trading/trading-ops-reliability/SKILL.md` | ~314 | Doc/example | "查持仓数（最多N仓；持仓数≥N则不建计划；<N正常执行用户请求）" |
| 9 | `skills/trading/trading-ops-reliability/SKILL.md` | ~289 | Doc (this list's header) | Bump the "verified YYYY-MM-DD" date in the section title |

**NOT changed**: `binance_executor.py` line ~353 uses `CFG.get("max_positions", 1)` — dynamic read, zero code change needed. Its inline comment already says "最多N个，由config控制" (no literal number), so it needs no edit either.

**Historical incident records are NOT changed**: the AAVE entry (~line 431) says "max_positions (2 slots full)" — that describes what actually happened at the time and must stay verbatim. A residual-check grep will surface it; recognize it as history, not a stale reference.

**Still verify with search_files (all three patterns above) AND the git-history cross-check before executing** — line numbers drift as skills evolve, and new references may have been added since this list was compiled.

### Behavioral Rule Pitfall (discovered 2026-07-24)

`trading-command-center/SKILL.md` line 66 originally said: "查是否有持仓（互斥：最多1仓，有仓位则不开新计划）"

Naive fix: "最多6仓，有仓位则不开新计划" → **WRONG** — with 1 position the system would refuse to find new opportunities even though 1 slot is still available.

Correct fix: "查持仓数（最多6仓；持仓数≥6则不建计划；<6正常执行用户请求）" — the LOGIC changed, not just the number.

**Rule: when a Skill sentence contains an if/then condition, changing a number inside it requires re-examining the entire condition.**

## Plan-Layer Duplicate Problem (user decision 2026-07-24: NO automated fix)

When user runs the scan flow multiple times without clearing, three issues can occur:
- Same-symbol plan overwritten silently
- Duplicate monitor Crons for same symbol
- No global coordination between scan runs

**User's chosen mitigation**: say "清掉所有监控和计划" before each scan run. This is a deliberate simplicity trade-off — user fears Skill complexity more than occasional manual cleanup.

**Do NOT add automated pre-scan checks to Skills unless user explicitly asks.** The execution layer (executor hard lock) already prevents over-opening positions; the plan layer mess is annoying but not dangerous.

## Backup & Restore

Skills and scripts can be backed up to a git repo for server migration:

1. Copy `~/.hermes/skills/<trading-skills>/` and `~/.hermes/scripts/` to a temp dir
2. **Never** include `trading-config.json` (contains API keys) or `trading-events/` (transient)
3. `trading-plans/` CAN be included (no secrets, useful for restoring active monitors after migration)
3. Include a `restore.sh` that copies skills back
4. **Path quirk**: `binance-executor` and `trading-ops-reliability` live under `skills/trading/` subdirectory, not root `skills/`. The restore script must handle this.
5. After restore: manually configure API keys + rebuild Cron jobs (ask Hermes "帮我重建交易监控 Cron")
6. Current backup repo: `github.com/jiangfei1986WAR3/hermes123`
7. **Local clone**: `/tmp/hermes-backup` (SSH remote: `git@github.com:jiangfei1986WAR3/hermes123.git`). To push updates: `cd /tmp/hermes-backup && cp ~/.hermes/scripts/binance_executor.py scripts/ && git add -A && git commit -m "..." && git push origin main`. If `/tmp/hermes-backup` doesn't exist (reboot clears /tmp), re-clone: `git clone git@github.com:jiangfei1986WAR3/hermes123.git /tmp/hermes-backup`.
8. **Sanitized config backup**: `config/trading-config.example.json` in the repo has the full config structure with API keys replaced by placeholders (`YOUR_BINANCE_API_KEY_HERE`). `config/README.md` has restore instructions. To update after config changes: regenerate the example file with placeholders, never copy the real config.

## Known Unfixed Bugs (audit 2026-07-23, user explicitly deferred)

User reviewed all P1/P2 items and said: "先不用优化 等真的遇到以后再说" (don't optimize yet, deal with it when it actually happens). **Do NOT proactively fix these. Only fix if the user encounters the actual problem and asks.**

### ~~P1: Breakeven Move Silently Fails — Unrounded Write-Back vs Rounded Algo Orders~~ (FIXED 2026-08-03, Option A approved + implemented + verified + pushed)

**Symptom**: TP1 fills (half position sold at TP1), but the remaining half's stop-loss never moves to breakeven. Position later stops out at the ORIGINAL wide SL → net loss despite TP1 profit. IDOL trade 2026-08-03: TP1 +0.81U at 11:08, remaining half stopped at 11:20 for -1.81U (SL still at original 0.02312 instead of entry 0.02397).

**Root cause**: `manage_position()` matches exchange Algo orders against plan-file prices with tolerance `abs(trigger_price - plan_price) < 0.0001 * plan_price`. But gate-7 slippage calibration writes back UNROUNDED floats to the plan file (`plan["stop_loss"] = 0.023115274361400186`) while the exchange Algo orders were placed at ROUNDED prices (`round_price` → 0.02312). Difference 4.7e-6 > tolerance 2.3e-6 → BOTH the `tp1_orders` match AND the `sl_at_original` check fail → `manage_position()` falls into the "already handled" branch → breakeven move NEVER fires. Affects every trade that had nonzero slippage calibration (write-back of shifted unrounded prices).

**Evidence trail (how to recognize it)**: executor log shows "持仓变动: 🟡 部分止盈" (watch detected the fill) but NO "止损移到保本" line afterward (manage never acted) → then "🔴 已止损" at the original SL price.

**Fix applied (Option A, approved + implemented 2026-08-03, commit 6b74138)**: round before write-back in the slippage-calibration block:
```python
stop_loss = round_price(symbol, stop_loss + delta)
for tp in take_profits:
    tp["price"] = round_price(symbol, tp["price"] + delta)
```
This makes plan-file prices byte-identical to exchange order prices → matching succeeds. Option B (widen tolerance to 0.001×price) was considered and rejected — addresses the symptom, not the source.

**Why previous 10 breakeven moves worked despite this bug**: the bug only fires when slippage calibration writes back (delta ≠ 0). All prior trades (NEAR/AAVE/WLD/UNI/LINK/ADA/BEAT/SUI/BTC/AVAX) filled at or extremely near the plan price → delta ≈ 0 → no write-back → plan-file prices stayed as originally written → matching succeeded. IDOL 2026-08-03 was the FIRST trade with material slippage (plan 0.02365 vs fill 0.023965, +1.3%) → write-back triggered → bug exposed. **This is why the bug is size-independent**: it will fire on ANY future trade with nonzero slippage, at 10U or 1000U margin alike — only the dollar loss scales. User explicitly asked "本金大了就不会发生吗" — answer is NO, fix before scaling up.

**Verification (2026-08-03, real symbol info)**: three price magnitudes tested — IDOL (tick 1e-05), UNI (tick 0.001), BTC (tick 0.1). Before fix: `matches(round_price(raw), raw)` = False for both SL and TP1 (bug reproduced exactly). After fix: written-back price == exchange order price, both `sl_at_original` and `tp1_orders` match True. Zero-slippage path (delta=0) never enters the calibration branch → byte-identical behavior. Rounded price conforms to tickSize (exchange accepts it).

**tickSize is exchange-mandated, NOT agent-chosen**: `round_price()` reads the exchange's PRICE_FILTER (IDOL 0.00001 / UNI 0.001 / BTC 0.1). When the user asks "取整到几位小数好", the answer is always "币安 tickSize 决定" — rounding coarser silently shifts stops, rounding finer gets rejected by the exchange. The fix uses the exchange's own ruler, so written-back values always equal placed-order values.

**Durable lesson**: any price written to a file that later gets matched against exchange order prices MUST be rounded to the exchange tick size FIRST. "Write-back" alone is not enough — the written value must equal the placed-order value.

### ~~P0: TP1 Double-Close~~ (FIXED 2026-07-23)

Two independent TP1 mechanisms could fire simultaneously (exchange Algo order + `manage_position()` Cron). **Fixed**: `manage_position()` now checks if the TP1 Algo order still exists in `openAlgoOrders` before reducing. If it's gone (already filled by exchange), it skips the reduce and only does the breakeven move.

### ~~P0: TP1 Breakeven Move Never Fires After Price Drops~~ (FIXED 2026-07-24)

`manage_position()` gated all TP1 logic behind `if mark_price >= tp1_price` (for longs). After TP1 Algo order fills on exchange and price drops back below TP1, the condition becomes False → the breakeven move NEVER executes → position stays with original wide stop-loss indefinitely. In the RE trade (2026-07-24), TP1 filled at 0.538 but price dropped to 0.518; the SL stayed at 0.49 instead of moving to entry 0.5113.

**Fix applied**: Removed the `tp1_hit` price gate entirely. Detection now relies solely on Algo order existence:
- TP1 Algo order still in `openAlgoOrders` → not yet triggered → wait
- TP1 Algo order gone + SL at original price → TP1 filled → move SL to breakeven
- TP1 Algo order gone + SL NOT at original → already handled → skip

**Root cause lesson**: Never use current price as a proxy for "did a historical event happen." Price moves on; the event (TP1 fill) is permanent. Exchange order state is the authoritative signal.

### ~~P1: Stop-Loss Failure → False Success + Grep Eating JSON~~ (FIXED 2026-07-28)

Two independent defects combined into "silent failure":

**Defect A**: `execute_plan()` had no `return` in the stop-loss `except` block. After SL placement failed, execution continued to `result["success"] = True` unconditionally. The position was left naked while reporting success.

**Fix A**: The `except` block now: (1) market-closes the just-opened position via `place_order(symbol, exit_side, "MARKET", quantity=quantity, position_side=pos_side)`, (2) sets `result["success"] = False`, (3) returns immediately. If emergency close also fails, logs critical error. Additionally, `result["success"]` is now conditional: `sl_ok = any(step stop_loss has status OK)` — defense-in-depth.

**Defect B**: `trading-cron.sh` used `grep -v 'INFO\|WARNING\|ERROR\|运行模式'` to filter log noise. JSON output like `"status": "ERROR"` contains "ERROR" → the failure-reporting line was deleted. All 7 safety-check REJECTED messages were also swallowed.

**Fix B**: Changed all 3 grep instances to `grep -v '^[0-9]'`. Log lines start with timestamps (digits); JSON starts with `{` or `"`. Filters logs without touching JSON.

**Durable lesson**: Never filter mixed stdout (logs + structured data) by keyword content. Filter by line-format (timestamp prefix) or separate streams (logs→stderr, JSON→stdout).

### ~~P1: Slippage Not Recalibrating SL/TP~~ (FIXED 2026-07-28, Option A)

Gate 7 only handled "stop on wrong side of entry" (extreme). Normal slippage left SL/TP at plan prices → actual R:R degraded silently (e.g. plan R=1.0 → actual R=0.44 with 1% slippage on 2.7% stop distance). Take-profits were NEVER adjusted.

**Fix applied (Option A — shift prices, preserve R)**: Gate 7 rewritten to compute `delta = actual_entry - entry_price` and shift ALL prices (SL + every TP) by delta. Preserves the plan's relative structure (stop distance, R multiples). ~20 lines replacing the old "only fix wrong-side" logic.

**Critical companion change**: calibrated prices are **written back to the plan file** (`plan["stop_loss"]`, `plan["take_profits"]`, plus `plan["actual_entry"]` and `plan["slippage"]` for audit). Without this, `manage_position()` matches Algo orders against plan prices using a 0.01% tolerance — calibrated orders at shifted prices would never match → breakeven move would never fire. Write-back is best-effort (try/except); if it fails, exchange orders are still correct, only manage_position matching degrades.

**Why Option A over B (recalculate quantity)**: Option B touches `round_qty` and the fixed-margin model, higher complexity and regression risk. Option A's trade-off (SL closer to entry, may get stopped earlier) is actually correct behavior — "fixed risk per trade" means the distance is constant regardless of fill price.

**Durable lesson**: any system that places orders at pre-computed prices after a market-order fill MUST recalibrate against the actual fill. "Close enough" compounds across a backtest/live-test period and corrupts the R distribution the user is measuring.

### P1: Plan File Not Deleted After Opening (BY DESIGN as of 2026-07-28)

`execute_plan()` saves execution history but does NOT delete/rename the plan file. **This is now intentional**: the INVALIDATION re-fix (2026-07-28) requires the plan file to remain while a position exists, because `manage_all_positions()` needs it for TP1 breakeven moves and `detect_position_changes()` needs it for correct notification type (🔴止损 vs ⚪平仓).

The plan file is cleaned up by `detect_position_changes()` when the position disappears (watch cycle, ≤2min delay). The theoretical race (stale TRIGGER re-opening after close but before watch runs) is blocked by the "already has position" check during the position's life, and by the watch cleanup deleting the plan file + event files immediately after close detection.

**Do NOT "fix" this by deleting the plan file after opening** — it would break breakeven moves and notification accuracy. The current design is correct.

### P1: Cooldown Not Set in Generated Plans

Plans generated by trading-command-center workflow may lack `cooldown_seconds`. Without it, `signal_monitor.py`'s `should_emit()` has no cooldown → writes a TRIGGER event every minute while price is above trigger. The position check blocks re-entry, but this wastes resources and piles up event files.

**Fix approach:** Force `cooldown_seconds: 600` in plan generation (trade-execution-planner or command-center).

### P2: Event Consumed on Execution Failure

`process_events()` deletes the TRIGGER event file regardless of whether `execute_plan()` succeeded. If opening fails (API timeout, insufficient balance), the trigger opportunity is lost forever.

**Fix approach:** Only delete event file if `result["success"] == True`. On failure, leave it for retry next cycle (with a max-retry counter to avoid infinite loops).

### ~~P2: INVALIDATION Events Not Processed~~ (FIXED 2026-07-26, RE-FIXED 2026-07-28)

`process_events()` only handled TRIGGER/TP1_HIT/PLAN_EXPIRED. INVALIDATION events piled up unprocessed.

**First fix (2026-07-26)**: Added INVALIDATION branch — deleted plan file + `cancel_all_orders(symbol)` + deleted event file. Pushed to GitHub (commit 325a774).

**⚠️ CRITICAL BUG in first fix (found by external audit 2026-07-28)**: The INVALIDATION branch called `cancel_all_orders()` **without checking for active positions**. After a position was opened, the plan file remained (needed by `manage_position` for breakeven moves). If price then touched the invalidation level (which equals the stop-loss price — they're the same number!), INVALIDATION would fire and **strip the position's SL/TP Algo orders**, leaving it naked. Every component worked correctly in isolation; the composition was the bug.

**Why especially dangerous**: invalidation price = stop-loss price → bug fires exactly when protection is needed. Monitor reads `last` price (spiky); Binance SL uses `MARK_PRICE` (smooth) → a wick triggers INVALIDATION without triggering the exchange SL. `require_close: false` → one wick suffices.

**Re-fix (2026-07-28, 3 changes)**:
1. **INVALIDATION branch checks positions first** (~line 739): has position → skip (don't delete plan, don't cancel orders); no position → original cleanup; API failure → conservative (treat as has_position)
2. **`cancel_all_orders(symbol, force=False)` gained position guard** (~line 293): default refuses if position exists; `force=True` bypasses; API failure → conservative refusal. Defense-in-depth for all callers.
3. **CLI `cancel-all` requires `--force`** for live positions (~line 976)

**Verified unaffected**: `detect_position_changes()` calls `cancel_all_orders` only after position disappeared → guard sees no position → proceeds ✅

**Design decision**: plan file NOT deleted when position exists (needed by manage_all_positions for breakeven + detect_position_changes for notifications). Trade-off: monitor keeps writing INVALIDATION events (harmless, ~5 API weight/min).

**Durable lesson**: any code path that cancels exchange orders MUST first verify no active position depends on those orders. "Cancel" and "has position" are coupled state that must be checked together, never assumed from context.

### ~~P0: Entry Deviation Gate~~ (IMPLEMENTED 2026-07-26 via AAVE incident)

**Incident**: AAVE plan created 7/25 09:02 (trigger 92.4, SL 93.2). Trigger fired at 01:48 but was blocked by max_positions (2 slots full). Blocked for 13 hours. When NEAR stopped out at 15:21, AAVE immediately entered at 93.22 (market had moved). SL 93.2 < entry 93.22 → Binance rejected the stop order (400: trigger would fire immediately) → position ran unprotected ("裸奔") → user manually closed at 95.65 for -2.43U loss. With proper SL at 93.2, loss would have been -0.87U.

**Root cause**: No check between "trigger price" and "actual execution price". When a trigger is queued for hours, the market moves past the stop-loss level, making the stop invalid at execution time.

**Implemented as TWO gates in `execute_plan()`:**

Gate 6 — Entry deviation check (BEFORE the market order, reuses `current_price` already pulled by safety check #2):
```
_stop_dist = abs(entry_price - stop_loss)
_price_dev = abs(current_price - entry_price)
if _price_dev > _stop_dist:
    → ABORT: return without opening (no position, no SL/TP)
    → step "deviation_check" status REJECTED
```
Wrapped in `try/except NameError` — if safety check #2 failed to fetch `current_price`, the gate is skipped (logged as warning) and gate 7 below acts as backstop.

Gate 7 — Post-fill slippage calibration (AFTER market fill, BEFORE placing SL/TP):
```
actual_entry = float(order.get("avgPrice") or 0)
if actual_entry <= 0:                      # ⚠️ avgPrice is often null — see pitfall below
    fall back to get_positions()[symbol].entry_price
if actual_entry > 0:
    delta = actual_entry - entry_price
    if abs(delta) > 0:
        stop_loss += delta                 # shift SL by slippage
        for tp in take_profits: tp["price"] += delta   # shift all TPs
        # write calibrated prices back to plan file (manage_position needs them)
        plan["stop_loss"] = stop_loss; plan["take_profits"] = take_profits
        plan["actual_entry"] = actual_entry; plan["slippage"] = delta
        json.dump(plan, open(plan_path, "w"))   # best-effort
```

**⚠️ CRITICAL PITFALL — `avgPrice` is null on market orders**: Binance's market-order response frequently returns `avgPrice: null` (order submitted but not yet fully matched). The AAVE execution record literally shows `"avg_price": null`. Code that does `float(order.get("avgPrice"))` will crash or, with `or 0` guarding, silently skip the re-validation — defeating gate 7 entirely. **Always fall back to `get_positions()[symbol].entry_price` when `avgPrice` is null/0.** This was caught in code review before push; verify any future edit to gate 7 preserves the fallback.

**Rationale**: stop_distance = maximum acceptable loss. If price has already moved more than that from the trigger, the risk/reward is broken — the stop either can't be placed or would trigger immediately.

**Why this doesn't false-positive on normal slippage**: Typical slippage is 0.01-0.05% of price. Stop distance is typically 1-3%. The gate only fires when deviation EXCEEDS the entire stop distance — a massive move indicating the setup is no longer valid.

**Code location**: `execute_plan()` in `binance_executor.py`. Gate 6 after the 5 safety checks (~line 431); gate 7 after the market-order step (~line 490). ~30 lines total, touches no other function.

### ~~P2: Plan Expiry Not Enforced by Monitor~~ (FIXED 2026-07-28)

Plans have `expires_at` but `signal_monitor.py` previously didn't check it. Expired plans kept monitoring indefinitely.

**Fix applied**: `run_plan_path()` in `signal_monitor.py` now checks `expires_at` BEFORE evaluating rules. If expired: writes a `PLAN_EXPIRED` event file (consumed by executor's existing handler) and returns without evaluating. Handles timezone-aware and naive timestamps (naive treated as UTC). Plans without `expires_at` are unaffected (backward compatible). Duplicate PLAN_EXPIRED events are harmless (executor's handler is idempotent — second run finds plan file already deleted).

### ~~P2: Market Filter Purely Decorative~~ (FIXED 2026-07-28)

`market_filter` rules (BTC/ETH weakness detection) were evaluated by `signal_monitor.py` but emitted at `level: WATCH` → `write_event_file()` discarded them (only ALERT writes events). Breakout signals fired regardless of market conditions. The filter's result was never consumed by any downstream code.

**Fix applied**: `run_once()` in `signal_monitor.py` now checks if any evaluated event has `rule_type == "market_filter"`. If active, events with `rule_type in ("breakout", "pullback_reclaim")` are **blocked** (logged as `MARKET_FILTER_BLOCKED`, no event file written). **INVALIDATION events are NOT blocked** — if the market is crashing, the plan should still be invalidated/cleaned up. Fail-open design: if BTC/ETH data fetch fails, `evaluate_market_filter` returns False → no blocking (can't see the market ≠ market is definitely crashing).

**Design note**: the market_filter rule's `level: WATCH` in the plan JSON is now irrelevant to the blocking logic — blocking is driven by `rule_type`, not `level`. The WATCH level still prevents the filter itself from writing event files (correct — it's a gate, not a trigger).

**Known limitation + upgrade direction (discussed 2026-08-01, user selected 标准版 but DEFERRED — do NOT implement without approval):**

Current plan templates configure the filter as `timeframes: ["15m","1h"]` + `min_volume_ratio: 1.2`. Two gaps:
- 15m/1h is short-timeframe noise — a brief bounce clears the filter even inside a real downtrend
- `min_volume_ratio: 1.2` requires volume; a typical 退潮 (shrinking-volume grind-down) never triggers it

Upgrade path (user-chosen but deferred):
- Plan template: `timeframes: ["4h"]`, `min_volume_ratio: 0` — pure trend gate, no volume requirement (zero-code change, lives in plan-generation template)
- `evaluate_market_filter()` (signal_monitor.py ~140-165): judge on the last *closed* 4H candle (`candle["close"]` vs `ma25`, `close` vs `open`) instead of live `last` price — live `last` on 4H wicks in and out of MA25 every candle (~10-line change)
- Effect: BTC 4H close < 4H MA25 → all long entries blocked; shorts still allowed (the filter is already directional, lines 153-162 long-vs-short branches)
- Trade-off user accepted: this would have blocked the 2026-08-01 ADA/BEAT longs (BTC 4H was bearish that evening). Full design + trade-off stored in fact_store fact #3; 连亏熔断 (consecutive-loss breaker) design in fact #4.

### ~~P2: Close-Type Detection Hardcoded to Long~~ (FIXED 2026-07-28)

`detect_position_changes()` had two defects in the "position disappeared" branch:

**Defect 1**: `direction` defaulted to `"long"` (line 893) and was only overwritten if the plan file existed. When the plan file was already deleted (by INVALIDATION cleanup, prior watch cycle, or manual cleanup), short positions used the long PnL formula: `pnl = (current - entry) × amount` → sign reversed, profit reported as loss.

**Defect 2**: Close-type comparison ignored direction entirely. `current_price <= stop_loss * 1.002` only works for longs (SL below entry). For shorts (SL above entry), a profitable TP1 fill (price drops to TP1) satisfies `current_price <= stop_loss * 1.002` → reported as 🔴止损 instead of 🟢止盈.

**Fix applied**:
1. Direction inferred from `prev.get("amount")` sign (positive=long, negative=short) — same pattern already used in the "quantity reduced" branch (line 972). No longer depends on plan file existing.
2. Close-type judgment split into long/short branches: long checks `price <= SL` for stop and `price >= TP1` for profit; short checks `price >= SL` for stop and `price <= TP1` for profit.

**Why it didn't bite yet**: all plans so far have been `direction: "long"`. Will bite on the first short trade. Doesn't affect trade execution (exchange manages SL/TP), only notification accuracy and trading-history records.

**Durable lesson**: any code that infers trade direction should use the position's signed amount (always available in state snapshots), not a default value that depends on an optional file existing.

### P2: Two Position-Sizing Models Inconsistent (DEFERRED 2026-07-28, user decision)

Plan layer uses fixed-risk model (`quantity = risk_amount / stop_distance`); executor uses fixed-margin model (`quantity = margin × leverage / entry_price`). The executor ignores `plan.risk.quantity` entirely. Same 10U×10x position risks 0.78U (TRX, 0.78% stop) vs 2.69U (AAVE, 2.69% stop) — 3.4× difference.

**User decision**: defer until adding more capital and changing position sizing. "后期我会加入更多本金 仓位 甚至最大同时持仓数都会变化" — redesign both models together at that point.

**When revisiting**: three options were discussed — (A) fixed risk, (B) fixed margin (status quo), (C) fixed risk + notional cap. Option C recommended. Requires changing executor quantity calc + adjusting safety check #3 (notional validation) + possibly round_qty interactions.

### P2: Position-Full Queue Spam (user chose MANUAL mitigation 2026-07-26)

When max_positions is reached, pending monitors keep firing TRIGGER events every ~10 minutes. The executor blocks them ("已有持仓，跳过"), but events pile up and the monitor Crons keep running empty. In the AAVE incident, this queued for 13 hours before a slot opened — by which time the entry price had drifted past the stop distance.

**User's chosen mitigation**: manually say "清掉没触发的监控和计划" when positions are full. Deliberately NOT automated — user fears added complexity more than occasional manual cleanup.

**Do NOT auto-clean monitors on position-full unless user explicitly asks.** If implementing the auto-scan scheduler later, it could incorporate this (clean non-position monitors before scanning), but standalone automation of this was explicitly declined.

**Why it matters beyond spam**: the longer a trigger queues, the more the market drifts from the plan's trigger price. The entry deviation gate (gate 6, above) now catches the dangerous case (drift > stop distance → abort), so queue spam is now annoying-but-safe rather than dangerous.

## Pending Feature: Auto-Scan Scheduler (discussed 2026-07-24, NOT implemented)

User wants a fully-autonomous "find opportunities" loop. Design agreed in discussion; user said "后期再实现" (implement later). When the user asks to build it, use this design:

**Behavior:**
- Cron every 2 hours (12 runs/day).
- Check: any position OR any plan file? → if yes, do nothing (silent). If no → run the full trading-command-center scan→analyze→plan→monitor flow.
- **Critical: gate on plan FILES, NOT on Cron list.** Stale monitor Crons persist after a position closes (the plan file is deleted but the Cron keeps running empty). If the scheduler checks "is there a monitor Cron?", it will see the stale one and never run. The plan file is the correct signal of an active setup.
- Before scanning, clean up stale monitor Crons (delete all `*-monitor-check.sh` Crons except the event-processor and the scheduler itself), so they don't accumulate.
- Skip the run entirely if the BTC/ETH market filter fails (don't force a trade in a bearish tape).

**On/off switch (agreed: conversational + config fallback):**
- Primary: user says "开启自动扫描" / "关闭自动扫描" → `cronjob action=pause` / `resume` on the scheduler Cron.
- Fallback: `auto_scan: true/false` field in `trading-config.json`; the scheduler script checks it too (double safety in case the Cron is accidentally resumed).

**Open questions (ask user when implementing):**
- Time-of-day restriction (e.g. only 08:00–24:00 while user is awake)?
- Notify on "no opportunity found", or stay silent? (Leaning: silent, or a 6-hourly summary.)
- Implementation shape: lightweight script does the "any plan/position?" check (no token cost); only spawn an LLM session (with trading-command-center skill) when a scan is actually needed.

## Pending Feature: Web 交易面板 (discussed 2026-08-03, DEFERRED by user)

用户决策：**系统稳定盈利前不做**（"锦上添花，无法稳定赚钱则无必要"）。别主动推销。开工时要点：
- 架构已确认：独立 FastAPI 旁路服务（`~/.hermes/trading-web/`），只读 trading-plans/ + 子进程调 executor，**零侵入现有链路**；页面挂了不影响 Cron。用户已接受"方案 A：解析文本输出，零改动"
- 按钮设计：找机会（后台触发 trading-command-center 流程）、清理孤儿监控、状态展示（30s 轮询）
- 三个待拍板点：访问范围（localhost vs 公网反代鉴权）、找机会按钮是否需确认步、是否要盈亏曲线

## Multi-Bug-Fix Rigor Protocol (MANDATORY for trading system code changes)

User explicitly demands: "严谨 不能因为修改这个问题引入新的逻辑BUG". When fixing multiple bugs in one session:

### Per-Fix Protocol
1. **Before patching**: enumerate ALL callers/consumers of the code being changed (`search_files` for function names, variable names). Confirm each caller's behavior after the change.
2. **Patch**: minimal change, only the error/edge path. Normal flow must be byte-identical.
3. **After patching**: syntax check (`py_compile` / `bash -n`), then walk through 5+ scenarios including: normal flow, error flow, API failure, edge case, and interaction with prior fixes.

### Cross-Fix Verification (after ALL fixes applied)
4. **Re-read ALL modified files in full** (not just the diff hunks).
5. **Cross-check every pair of fixes**: does fix N change any assumption that fix M relies on? Key interactions to check:
   - Shared variables (e.g. `stop_loss` modified by slippage calibration → read by manage_position matching)
   - Shared files (e.g. plan file written by calibration → read by detect_position_changes)
   - Shared functions (e.g. `cancel_all_orders` guard → called from INVALIDATION + detect_position_changes + CLI)
   - Event flow (e.g. market filter blocks TRIGGER → but must NOT block INVALIDATION)
6. **Full lifecycle walkthrough**: trace one trade from plan creation → monitoring → trigger → open → calibrate → manage → TP1 → close → cleanup. Every branch must reach a valid end state.
7. **Report**: present a table of all fixes with status, then the cross-check results, then the lifecycle walkthrough. User needs to see the proof, not just "it's fine".

### User Communication During Code Changes
- **Explain with analogies FIRST, code SECOND.** User says "我有点看不懂" or "通俗举例" → use real-life scenarios (门卫/保险/菜市场/糖果). Map each element: "门卫 = signal_monitor, 锁门 = cancel_all_orders, 你 = 仓位".
- **Discuss feasibility BEFORE writing code.** User asks "是否可以...?" or "我们先探讨先不修改任何代码" → analyze pros/cons, present trade-offs, wait for explicit "OK 进行修复" before touching code.
- **Present severity assessment honestly.** If a bug only triggers under specific conditions (e.g. "only when you first short"), say so. User appreciates knowing "现在不咬你" vs "每笔都在发生".
- **Tables for status tracking.** After each fix, show a cumulative table: bug#, description, severity, status. User tracks progress this way.

## Post-Restart Health Check (网关/Hermes 重启后, verified 2026-08-03)

用户重启网关或更新 Hermes 后问"是否正常"，按此顺序查：

1. 进程：`ps aux | grep -iE "hermes|gateway"` + `systemctl list-units --type=service --state=running | grep hermes` + `ss -tlnp | grep 18789` — dashboard + gateway 都要在
2. `cronjob action=list` — **关键**：看 `last_run_at` 已恢复到当前时刻（调度器随 daemon 重启，必须确认 tick 恢复）
3. `tail ~/.hermes/logs/gateway.log` — 确认 `✓ weixin connected`（或对应平台重连成功；iLink 重启后第一条通知可能被 30s 限流吃掉，属正常）
4. 持仓/挂单在交易所侧，重启不影响：`positions` + `get_open_algo_orders` 复查数量即可
5. 日志扫描 `grep -iE "error|traceback" ~/.hermes/logs/*.log` — 区分真故障与无害项：dashboard 启动期 sqlite schema 竞态（自愈）、auxiliary 备用模型无 credit（预存状态）、tools.registry check_fn False（未配置项）都不是故障

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
4. **Cross-reference plan `expires_at` with running monitor Crons.** If all plans are expired but monitor Crons still run → they're harmless zombies (exit silently every minute). Tell the user and offer to clean them up. Same for **missing plan file entirely** (plan deleted without removing Cron — wrapper's `[ ! -f "$PLAN" ] && exit 0` makes it a silent zombie; detected 2026-08-03 IDOL).
5. `pgrep -af "signal_monitor"` — should return NOTHING (no background processes expected; if something shows up alongside a Cron, the process is stale — kill it)
6. `ls ~/.hermes/trading-events/` — should be empty unless a trigger just fired
7. **Check SL/TP orders for each open position**: `get_open_algo_orders(symbol)` — if ZERO orders exist, the position is unprotected ("裸奔"). Flag this to the user immediately and offer to re-place SL/TP. Common causes: placement failure at entry time, or orders already triggered/cancelled.

   ⚠️ **NEVER use `/fapi/v1/openOrders` or `/fapi/v1/allOrders` to check SL/TP status.** These endpoints ONLY list normal orders (MARKET, LIMIT). Algo conditional orders (STOP_MARKET, TAKE_PROFIT_MARKET placed via `/fapi/v1/algoOrder`) are **completely invisible** to them — they will ALWAYS return 0 for SL/TP, even when orders exist on the exchange. Using them leads to the false conclusion "no orders were ever placed" when in fact SL/TP are live on the exchange.
   
   **Correct check**: `python3 ~/.hermes/scripts/binance_executor.py positions` then for each symbol: query `GET /fapi/v1/openAlgoOrders?symbol=<SYMBOL>` (signed). Or use the executor's `get_open_algo_orders(symbol)` helper.
   
   **核对保护单价格（2026-08-03 验证）**: executor 挂单用「实际成交价 ± 计划距离」，不是计划绝对价。核对公式：SL ≈ 实际入场 + (计划SL − 计划触发价)，TP ≈ 实际入场 − (计划触发价 − 计划TP)。读 openAlgoOrders 的 `triggerPrice` 字段（`stopPrice` 恒为 null，字段名踩过坑）。9 单全对的实例：BTC 入场 62606.7 + 445 = SL 63051.7。
   
   **Incident (2026-07-30)**: Agent queried `/fapi/v1/openOrders` → 0 results → `/fapi/v1/allOrders` → only MARKET fills visible → concluded "executor NEVER placed SL/TP, positions are naked." User said "我币安后台能查到挂单啊" — orders existed on the exchange the whole time. The agent was looking at the wrong endpoint. Root confusion: the Algo Order API section above documents this, but the diagnostic flow didn't enforce it strongly enough.

### Architecture Reassurance (user often asks "过期会不会影响持仓？")

Price monitor Crons and position management are **completely independent**:

| Component | Depends on | Affects |
|-----------|-----------|---------|
| Price monitor Crons (1m) | plan.json files | **Opening** new positions only |
| Core trading-cron.sh (配置2m/实际3m) | Exchange API (live positions) | **Managing** existing positions (TP1, breakeven, watch) |

Deleting expired monitor Crons or plan files has **ZERO impact** on existing positions. The core cron queries Binance directly — it never reads plan files for position management. Always explain this clearly when the user worries about cleanup affecting their trades.

### Checking Position History (TP1/TP2 partial fills)

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

**Single-pair cleanup after a position fully closes (EXITED):**
- Delete `~/.hermes/trading-plans/<SYMBOL>-plan.json` + `<SYMBOL>-plan.state.json`
- Remove the symbol's monitor Cron (`cronjob action=remove`, name contains "价格监控")
- Archive the wrapper script: `mv ~/.hermes/scripts/<symbol>-monitor-check.sh ~/.hermes/scripts/archive/` (keep archive/ as the graveyard; scripts dir should only hold live monitors + executor + trading-cron.sh)
- Watch `write_file` sibling-modification warnings: another session (Web) may create/delete the same files — `rm` may report "No such file" because the sibling already removed it; that's fine, verify final state with `ls` instead of trusting the rm result.

### Pitfall: Stale Log Files
- `~/.hermes/trading-logs/signal-monitor.log` is written by the old `--loop` background process. After migrating to Cron, **this log stops updating**. Do NOT use it to judge whether monitoring is active. Check Cron output (`~/.hermes/cron/output/<job_id>/`) or `cronjob action=list` last_run_at instead.

## Reference

Read `references/system-architecture.md` for the full trigger-to-execution flow diagram, post-entry management, multi-symbol monitoring, file locations, and scanner data source details.
