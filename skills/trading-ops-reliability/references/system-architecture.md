# Trading System Architecture (Full Flow)

## Components

| Component | Frequency | Mechanism | Session-dependent? |
|---|---|---|---|
| Price monitor | Every 1 min | Cron (no_agent, script) | ❌ Survives session close |
| Event processor + position manager | Every 2 min | Cron (no_agent, script) | ❌ Survives session close |
| Stop-loss / TP1 / TP2 orders | Always | **Binance server-hosted** | ❌ Independent of everything |

## Trigger-to-Execution Flow

```
Price hits entry_trigger
  → Monitor Cron writes TRIGGER event to trading-events/
  → Event Cron (≤2 min) finds event
  → binance_executor.py process-events:
      1. Load plan JSON
      2. Check no conflicting position (max_positions=6)
      3. Five data-sanity checks:
         ① Direction: entry > stop (long) or entry < stop (short)
         ② Market deviation: |current - entry| < 10%
         ③ Notional: qty × price ≈ margin × leverage (±15%)
         ④ TP direction: TP > entry (long) or TP < entry (short)
         ⑤ Stop distance: < 20% from entry
      4. Set leverage + isolated margin
      5. Market open
      6. Place SL order (server-hosted)
      7. Place TP1 order (server-hosted)
      8. Place TP2 order (server-hosted)
  → Notify user via WeChat
```

## Post-Entry Management

| Event | Who handles | Mechanism |
|---|---|---|
| SL hit | Binance server | Auto market close |
| TP1 hit | Binance server + Cron | Server closes 50%, Cron moves SL to breakeven (entry price) |
| TP2 hit | Binance server | Auto market close remaining 50% |
| Plan expired (24h) | Cron | Delete plan + notify user |

## Worst Case: Everything Dies

If Hermes crashes, server shuts down, all Crons stop:
- ✅ SL/TP still execute (Binance server-hosted)
- ❌ TP1 → breakeven move won't happen (optimization lost)
- ❌ No WeChat notification
- The user's money is protected by exchange-hosted orders, NOT by our system.

## Multi-Symbol Monitoring

Each symbol gets its own independent Cron + plan file:
```
Cron every 1m: btc-monitor-check.sh   → reads BTCUSDT-plan.json
Cron every 1m: eth-monitor-check.sh   → reads ETHUSDT-plan.json
Cron every 2m: trading-cron.sh        → processes all events + manages all positions
```

Up to 6 positions can be open at a time (max_positions=6 config). If 6 positions are already open, a 7th trigger is rejected until one closes.

## Key File Locations

| File | Purpose |
|---|---|
| `~/.hermes/trading-plans/<SYMBOL>-plan.json` | Trade plan (entry, SL, TP, expiry) |
| `~/.hermes/trading-events/` | Trigger events (written by monitor, consumed by executor) |
| `~/.hermes/scripts/binance_executor.py` | Execution engine |
| `~/.hermes/scripts/trading-cron.sh` | Event processing + position management wrapper |
| `~/.hermes/scripts/<symbol>-monitor-check.sh` | Per-symbol price monitor wrapper |
| `~/.hermes/trading-config.json` | API keys + position sizing config (chmod 600) |

## Scanner Data Source

The binance-market-scanner pulls 4-timeframe K-lines for each symbol:
- 15m × 120 bars ≈ 30 hours (entry timing, volume, taker-buy ratio)
- 1h × 120 bars ≈ 5 days (trigger level = 1H prior high, MA7/MA25, range position)
- 4h × 120 bars ≈ 20 days (medium-term trend direction)
- 1d × 120 bars ≈ 4 months (macro trend, bull/bear alignment)

Symbol universe: all USDT perpetual contracts on Binance with 24h quote volume ≥ 50M USDT, top 100 by volume. Dynamic per scan, not hardcoded.
