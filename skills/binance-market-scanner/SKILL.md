---
name: binance-market-scanner
description: Scan Binance USDT perpetual futures using public market data, save JSON/CSV snapshots, rank trading pairs by trend, pullback, breakout, breakdown, funding, OI, and volume conditions, summarize watchlist candidates, or run strict immediate-execution checks with EXECUTABLE_NOW when the user asks what can be entered now. Use when the user asks to scan Binance pairs, find suitable crypto futures setups, save Kline scan results, create a market watchlist, find pairs closest to a signal, find immediately executable setups, or rerun the user's trading-document-based screener.
---

# Binance Market Scanner

Use this skill to batch scan Binance U-margined perpetual markets and persist results for later review. This skill gathers market facts and ranks candidates; use `trading-analysis` for deeper interpretation of any selected pair.

## Safety

- Use only Binance public endpoints.
- Do not log in, read account data, place orders, set stops, or operate funds.
- Treat scores as watchlist filters, not trading instructions.
- For leveraged futures, always surface invalidation/protection levels before discussing entry.

## Workflow

1. Run `scripts/scan_binance_usdt_perps.py`.
   - Quality-first default for the user: allow a longer scan and use `--progress --timeout 45 --retries 3`.
   - Use quick scans only when the user explicitly asks for speed.
   - Add `--executable-now` only when the user explicitly asks what can be entered now, asks for immediate executable signals, or asks whether any scanned pair is currently tradable.
2. Save both JSON and CSV output under `/root/Documents/trae_projects/zhuandaqian/market-scans` unless the user gives another path.
3. Summarize:
   - total pairs scanned and filter settings
   - strongest long and short watchlists
   - pairs close to trigger but not confirmed
   - immediately executable candidates when `--executable-now` was used
   - major market filter from BTC/ETH
   - saved file paths
4. If the user asks about a specific result, load the saved JSON/CSV and use `trading-analysis` to analyze that pair.

## Script Usage

Default quality scan:

```powershell
python3 "~/.hermes/skills/binance-market-scanner/scripts/scan_binance_usdt_perps.py" --progress --timeout 45 --retries 3
```

Useful options:

```powershell
python3 "~/.hermes/skills/binance-market-scanner/scripts/scan_binance_usdt_perps.py" --min-quote-volume 50000000 --limit 100 --progress --timeout 45 --retries 3 --out-dir "/root/Documents/trae_projects/zhuandaqian/market-scans"
```

Deep quality scan:

```powershell
python3 "~/.hermes/skills/binance-market-scanner/scripts/scan_binance_usdt_perps.py" --min-quote-volume 30000000 --limit 100 --progress --timeout 45 --retries 3 --out-dir "/root/Documents/trae_projects/zhuandaqian/market-scans"
```

Fast scan, only when the user asks for speed:

```powershell
python3 "~/.hermes/skills/binance-market-scanner/scripts/scan_binance_usdt_perps.py" --min-quote-volume 50000000 --limit 40 --progress --timeout 15 --retries 1 --out-dir "/root/Documents/trae_projects/zhuandaqian/market-scans"
```

Strict immediate-execution scan, only when the user asks for current tradable candidates:

```powershell
python3 "~/.hermes/skills/binance-market-scanner/scripts/scan_binance_usdt_perps.py" --min-quote-volume 50000000 --limit 100 --progress --timeout 45 --retries 3 --executable-now --max-stop-pct 3 --min-rr 1.5 --out-dir "/root/Documents/trae_projects/zhuandaqian/market-scans"
```

The script writes:

- `*_binance-usdt-perp-scan.json`: full structured data and rankings
- `*_binance-usdt-perp-summary.csv`: flat summary for sorting/filtering

## Ranking Model

Read `references/scoring.md` when changing scoring rules or explaining why a symbol ranked high.

Default interpretation:

- `LONG_TRIGGER_OR_CLOSE`: possible long trigger or near-trigger; still requires manual confirmation.
- `LONG_WATCH`: structure is constructive but not confirmed.
- `SHORT_TRIGGER_OR_CLOSE`: possible short trigger or near-trigger; still requires manual confirmation.
- `SHORT_WATCH`: structure is weak but not confirmed.
- `NEUTRAL`: no actionable setup.

When `--executable-now` is enabled, keep the base labels above and add a separate execution layer:

- `EXECUTABLE_NOW`: current price is triggered and still inside the allowed entry band, BTC/ETH filter is not blocking the side, stop distance is within `--max-stop-pct`, and target1 has at least `--min-rr`.
- `WAIT_TRIGGER`: setup is valid enough to watch, but price has not reached the trigger.
- `MISSED_ENTRY`: trigger happened but current price has moved beyond the allowed entry band.
- `NOT_EXECUTABLE`: required confirmation, protection, market filter, stop distance, or reward/risk check failed.

Do not present `EXECUTABLE_NOW` as automatic execution. Treat it as manual-confirmation support and still surface entry band, protection, target1, cancellation reason, BTC/ETH filter, and risk notes.

## Output Format

Answer in Chinese unless the user asks otherwise. Use this structure:

```text
Conclusion:
Scan scope:
Long watchlist:
Short watchlist:
Near trigger but not confirmed:
Executable now:
Saved files:
Risk:
```

Keep the answer concise. Mention that execution is manual and that the scan does not place orders.
