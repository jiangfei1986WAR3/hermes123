# Operating Ported Codex Trading Skills in Hermes

Notes from porting the user's Codex "Trading Codex System" backup repo
(`jiangfei1986WAR3/jiaoyidashi`) into Hermes. The skill set: `trading-command-center`
(umbrella/router), `binance-market-scanner`, `trading-analysis`,
`trade-execution-planner`, `risk-manager`, `auto-signal-monitor`, `trade-review`.
Frontmatter loaded as-is; the operational quirks below are about RUNNING them.

## Install + adapt (worked)

1. `git clone <repo> /tmp/...`; `cp -r /tmp/<repo>/skills/* ~/.hermes/skills/`.
2. Fix hardcoded paths in SKILL.md **via Python `content.replace()`**, not sed —
   the single-backslash `C:\Users\...` form does not survive sed escaping.
   Map `C:\Users\<u>\.codex\skills\<s>\scripts\x.py` → `~/.hermes/skills/<s>/scripts/x.py`,
   `D:\Projects\codex1\<dir>` → a real Linux project dir (create with `mkdir -p`),
   and `python "..."` → `python3 "..."` (host has python3 only).
3. `auto-signal-monitor/scripts/signal_monitor.py` imported `winsound` + `ctypes`
   and used PowerShell TTS — replaced with the cross-platform `beep()`/`speak()`
   in `scripts/cross_platform_sound.py`. Remove unused `import ctypes` too.
4. Verify each script: `python3 -m py_compile <p>` then `python3 <p> --help`.
   All four scripts here are stdlib-only (urllib/json/argparse), no install needed.

## binance-market-scanner: real JSON shape + the key pitfall

Scan JSON top-level keys: `generatedAt, filter, counts, errors, results,
summaryRows, topLong, topShort, marketFilter, executableNow`.
- `results`: full per-pair (last/mark/changePct/funding/oi + 15m/1h/4h/1d K-line
  dicts + long/short score dicts + `state` + `execution` dict).
- `summaryRows`: flat CSV-style rows (executableStatus, entryLow/High, protection,
  target1, riskRewardToTarget1, stopDistancePct, executableReason).
- `topLong`/`topShort`: pre-sorted candidates (same shape as results items).
- `marketFilter`: `{longOk, shortOk, notes[]}` — when BTC/ETH are strong above
  1h/4h MA25, `shortOk:false` locks out all shorts.
- `executableNow`: pairs passing ALL execution checks — frequently `[]`.

**Pitfall:** `execution.status` is only computed for pairs whose `state` is
`LONG_TRIGGER_OR_CLOSE` / `SHORT_TRIGGER_OR_CLOSE`. Every other state
(LONG_WATCH, SHORT_WATCH, NEUTRAL) returns `NOT_EXECUTABLE` with reason
"scanner state is not trigger-or-close" no matter how high the score. So in a
calm/ranging market, `executableNow:[]` and zero WAIT_TRIGGER is the NORMAL
outcome, not a failure. Do NOT re-run or "fix" the scanner in that case.

## Fallback when nothing is executable (the common case)

When the user wants "the closest WAIT_TRIGGER / top 3 plans" but the scanner
returned no triggers:
1. Take `topLong` (or `topShort` if `shortOk`) sorted by score; pick top 2–3
   with the strongest multi-timeframe alignment (read `long.reasons`).
2. Derive levels from K-line data: trigger = `1h.recent20High` (long) /
   `1h.recent20Low` (short); protection = `1h.ma7` or recent swing; target1 =
   `1d.recent20High` / `1d.recent20Low`.
3. Feed into `trade-execution-planner/scripts/plan_calculator.py`:
   `--symbol --side --entry --stop --equity --risk-pct --leverage --tp TP1,TP2`.
   It returns entry/stop/risk/position/take_profits with `r_multiple`,
   `status: EXECUTABLE_AFTER_CONFIRMATION`, and manual `command_drafts`.
4. Label these plans `WAIT_TRIGGER` (price hasn't hit the trigger yet) and
   present full structure: entry, stop, TP1/TP2, R:R, position size, cancel
   condition, market-filter note. Flag high-ATR / extreme-funding pairs (e.g. a
   +49%/24h coin) as high-risk and drop leverage (5x vs 10x).

## Risk sizing convention that fit this user

`risk-manager`/`plan_calculator` default: 0.5% account risk per trade, compare
5x/10x/20x. Position sized by stop distance + risk amount, not by "use all
margin". All output is decision support — never login/place orders.
