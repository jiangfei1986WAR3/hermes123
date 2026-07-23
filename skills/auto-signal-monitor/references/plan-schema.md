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
- `pullback_reclaim`: price previously touches a pullback zone, does not break invalidation, then reclaims a trigger level.
- `invalidation`: price breaks a risk/protection level.
- `market_filter`: BTC/ETH or other filter symbols weaken/strengthen enough to block a setup.

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
  "pullback_low": 2.96,
  "pullback_high": 2.97,
  "reclaim_price": 3.0,
  "invalidation_price": 2.9,
  "timeframe": "15m",
  "min_volume_ratio": 1.1
}
```

## Market Filter Fields

```json
{
  "type": "market_filter",
  "symbols": ["BTCUSDT", "ETHUSDT"],
  "timeframes": ["15m", "1h"],
  "weak_if_below_ma25": true,
  "min_volume_ratio": 1.2,
  "message": "BTC/ETH weakening; block long entry"
}
```

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
      "weak_if_below_ma25": true,
      "min_volume_ratio": 1.2,
      "message": "BTC/ETH weakening; filter long entries"
    }
  ]
}
```
