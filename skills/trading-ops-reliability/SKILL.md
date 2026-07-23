---
name: trading-ops-reliability
description: Operational reliability patterns for the user's live crypto trading system — Cron-based monitoring deployment, cross-session duplicate prevention, silence rules for notification scripts, executor behavior at trigger time, and exchange-hosted order safety. Load this skill whenever setting up, modifying, debugging, or explaining the trading system's runtime behavior (monitors, crons, executor, notifications).
---

# Trading Ops Reliability

Hard-won operational lessons from running the user's live Binance futures trading system. These complement the functional trading skills (auto-signal-monitor, binance-executor, trading-command-center) with deployment and reliability knowledge.

## Monitor Deployment: Cron Only, Never Background Processes

- **NEVER** use `terminal(background=true)` or nohup for long-running price monitors. They are session-scoped — closing the web page, disconnecting WeChat, or ending the TUI session kills them silently.
- **ALWAYS** use Hermes Cron (`no_agent=true`, script mode) for monitoring. Cron is managed by the daemon and survives all session closures.
- Pattern: create a wrapper script (`~/.hermes/scripts/<symbol>-monitor-check.sh`) that runs `signal_monitor.py` in single-shot mode, filters DONT_NOTIFY lines, and only outputs on ALERT/TRIGGER/EXPIRED. Then create a Cron with `schedule="every 1m"`, `no_agent=true`, `deliver=all`.
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
- Rule: if the script has nothing actionable to report, print nothing.

## No Re-Analysis at Trigger Time

- The executor's 5 checks are **data-sanity checks** (direction, market deviation <10%, notional ±15%, TP direction, stop distance <20%), NOT market re-analysis.
- At trigger: the system does NOT re-pull K-lines, re-evaluate trends, or check for flash crashes. Trigger + valid data = immediate entry.
- This is a deliberate user decision: small positions (10U margin), max loss ~0.75U per trade, speed matters for breakout strategies.
- If the user asks "will it re-analyze before entering?", answer honestly: NO.
- User considered adding 5m K-line confirmation but chose to run without it first, planning to add later if false breakouts become frequent.

## Notification Coverage Gap (CRITICAL — discovered 2026-07-22)

The `trading-cron.sh` (deliver=all) only notifies on events the **executor actively processes**. Exchange-hosted conditional orders execute **without any Hermes notification**:

| Event | WeChat notification? | Why |
|-------|---------------------|-----|
| Price reaches trigger | ✅ | Monitor Cron → signal_monitor ALERT → deliver=all |
| Open position success | ✅ | trading-cron.sh → executor output → deliver=all |
| TP1 reduce 50% + breakeven | ✅ | trading-cron.sh manage → deliver=all |
| Plan expired cleanup | ✅ | trading-cron.sh process-events → deliver=all |
| **TP2 full close (exchange)** | ❌ | Exchange conditional order fills, Hermes has no awareness |
| **Stop-loss hit (exchange)** | ❌ | Exchange conditional order fills, Hermes has no awareness |

**User impact**: After SL or TP2 executes, user doesn't know position is gone unless they check Binance app.

**Fix (pending implementation)**: Add "position disappearance detection" to trading-cron.sh:
1. Read plan symbols from `~/.hermes/trading-plans/`
2. Call `executor positions` to check if those symbols still have open positions
3. If plan exists but position gone → output notification ("SOL 仓位已消失，可能被止损/TP2平仓")
4. If position exists but plan expired/missing → output reminder

## Cleanup Procedure (user says "清掉所有监控和计划")

When user requests clearing all monitors and plans:
1. `cronjob list` → identify monitor Crons (name contains "价格监控" or script contains `monitor-check`)
2. Remove each monitor Cron (⚠️ NEVER remove `trading-cron.sh` event-processing Cron)
3. `rm ~/.hermes/trading-plans/*-plan.json *-plan.state.json`
4. `rm ~/.hermes/scripts/*-monitor-check.sh`
5. Verify: re-check Cron list + plans directory, confirm clean
6. Output report: what was deleted, what was preserved

## Exchange-Hosted Orders Are the Real Safety Net

- Stop-loss and take-profit orders live on **Binance servers**, not in our system.
- If Hermes crashes, all Crons die, or the server shuts down: SL/TP still execute on the exchange.
- The Cron-based TP1 reduce + breakeven move is an **optimization**, not a requirement.
- Margin mode (isolated) and leverage are set per-symbol at order time, regardless of what the user set on the Binance web UI. No conflict.

## System Resource Impact

- Monitor Cron: ~0 disk growth per day (silent mode writes nothing unless triggered)
- Trigger event file: ~1KB per trigger
- Estimated annual growth: <1MB
- CPU/memory impact: negligible (each Cron run is a single API call, <1 second)

## Binance Hedge Mode API Quirks (from 2026-07-22 code audit)

Hard-won API parameter conflicts when the account uses Hedge Mode (dual-side positions). These bit us during live ENA execution:

| Error Code | Trigger | Fix |
|------------|---------|-----|
| -1106 | `reduceOnly=true` + `positionSide=LONG/SHORT` on any order type | **All `reduceOnly` removed from codebase.** In Hedge Mode, `positionSide` alone tells Binance the order reduces a position. Applies to: TP orders, TP1 partial close, CLI close. |
| -4120 | `STOP_MARKET` or `TAKE_PROFIT_MARKET` on some symbols (e.g. ENA) via standard `/fapi/v1/order` | Fixed with `_place_conditional_order()`: tries 3 combos in order — (1) `closePosition=true`, (2) `quantity+reduceOnly`, (3) `quantity` only. Silently retries on -4120/-1106, raises other errors. Algo Order API returned 404 as of 2026-07. |
| -4136 | `MARKET` + `closePosition=true` | MARKET orders must use `quantity`, never `closePosition` |
| -1102 | `STOP_MARKET` without `quantity` or `closePosition` | Must send one of them |

**Scientific notation trap**: Binance filter strings like `"0.0000100"` become `"1e-05"` via `str(float(...))`, breaking decimal parsing → `decimals=0` → prices/quantities rounded to 0. Always parse precision from the **original string**, not from `str(float_value)`. Both `round_price()` and `round_qty()` are **fixed** (2026-07-22): parse from `tick_str`/`step_str` original strings. When `decimals==0` (e.g. ENA stepSize="1"), `round_qty()` returns `int` — Binance rejects `1142.0` but accepts `1142`.

**Integer quantity**: When `stepSize="1"`, `round_qty()` must return `int`, not `float`. Binance rejects `1142.0` but accepts `1142`.

**Post-execution verification**: After `execute_plan()`, always check individual step statuses (`stop_loss`, `take_profits`), not just top-level `success`. A known bug returns `success=true` even when ALL SL/TP orders failed, leaving the position unprotected.

Full audit with 10 bugs ranked by severity: see `binance-executor` skill references (code-audit-2026-07-22).

## Quick Diagnostic Checklist

When the user asks "is the monitor running?" or "check the system":

0. `session_search query="监控 OR monitor OR cron" sort=newest limit=3` — check if another session changed the architecture recently (PREVENTS conflicting actions)
1. `cronjob action=list` — verify monitor + event-processing Crons are enabled and running
2. `curl -s "https://fapi.binance.com/fapi/v1/ticker/price?symbol=<SYMBOL>"` — current price
3. `cat ~/.hermes/trading-plans/<SYMBOL>-plan.json` — plan details + expiry
4. `pgrep -af "signal_monitor"` — should return NOTHING (no background processes expected; if something shows up alongside a Cron, the process is stale — kill it)
5. `ls ~/.hermes/trading-events/` — should be empty unless a trigger just fired

### Pitfall: Stale Log Files
- `~/.hermes/trading-logs/signal-monitor.log` is written by the old `--loop` background process. After migrating to Cron, **this log stops updating**. Do NOT use it to judge whether monitoring is active. Check Cron output (`~/.hermes/cron/output/<job_id>/`) or `cronjob action=list` last_run_at instead.

## Reference

Read `references/system-architecture.md` for the full trigger-to-execution flow diagram, post-entry management, multi-symbol monitoring, file locations, and scanner data source details.
