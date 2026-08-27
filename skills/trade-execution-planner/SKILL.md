---
name: trade-execution-planner
description: Convert cryptocurrency futures analysis, watchlist candidates, or monitor signals into execution-ready trade plans with concrete entry price, stop loss, take-profit levels, invalidation conditions, risk percentage, position size inputs, and Binance Futures order-parameter drafts. Use when the user asks to turn "can watch / breakout / pullback / breakdown" analysis into a practical plan, prepare a monitorable setup, generate manual order commands, validate whether a signal is executable, or bridge trading-analysis, risk-manager, auto-signal-monitor, and Binance Futures without placing orders.
---

# Trade Execution Planner

Turn a crypto futures idea into a complete execution plan. This skill is the missing bridge between analysis and monitoring/execution: it converts directional logic into exact prices, risk inputs, and order parameters.

## Safety

- Do not log in, place orders, set stops, close positions, transfer funds, or operate accounts.
- Do not call exchange execution tools directly. Generate order-parameter drafts or commands for manual confirmation only.
- Mark the plan `NOT_EXECUTABLE` when entry, stop, risk, or quantity cannot be determined.
- In generic workflows, prefer risk-based sizing over margin-based sizing; the user's fixed-margin live workflow is the explicit override below.
- Treat outputs as planning support, not financial advice or guaranteed prediction.
- Never average down losing futures positions as a default action.

## User System Override

For this user's live trading workflow, these rules override the generic risk-percent examples below:

- Fixed margin: 10 USDT.
- Leverage: BTC 20x; all other symbols 10x.
- Quantity: `qty = (10 × leverage) / entry_trigger`, rounded to exchange precision.
- Do not use the generic 0.5% equity-risk model or `plan_calculator.py` to size this user's live plans.
- Derive the stop from valid market structure with enough ATR room; never tighten it merely to fit a dollar-risk target.
- Calculate and display `risk_amount_usdt = qty × |entry_trigger − structural_stop|` from the trigger price, not current price.
- No fixed USDT risk amount is an automatic rejection threshold unless the user explicitly approves it. In particular, 2.6U is historical guidance, not an active hard gate.
- This skill is the single final decision layer for `PLAN_READY`, `WATCH_ONLY`, and `NOT_EXECUTABLE`. Historical checklists provide evidence but do not set the final status.

## Workflow

1. Identify the candidate direction, then evaluate both same-direction entry paths:
   - long: `breakout_long` and `pullback_long`
   - short: `breakdown_short` and `retest_short`
   - `range_trade` and `manage_existing_position` remain single-path workflows.
2. For each applicable path, either produce a numeric draft or mark `STRUCTURE_NOT_PRESENT`; never invent a trigger, pullback/retest zone, stop, or target merely to complete both paths. Failure of one path does not skip the other, and both may be rejected.
3. For every numeric draft, calculate on that path's own `entry_trigger`:
   - structural stop with adequate ATR room
   - nearest real structural TP1 and next TP2
   - TP1/TP2 R, fixed-margin quantity, displayed USDT risk
   - current-price/missed-entry state, market conflict, and cancellation condition
4. Compare valid drafts and select one path or none. Explain the decisive structural/R/execution-quality difference; do not add a new fixed threshold or automatic gate.
5. Only the selected path may become `PLAN_READY` and be handed to monitoring. Per symbol, output at most one runtime plan; unselected drafts are analysis only and must not create plan files, events, or Cron jobs. Never overwrite an existing same-symbol plan automatically.
6. Gather shared inputs:
   - symbol and direction
   - current price if available
   - trigger level or intended entry
   - protection/invalidation level
   - fixed margin and leverage from the user-system override
   - calculated risk amount for display/comparison (not risk-based sizing)
   - optional ATR, recent swing high/low, resistance/support zones, funding/OI/BTC/ETH filter
7. If the user only gives a vague idea, use `trading-analysis` first when available to define the trigger level, protection line, and target zones.
8. Read `references/execution-rules.md` when choosing entry buffers, stop buffers, target rules, monitor states, or executable-status rules.
9. For this user's live workflow, calculate quantity with the fixed-margin formula and calculate R/risk amount directly. Use `scripts/plan_calculator.py` only for unrelated generic risk-percent scenarios.
10. Produce the selected plan's:
   - executable status
   - entry trigger and order type
   - stop loss / invalidation
   - take-profit levels
   - risk amount and position size
   - monitor conditions
   - manual Binance Futures command drafts if requested or useful

## Executable Status

Use these labels consistently. Path drafts may also use `STRUCTURE_NOT_PRESENT`; it is a comparison result, not a deployable plan status:

- `WATCH_ONLY`: setup is interesting but has no concrete trigger or stop.
- `PLAN_READY`: entry, stop, targets, invalidation, and risk are defined, but trigger has not occurred.
- `EXECUTABLE_AFTER_CONFIRMATION`: trigger condition is met or can be placed as a conditional order, and sizing is complete.
- `NOT_EXECUTABLE`: required fields are missing, risk is invalid, stop is on the wrong side, or market filter cancels the trade.

## Required Output

Answer in Chinese unless the user asks otherwise. Use this structure:

```text
Conclusion:
Execution status:
Direction:
Entry plan:
Stop / invalidation:
Take-profit plan:
Position size and risk:
Monitor conditions:
Order-parameter draft:
Plan cancellation conditions:
Risk notes:
```

For JSON handoff to monitoring or execution tooling, also provide:

```json
{
  "symbol": "BTCUSDT",
  "direction": "long",
  "setup_type": "breakout_long",
  "status": "PLAN_READY",
  "entry": {
    "order_type": "STOP_MARKET",
    "trigger_price": 62500.0,
    "limit_price": null
  },
  "stop_loss": 61200.0,
  "take_profits": [
    {"price": 63800.0, "reduce_percent": 50},
    {"price": 65500.0, "reduce_percent": 50}
  ],
  "risk": {
    "margin_usdt": 10.0,
    "risk_amount_usdt": 3.9,
    "leverage": 20,
    "quantity": 0.003
  },
  "monitor": {
    "trigger_condition": "15m close >= 62500 AND vol_ratio >= 1.0",
    "min_volume_ratio": 1.0,
    "invalidation_condition": "15m close < 61200",
    "market_filter": "BTC/ETH not breaking key support",
    "expires_after": "24h"
  }
}
```

## Script Usage

Generic risk-percent calculator example (not for this user's fixed-margin live workflow):

```powershell
python3 "~/.hermes/skills/trade-execution-planner/scripts/plan_calculator.py" --symbol BTCUSDT --side long --entry 62500 --stop 61200 --equity 1000 --risk-pct 0.5 --leverage 10 --tp 63800,65500
```

The script returns generic risk-percent sizing output. It is not the sizing source for this user's fixed-margin live workflow.

## Integration

- Use `trading-analysis` before this skill when key levels are not yet defined.
- Use `risk-manager` when the user wants a deeper leverage/liquidation comparison.
- Use `auto-signal-monitor` after this skill to monitor the generated `entry`, `stop_loss`, `market_filter`, and `cancel_condition`.
- Use Binance Futures only after the user explicitly confirms live-account action. Before that, provide command drafts only.
