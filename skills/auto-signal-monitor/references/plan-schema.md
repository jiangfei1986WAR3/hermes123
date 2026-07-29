# Monitor Plan Schema

Use one JSON object per monitored setup.

## Required Fields

```json
{
  "name": "UNI long breakout",
  "symbol": "UNIUSDT",
  "direction": "long",
  "market_filter_symbols": ["BTCUSDT", "ETHUSDT"],
  "intervals": ["15m", "1h"],
  "cooldown_seconds": 600,
  "alerts": {
    "sound": "beep",
    "speech": false,
    "wav_path": null
  },
  "rules": [
    {
      "id": "breakout_confirm",
      "level": "ALERT",
      "type": "breakout",
      "side": "above",
      "price": 3.0,
      "timeframe": "15m",
      "require_close": true,
      "min_volume_ratio": 1.2,
      "message": "UNI 15m volume breakout above 3.00"
    }
  ]
}
```

## Rule Types

- `breakout`: price crosses and, if `require_close` is true, candle close confirms the level.
- `pullback_reclaim`: price previously touches a pullback zone, does not break invalidation, then crosses the trigger level. Use `side: "above"` for long (reclaim upward) or `side: "below"` for short (reject downward). Default is `above`.
- `invalidation`: price breaks a risk/protection level.
- `market_filter`: BTC/ETH or other filter symbols move against the plan's direction enough to block entry. For long plans, blocks when filter symbols are weak; for short plans, blocks when filter symbols are strong. Direction is read from the plan's top-level `direction` field automatically.

## Common Rule Fields

- `id`: stable identifier.
- `level`: `WATCH` or `ALERT`.
- `type`: one of the rule types above.
- `side`: `above` or `below`.
- `price`: trigger price for breakout/invalidation.
- `timeframe`: Binance kline interval such as `15m`, `1h`, `4h`.
- `require_close`: true means use latest closed candle; false means allow live price.
- `min_volume_ratio`: current or closed candle volume divided by prior 20-candle average.
- `message`: user-facing alert text.

## Pullback Reclaim Fields

```json
{
  "type": "pullback_reclaim",
  "side": "above",
  "pullback_low": 2.96,
  "pullback_high": 2.97,
  "reclaim_price": 3.0,
  "invalidation_price": 2.9,
  "timeframe": "15m",
  "min_volume_ratio": 1.1
}
```

For short setups, use `"side": "below"` — the trigger fires when price is rejected from the pullback zone and breaks below `reclaim_price`; invalidation fires when price rises above `invalidation_price`.

## Market Filter Fields

```json
{
  "type": "market_filter",
  "symbols": ["BTCUSDT", "ETHUSDT"],
  "timeframes": ["15m", "1h"],
  "min_volume_ratio": 1.2,
  "message": "BTC/ETH moving against plan direction; block entry"
}
```

Direction is automatic: reads the plan's top-level `direction` field. Long plans are blocked when filter symbols are weak (below MA25 + bearish candle + volume). Short plans are blocked when filter symbols are strong (above MA25 + bullish candle + volume).

## Example UNI Plan

```json
{
  "name": "UNIUSDT long watch",
  "symbol": "UNIUSDT",
  "direction": "long",
  "market_filter_symbols": ["BTCUSDT", "ETHUSDT"],
  "intervals": ["15m", "1h", "4h"],
  "cooldown_seconds": 600,
  "alerts": {
    "sound": "beep",
    "speech": true,
    "wav_path": null
  },
  "rules": [
    {
      "id": "breakout_3",
      "level": "ALERT",
      "type": "breakout",
      "side": "above",
      "price": 3.0,
      "timeframe": "15m",
      "require_close": true,
      "min_volume_ratio": 1.2,
      "message": "UNI 15m closes above 3.00 with volume"
    },
    {
      "id": "pullback_reclaim",
      "level": "ALERT",
      "type": "pullback_reclaim",
      "side": "above",
      "pullback_low": 2.96,
      "pullback_high": 2.97,
      "reclaim_price": 3.0,
      "invalidation_price": 2.9,
      "timeframe": "15m",
      "min_volume_ratio": 1.1,
      "message": "UNI pullback holds 2.96-2.97 then reclaims 3.00"
    },
    {
      "id": "invalid_2_90",
      "level": "ALERT",
      "type": "invalidation",
      "side": "below",
      "price": 2.9,
      "timeframe": "15m",
      "require_close": false,
      "message": "UNI breaks below 2.90; long setup invalidated"
    },
    {
      "id": "market_filter",
      "level": "WATCH",
      "type": "market_filter",
      "symbols": ["BTCUSDT", "ETHUSDT"],
      "timeframes": ["15m", "1h"],
      "min_volume_ratio": 1.2,
      "message": "BTC/ETH moving against plan direction; block entry"
    }
  ]
}
```
