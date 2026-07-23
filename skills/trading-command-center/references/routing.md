# Trading Command Center Routing

Use this reference to decide which child skill to use.

## Child Skills

### binance-market-scanner

Use when:

- user has no position and wants opportunities
- user asks to scan Binance futures
- user asks which pair is closest to a signal
- user asks what can be entered now or asks for immediately executable candidates
- user asks for a watchlist
- user wants saved JSON/CSV Kline scan results

Default scan preference:

- The user accepts longer waits for better opportunities.
- Prefer quality-first scanning with progress output, longer timeout, and retries.
- Use fast scan only when the user explicitly asks for speed or a quick check.
- Use `--executable-now` only when the user explicitly asks for current tradable candidates, direct entry candidates, or "do not give me setups that only wait."
- If a scan is slow but still printing progress, keep waiting.

Immediate-execution scan interpretation:

- `EXECUTABLE_NOW`: current price is triggered and still inside the allowed entry band; send the best candidate to `trade-execution-planner` for revalidation before sizing, monitoring, or command drafts.
- `WAIT_TRIGGER`: valid watch setup, but price has not reached the trigger.
- `MISSED_ENTRY`: trigger happened, but the current price is beyond the allowed entry band.
- `NOT_EXECUTABLE`: risk, confirmation, protection, reward/risk, or market filter failed.

### trading-analysis

Use when:

- user names a symbol and asks about trend
- user asks whether a setup is technically valid
- user asks entry/exit/stop/take-profit logic
- user asks whether to hold, add, reduce, or close
- user asks about funding/OI/volume-price structure
- a scanner candidate needs deeper interpretation

### trade-execution-planner

Use when:

- analysis says "can watch", "breakout", "pullback", "breakdown", or "retest" and the user needs concrete prices
- a setup must become entry, stop, TP1, TP2, risk, quantity, and cancel condition
- user asks whether a signal is executable
- user wants a monitorable plan instead of a vague alert
- user wants Binance Futures command drafts without live execution
- monitor fires and the plan needs revalidation before execution

Do not skip this skill before monitoring a new trade setup. Monitoring should watch a complete plan, not vague analysis.

### risk-manager

Use when:

- entry and stop are known
- user asks position size, margin, leverage, liquidation risk
- user mentions equity, margin, 5x, 10x, 20x, or risk percent
- user is about to enter a trade and needs sizing
- user is holding a leveraged position and asks if risk is acceptable

### auto-signal-monitor

Use when:

- a `PLAN_READY` trade plan exists
- user wants recurring checks
- user wants alerting for entry trigger, invalidation, expiration, BTC/ETH filter, funding/OI, or volume conditions

Do not use it as a substitute for execution planning.

### trade-review

Use when:

- trade is completed
- user asks to review a win/loss
- user wants to know what went wrong
- user wants next-time rules
- user provides entry/exit screenshots or trade history

## State Examples

`FLAT`:

- "Scan the market and find candidates."
- "I have no position, find opportunities."
- "Which pair is closest to a signal?"
- "Find what can be entered now."
- "Only show immediately executable setups."

`PLANNING`:

- "Can SOLUSDT be entered?"
- "Turn this breakout into an executable plan."
- "Give entry, stop, TP, and size."
- "Can this signal be traded?"

`PLAN_READY`:

- "Create a monitor for this plan."
- "Watch the entry and invalidation."
- "Alert me when the executable plan triggers."

`TRIGGERED`:

- "The monitor fired. Should I execute?"
- "The entry price has been reached, recheck the plan."
- "Generate command drafts after confirming it is still valid."

`HOLDING`:

- "I entered JTO at 0.7975; hold or close?"
- "Where should the stop move?"
- "Can I add?"
- "Monitor this open position."

`EXITED`:

- "Review that trade."
- "Why did this lose?"
- "What should I do differently next time?"

## Priority Rules

1. If the user is holding, manage open risk before scanning broadly.
2. If the user is flat, scan first unless they name a specific pair.
3. Before any suggested entry, define invalidation.
4. `EXECUTABLE_NOW` is not an order instruction; revalidate with `trade-execution-planner` before any sizing, monitor, or command draft.
5. Before monitoring a new trade, create a complete execution plan.
6. Before any position size, define account risk.
7. Before any command draft, confirm entry, stop, quantity, and cancel condition.
8. After any trade result, extract a reusable rule.

## Safety Refusals

Refuse only the prohibited action, not the whole task:

- Cannot place order -> can provide manual entry conditions or command drafts.
- Cannot set stop -> can provide stop reference and risk calculation.
- Cannot auto trade -> can monitor public data and notify.
- Cannot trade a vague signal -> can generate a required-field checklist.
