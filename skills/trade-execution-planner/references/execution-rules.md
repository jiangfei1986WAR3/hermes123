# Execution Rules

Use these rules to convert analysis into executable crypto futures plans. Prefer the user's trading framework and current market structure when they provide more specific levels.

## Required Fields

A plan is executable only when all fields are present:

- symbol
- direction: `long` or `short`
- setup type
- entry trigger price
- min_volume_ratio（触发量比门槛：突破类 ≥ 1.0，回踩类 ≥ 0.8，固定值）
- stop loss / invalidation price
- risk percent or fixed risk amount
- account equity or explicit position size
- take-profit logic
- cancel condition

If any required field is missing, output `WATCH_ONLY` or `NOT_EXECUTABLE`.

## Price Buffers

Use ATR when available. If ATR is unavailable, use conservative percentage buffers.

Breakout long:

- entry trigger = resistance + max(0.10% to 0.30% of price, 0.20 * ATR)
- stop = breakout level or recent pullback low - max(0.20% to 0.50% of price, 0.50 * ATR)
- cancel if price rejects back below the breakout level with weak volume or BTC/ETH filter turns risk-off

Pullback long:

- entry trigger = reclaim of support/MA/structure level after pullback confirmation
- stop = pullback swing low - max(0.20% to 0.50% of price, 0.50 * ATR)
- cancel if support breaks on closing basis or rebound volume is weak

Breakdown short:

- entry trigger = support - max(0.10% to 0.30% of price, 0.20 * ATR)
- stop = breakdown level or retest high + max(0.20% to 0.50% of price, 0.50 * ATR)
- cancel if price quickly reclaims support or BTC/ETH rebounds strongly

Retest short:

- entry trigger = failed reclaim / rejection near former support
- stop = retest swing high + max(0.20% to 0.50% of price, 0.50 * ATR)
- cancel if price closes back above the failed level

## Target Rules

Use both structure and R multiples:

- TP1: nearest meaningful support/resistance or 1R to 1.5R
- TP2: next structure zone or 2R to 3R
- For follower/catch-up coins, prefer faster TP1 and stricter invalidation
- For strong leaders, allow a runner only after stop is moved to breakeven or profitable territory

When structure levels conflict with R multiples, state the tradeoff and prefer the level that avoids poor reward/risk.

## Order-Type Mapping

Long:

- Breakout trigger not yet hit: `STOP_MARKET` buy above trigger
- Pullback limit entry: `LIMIT` buy near support only after confirmation
- Immediate entry: `MARKET` only if user explicitly accepts slippage/reconfirmation
- Stop loss: sell `STOP_MARKET`
- Take profit: sell `TAKE_PROFIT_MARKET` or reduce manually at targets

Short:

- Breakdown trigger not yet hit: `STOP_MARKET` sell below trigger
- Retest limit entry: `LIMIT` sell near resistance only after rejection
- Immediate entry: `MARKET` only if user explicitly accepts slippage/reconfirmation
- Stop loss: buy `STOP_MARKET`
- Take profit: buy `TAKE_PROFIT_MARKET` or reduce manually at targets

## Monitor States

- `WATCH`: price is approaching setup but no executable plan exists.
- `PLAN_READY`: all levels and sizing are defined; monitor can watch the trigger.
- `TRIGGERED`: trigger condition met; recheck market filter, spread, funding, and duplicate positions.
- `INVALIDATED`: stop/invalidation condition hit before entry; cancel the plan.
- `EXPIRED`: setup did not trigger within the defined time window.

## Risk Rules

- Default risk per trade: `0.5%` of equity unless user specifies otherwise.
- Conservative range: `0.3%` to `1.0%`.
- Avoid plans with reward/risk below 1.2R unless there is a clear scalp rationale.
- Do not make stop distance so tight that normal spread/noise can trigger it.
- Do not enlarge position size to compensate for a weak setup.
- Leverage changes margin usage, not the planned loss at the stop; position size and stop distance control risk.

## Binance Futures Draft Rules

When generating command drafts:

- Round quantity conservatively if exchange precision is unknown.
- Use command drafts only; require user confirmation for live execution.
- Include a leverage command only when leverage is specified.
- Prefer placing or drafting the protective stop immediately after entry.
- Before live execution, require checks for existing position, open orders, account mode, margin type, and symbol precision.
