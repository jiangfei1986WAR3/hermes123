# Post-fix audit protocol

Use this reference when a live trading-system code change has just been made and the user asks whether it introduced instability or a logic bug.

## Read-only audit sequence

1. Compare the live file with the backup or baseline. Confirm the exact diff and modification times before interpreting runtime logs.
2. Enumerate callers and shared variables around the changed predicate. Check cross-symbol impact, position-management assumptions, event routing, cleanup, and retry behavior.
3. Run `python3 -m py_compile` for Python and `bash -n` for affected shell wrappers.
4. Inspect Cron configuration and actual output timestamps. `every 1m` is configuration, not proof of a one-minute runtime interval; use three or more output timestamps to measure the real cadence.
5. For open positions, query Binance `positions`, symbol-scoped `userTrades`, and `get_open_algo_orders(symbol)` in the same pass. Algo SL/TP must be checked through `openAlgoOrders`, using `orderType`, `triggerPrice`, `quantity`, and `algoStatus`; `openOrders` is not evidence for Algo orders.
6. Run every active plan with `signal_monitor.py --dry-run` only. Never use production mode as a verification command because it writes events and can open a real position.
7. For changed pure predicates, run local boundary tests covering normal values, exact threshold, both sides of threshold, zero values, and a normal non-target symbol. Do not call order functions.
8. Report five sections: exact change scope, execution-chain audit, live runtime evidence, test evidence, and residual boundary risks. Explicitly distinguish regressions caused by this change from pre-existing behavior.

## State precedence

When historical logs and current exchange state disagree, use this precedence:

`Binance positions/userTrades > Binance Algo orders > executor log > local plan/state`.

A historical log may show several failed retries before a later successful fill. Never conclude “no position” from an old rejection without a same-pass live check.

## Trigger-to-fill timing

Price-monitor Cron and event-processing Cron are independent jobs. Record three timestamps separately: monitor detection/event write, event consumption, and exchange fill. Do not describe the theoretical schedule as a fixed latency. Measure actual cadence from Cron output files; configured `every 1m` may run at a different effective interval.

## Threshold-change review

If a global safety threshold is widened to accommodate one symbol's exchange precision, explicitly flag that all symbols in the shared executor now inherit the wider tolerance. Verify that ordinary symbols remain below the old threshold and that values just above the new threshold are still rejected. Treat this as an accepted boundary risk, not as proof that quantity sizing has been fully fixed.
