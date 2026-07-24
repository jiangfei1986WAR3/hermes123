---
name: binance-executor
description: Execute crypto futures trade plans on Binance via API. Reads plan JSON from trading-plans/, sets leverage and isolated margin, opens market orders, places stop-loss and take-profit orders, manages positions (TP1 reduce + breakeven move), processes trigger events from trading-events/, and provides emergency close/cancel. Use when the user confirms live trading execution, or when a signal monitor trigger event needs to be executed. Pairs with trade-execution-planner (generates plans) and auto-signal-monitor (detects triggers).
---

# Binance Executor

Execute trade plans on Binance USDT perpetual futures via REST API. This is the execution layer that turns plans into real orders.

## Safety

- Reads API keys from `~/.hermes/trading-config.json` (chmod 600).
- Config controls: fixed margin (10U), leverage (BTC 20x / others 10x), max positions (2), isolated margin only.
- API Key must have read + trade permissions. NEVER enable withdrawal permission.
- Every order gets a stop-loss. No position is left unprotected.
- Plans expire after 24 hours (configurable).
- Execution records saved to `~/.hermes/trading-history/`.

## Architecture

```
trading-plans/*-plan.json   ← trade-execution-planner writes these
trading-events/*-event.json ← signal-monitor writes trigger events here
trading-history/*.json      ← execution records
trading-executor.log        ← execution log
```

## Script

Main script: `~/.hermes/scripts/binance_executor.py`

### Commands

```bash
# Check balance
python3 ~/.hermes/scripts/binance_executor.py balance

# Check positions
python3 ~/.hermes/scripts/binance_executor.py positions

# Execute a plan
python3 ~/.hermes/scripts/binance_executor.py execute --plan ~/.hermes/trading-plans/UNIUSDT-plan.json

# Process all pending events (called by cron)
python3 ~/.hermes/scripts/binance_executor.py process-events

# Manage all active positions (TP1 reduce + breakeven)
python3 ~/.hermes/scripts/binance_executor.py manage

# Cancel all orders for a symbol
python3 ~/.hermes/scripts/binance_executor.py cancel-all --symbol UNIUSDT

# Emergency close (market)
python3 ~/.hermes/scripts/binance_executor.py close --symbol UNIUSDT --percent 100
```

## Plan JSON Format

Compatible with trade-execution-planner output:

```json
{
  "symbol": "UNIUSDT",
  "direction": "long",
  "setup_type": "breakout_long",
  "entry_trigger": 3.00,
  "stop_loss": 2.85,
  "take_profits": [
    {"price": 3.30, "reduce_percent": 50},
    {"price": 3.60, "reduce_percent": 50}
  ],
  "status": "PLAN_READY",
  "expires_at": "2026-07-23T10:00:00"
}
```

Also accepts nested `entry.trigger_price` format from execution-planner JSON handoff.

## Event JSON Format

Written by signal-monitor to `trading-events/`:

```json
{"type": "TRIGGER", "symbol": "UNIUSDT", "price": 3.01, "timestamp": "..."}
{"type": "TP1_HIT", "symbol": "UNIUSDT", "price": 3.30, "timestamp": "..."}
{"type": "PLAN_EXPIRED", "symbol": "UNIUSDT", "timestamp": "..."}
```

## Execution Flow

1. `process-events` scans `trading-events/` for TRIGGER events
2. For each TRIGGER: load plan → check no conflicting position → set leverage → set isolated → market open → place SL → place TPs
3. For TP1_HIT: check position → reduce 50% → move SL to breakeven
4. For PLAN_EXPIRED: delete plan file
5. `manage` runs periodically to catch TP1 hits between event checks

## Cron Integration

A cron job runs every 2 minutes:
1. `python3 ~/.hermes/scripts/binance_executor.py process-events` — handle triggers
2. `python3 ~/.hermes/scripts/binance_executor.py manage` — manage positions

## Position Management Rules

- Max 1 position at a time (configurable)
- TP1 hit → reduce 50%, move SL to entry price (breakeven)
- TP2 hit → exchange TP order auto-closes remaining 50%
- SL hit → exchange SL order auto-closes full position
- Plan expired (24h) → cancel monitoring, delete plan

## Pitfalls

- BTC quantity precision is 0.001, so 10U×20x at $115k = 0.001 BTC ($115 notional, ~5.75U margin). This is normal.
- Binance returns 400 for "no need to change leverage/margin" — the script handles this gracefully.
- If stop-loss order placement fails after opening a position, the position is unprotected. The script logs this as ERROR. Always verify orders after execution.
- Use `close` command for emergency market close if something goes wrong.
