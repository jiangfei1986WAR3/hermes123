# Binance Market Scanner Scoring

This scanner uses the user's trading-document framework in a compact, machine-scannable form.

## Data Inputs

For each USDT perpetual symbol, collect:

- 24h ticker: last price, change percent, quote volume
- premium index: mark price, funding rate
- open interest
- klines: `15m`, `1h`, `4h`, `1d`

For each timeframe compute:

- close, high, low
- MA7, MA25, MA99
- current-volume / previous-20-average-volume
- taker-buy quote ratio over last 20 candles
- previous-20 high/low
- range position inside previous-20 high/low
- ATR percent

## Long Bias

Constructive long factors:

- 1D price above MA7 and MA7 above MA25
- 4H price above MA7 and MA7 above MA25
- 1H close above MA7
- 15m close above MA7
- 1H close breaks previous-20 high with volume ratio >= 1.3
- price pulls back near 1H MA25 or a prior breakout level with volume ratio <= 0.9 while 4H remains constructive
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

- `LONG_TRIGGER_OR_CLOSE`: long score >= 70
- `LONG_WATCH`: long score >= 58
- `SHORT_TRIGGER_OR_CLOSE`: short score >= 70
- `SHORT_WATCH`: short score >= 58
- `NEUTRAL`: otherwise

If BTC/ETH are weak, downgrade long conclusions and prefer waiting for confirmation.
If BTC/ETH are strong, downgrade short conclusions and prefer waiting for confirmation.

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
