# Binance Market Scanner Scoring

This scanner uses the user's trading-document framework in a compact, machine-scannable form.

## Data Inputs

For each USDT perpetual symbol, collect:

- 24h ticker: last price, change percent, quote volume
- premium index: mark price, funding rate
- open interest
- klines: `15m`, `1h`, `4h`, `1d`

**Important**: The last (unclosed) kline from Binance is always excluded. All indicators
are computed on closed candles only, eliminating scan-timing bias on volRatio etc.
Requests fetch 121 bars so that 120 remain after exclusion.

For each timeframe compute:

- close, high, low
- MA7, MA25, MA99
- current-volume / previous-20-average-volume
- taker-buy quote ratio over last 20 candles
- previous-20 high/low
- range position inside previous-20 high/low
- ATR percent

If fewer than 100 closed bars are available, the timeframe is marked
`dataQuality: "insufficient"` and the symbol is excluded from scoring
(state = `INSUFFICIENT_DATA`).

## Long Bias

Constructive long factors:

- 1D price above MA7 and MA7 above MA25
- 4H price above MA7 and MA7 above MA25
- 1H close above MA7
- 15m close above MA7
- 1H close breaks previous-20 high with volume ratio >= 1.3 (mutually exclusive with pullback)
- price pulls back near 1H MA25 with 0.5 <= volume ratio <= 0.9 while 4H remains constructive (mutually exclusive with breakout)
- 15m volume improves with taker-buy ratio >= 0.52
- funding is not extreme

Warnings:

- 24h gain is already very large
- price is below 1H short MA
- volume expands but price cannot reclaim short MA
- funding is extreme

## Short Bias

Constructive short factors:

- 1D price below MA7 and MA7 below MA25
- 4H price below MA7 and MA7 below MA25
- 1H close below MA7
- 15m close below MA7
- 1H close breaks previous-20 low with volume ratio >= 1.3
- 15m volume improves with taker-buy ratio <= 0.48
- funding is not extremely negative

Warnings:

- 24h drop is already very large
- funding is extreme
- low-position breakdown may be close to exhaustion; require rebound-failure confirmation

## Labels

- `LONG_TRIGGER_OR_CLOSE`: long score >= 60
- `LONG_WATCH`: long score >= 46
- `SHORT_TRIGGER_OR_CLOSE`: short score >= 60
- `SHORT_WATCH`: short score >= 46
- `AMBIGUOUS`: both sides >= 46 and score gap <= 8 — conflicting signals, do not enter
- `INSUFFICIENT_DATA`: one or more timeframes have fewer than 100 closed bars
- `NEUTRAL`: otherwise

Classification picks the stronger side first (no long-first order bias).

If BTC/ETH are weak, downgrade long conclusions and prefer waiting for confirmation.
If BTC/ETH are strong, downgrade short conclusions and prefer waiting for confirmation.
If BTC/ETH data is missing from the scan universe, the market filter conservatively
blocks both sides (`longOk: false, shortOk: false`).

## Stability Check

Each scan computes a Jaccard similarity against the previous scan's watchlist.
A warning is emitted when Jaccard < 0.5 (excessive list churn). The result is
stored in the output JSON under `stability`.

## Immediate Execution Layer

The optional `--executable-now` mode does not replace the labels above. It adds a stricter current-price execution layer for user prompts such as "find what can be entered now" or "scan for immediately executable signals."

Immediate long candidates require:

- base state `LONG_TRIGGER_OR_CLOSE`
- current mark price has broken the 1H previous-20 high
- current mark price remains inside the breakout entry band, using an ATR-based buffer capped between 0.3% and 1.0%
- BTC/ETH filter does not block longs
- 1H and 15m price remain above MA7
- volume confirmation from 1H volume ratio >= 1.2 or 15m volume ratio >= 1.2 with taker-buy ratio >= 0.52
- protection level below current price from 1H MA25, 15m previous-20 low, or 1H previous-20 low
- stop distance <= `--max-stop-pct`
- target1 reward/risk >= `--min-rr`

Immediate short candidates mirror the long rules:

- base state `SHORT_TRIGGER_OR_CLOSE`
- current mark price has broken the 1H previous-20 low
- current mark price remains inside the breakdown entry band
- BTC/ETH filter does not block shorts
- 1H and 15m price remain below MA7
- volume confirmation from 1H volume ratio >= 1.2 or 15m volume ratio >= 1.2 with taker-buy ratio <= 0.48
- protection level above current price from 1H MA25, 15m previous-20 high, or 1H previous-20 high
- stop distance <= `--max-stop-pct`
- target1 reward/risk >= `--min-rr`

Execution statuses:

- `EXECUTABLE_NOW`: current setup passes the strict immediate-execution layer.
- `WAIT_TRIGGER`: setup has not reached the trigger.
- `MISSED_ENTRY`: trigger happened, but price has moved beyond the entry band.
- `NOT_EXECUTABLE`: confirmation, market filter, protection, stop distance, or reward/risk failed.
