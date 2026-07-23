# Risk Rules

Use these rules for crypto futures risk calculations.

## Core Rules

- Single-trade planned loss should normally be `0.3%` to `1%` of account equity.
- Position sizing formula:

```text
notional_position = account_equity * risk_pct / stop_distance_pct
```

- Stop distance is the distance from entry to protection line:

```text
long_stop_distance_pct = (entry - stop) / entry
short_stop_distance_pct = (stop - entry) / entry
```

- Initial margin estimate:

```text
initial_margin = notional_position / leverage
```

- Leverage does not decide the loss at the planned stop; notional size and stop distance do.
- Higher leverage reduces margin required but moves liquidation closer.

## Leverage Guidance From The Trading Framework

- Trend breakout: prefer 2x to 4x
- Pullback confirmation: prefer 2x to 5x
- Liquidation reversal/low absorb: prefer 1x to 3x
- Catch-up/follower arbitrage: prefer 1x to 3x
- Counter-trend trades: avoid when possible; if attempted, keep very small

For user comparisons, still calculate 5x, 10x, and 20x when requested, but warn clearly when the leverage exceeds the framework's preferred range.

## Liquidation Approximation

For a rough educational estimate before exchange-specific maintenance margin:

```text
long_liq_approx = entry * (1 - 1 / leverage)
short_liq_approx = entry * (1 + 1 / leverage)
```

This is not exact. Binance maintenance margin, fees, funding, unrealized PnL, cross-margin balance, and bracket tiers change the real liquidation price.

## Red Flags

- Planned stop is close to or beyond approximate liquidation.
- Required initial margin is greater than account equity or available margin.
- User wants to risk more than 2% on one trade.
- Stop distance is so small that normal noise can hit it.
- User wants to add to a losing futures position.
- User wants 20x on an unconfirmed signal.

## Good Output

Always state:

- assumed equity
- risk percent and USDT risk
- entry, stop, stop distance
- suggested notional position from risk formula
- margin required under each leverage
- liquidation approximation and warning
- manual execution reminder
