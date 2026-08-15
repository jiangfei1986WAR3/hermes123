# Conditional Order Trigger Mechanics (verified 2026-08-02)

How STOP_MARKET / TAKE_PROFIT_MARKET actually behave at trigger time, with real
case data from the user's live account (BEAT trades). Use when explaining why
a TP/SL filled late, early, or at a worse price than the trigger.

## Two-step model: trigger ≠ fill

```
Step 1: mark price crosses trigger price  →  "alarm rings"
Step 2: a MARKET order sweeps the book   →  actual fill price = book, not trigger
```

The trigger price is a fuse, not a price guarantee. Fill price depends on book
liquidity at the moment of triggering.

## Mark price: shaves peaks, not speed (key insight)

`/fapi/v1/markPriceKlines` (BEAT 2026-08-02 01:21, last vs mark, same minute):

```
01:21  last: O=4.981  H=6.365  C=5.350   (wick +28%)
01:21  mark: O=4.979  H=6.066  C=5.502   (same-minute spike, ~4.7% shaved)
```

Mark price moves **synchronously** with last price during a wick — it is
smoother in amplitude, not slower in time. So "mark lags behind" is wrong;
"mark never reaches as high" is right.

## Trigger-certainty rule of thumb (two real cases)

| Overshoot beyond trigger | Mark crossing | Verdict |
|---|---|---|
| >5% (8/2: TP 5.128, last 6.365, +24%) | same minute | fills even on a 2-min flash-back — trigger already fired before the return |
| 2–5% | within ~1 min | safe |
| <1% (7/31: TP 4.282, last 4.299, +0.4%) | may never cross | mark shaves the peak below the trigger → no trigger → then SL hits |

7/31 death: last peaked 4.299 but mark probably topped ~4.27–4.28, below TP
4.282 → TP1 never fired → down-wick hit SL. It lost because of **insufficient
overshoot**, not insufficient dwell time.

## Stop-loss slippage is real (7/31 reverse-calc)

Planned SL 4.022, position ~24.3 units (10U × 10x / 4.122). Actual loss -3.67U
vs expected (4.122-4.022)×24.3 ≈ 2.43U → actual fill ≈ 3.97, **1.3% deeper
than the stop**. Market-stop guarantees exit, never price. Thin books + violent
wicks (1-min 8.5% swings) = bigger slippage. This is the accepted trade-off vs
STOP_LIMIT (which can fail to fill entirely on gaps).

## Practical implications

- A manual close can never catch the wick top: 6.365 existed for seconds with
  thin top-of-book depth; human reaction (push delay + 1–3s reaction + 3–10s
  UI) lands the order back in the 5.0–5.5 range anyway.
- System TP at 5.35 on 8/2 was not luck-of-the-tick: overshoot was huge (24%),
  so mark crossed inside the spike minute and the market order swept a still-
  liquid book at ~5.35.
- High-ATR small caps (BEAT: daily ATR ≈ 17%) are the worst case for both
  directions: up-wick → TP can fire fine if overshoot is big; down-wick → SL
  slippage is structural. Treat them differently from BTC-class pairs.
- 8/2 vs 7/31 form a complete mirror pair (up-wick TP win +6U vs down-wick SL
  loss -3.67U); both logged in fact_store (fact_id 1 and 6). Rule changes
  deferred until a third wick event per user's "record first, react on repeat".

## Verification tools (when reconstructing a fill timeline)

1. `/fapi/v1/markPriceKlines?symbol=X&interval=1m` — mark-price candles; the
   minute its H crosses the trigger is the trigger minute.
2. Last-price 1m candles (`/fapi/v1/klines`) + executor log timestamps — the
   executor's `watch` detection (every 2 min) is a *detection* delay, not a
   fill delay; fills usually happen 1 min after the spike.
3. Back out actual fill from realized PnL when `avgPrice` is unknown:
   `fill ≈ entry - realized_pnl / qty` (long) — proves slippage without API
   trade history.
