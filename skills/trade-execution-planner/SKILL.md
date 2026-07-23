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
- Prefer risk-based sizing over margin-based sizing.
- Treat outputs as planning support, not financial advice or guaranteed prediction.
- Never average down losing futures positions as a default action.

## Workflow

1. Identify the setup:
   - `breakout_long`
   - `pullback_long`
   - `breakdown_short`
   - `retest_short`
   - `range_trade`
   - `manage_existing_position`
2. Gather required inputs:
   - symbol and direction
   - current price if available
   - trigger level or intended entry
   - protection/invalidation level
   - account equity or risk amount
   - risk percent, default `0.5%` if unspecified
   - leverage preference, default compare or use `10x` for command drafts
   - optional ATR, recent swing high/low, resistance/support zones, funding/OI/BTC/ETH filter
3. If the user only gives a vague idea, use `trading-analysis` first when available to define the trigger level, protection line, and target zones.
4. Read `references/execution-rules.md` when choosing entry buffers, stop buffers, target rules, monitor states, or executable-status rules.
5. Run `scripts/plan_calculator.py` when entry, stop, equity, and risk percent are known and exact sizing/R values are needed.
6. Produce:
   - executable status
   - entry trigger and order type
   - stop loss / invalidation
   - take-profit levels
   - risk amount and position size
   - monitor conditions
   - manual Binance Futures command drafts if requested or useful

## Executable Status

Use these labels consistently:

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
    "equity_usdt": 1000.0,
    "risk_percent": 0.5,
    "risk_amount_usdt": 5.0,
    "leverage": 10,
    "quantity": 0.012
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

Use the calculator for exact sizing:

```powershell
python3 "~/.hermes/skills/trade-execution-planner/scripts/plan_calculator.py" --symbol BTCUSDT --side long --entry 62500 --stop 61200 --equity 1000 --risk-pct 0.5 --leverage 10 --tp 63800,65500
```

The script returns JSON with stop distance, risk amount, quantity, notional, initial margin, target R multiples, and Binance Futures command drafts.

## Integration

- Use `trading-analysis` before this skill when key levels are not yet defined.
- Use `risk-manager` when the user wants a deeper leverage/liquidation comparison.
- Use `auto-signal-monitor` after this skill to monitor the generated `entry`, `stop_loss`, `market_filter`, and `cancel_condition`.
- Use Binance Futures only after the user explicitly confirms live-account action. Before that, provide command drafts only.
