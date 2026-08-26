# Audit Rules

## Layer ownership

1. Scanner collects public data, scores/ranks the universe, and selects at most three opportunity candidates.
2. Every selected Top candidate runs `fetch_klines` and full `trading-analysis` before historical risk review.
3. `trading-candidate-screening` provides evidence only and cannot assign final plan status.
4. `trade-execution-planner` is the only owner of trigger, structural stop, targets, R, quantity, displayed risk, cancellation, and final status.
5. `trading-plan-format` validates arithmetic/schema/monitor compatibility; it does not reinterpret market direction.
6. `trading-ops-reliability` owns runtime/deployment reliability, not candidate selection order.

## Approved live sizing

- Fixed margin: 10U.
- BTC leverage: 20x.
- Other leverage: 10x.
- Max positions: 6.
- Quantity uses `entry_trigger`, not current price.
- Risk amount is displayed and compared; no fixed USDT hard gate is active.

## Proposal boundary

A new threshold or automatic rejection rule must be marked `PROPOSED / NOT ACTIVE` until the user explicitly approves it. Historical examples do not grant approval.

## Forbidden revivals

- `space_gate.py`
- `pivot_gate.py`

They may appear only in text that explicitly says historical/deleted/not active.

## Indicator interpretation

`stability.jaccard < 0.5` means candidate-list instability. It is not independently equivalent to climax, risk-off, no-trade, or flat positioning.

## Runtime integrity

The five execution hashes in `approved-hashes.json` are compared byte-for-byte by SHA-256. A mismatch is P0, but the auditor performs no action beyond reporting.

## Trading document inventory

`approved-documents.json` covers twelve core trading skill directories and `.md/.json/.py/.sh` files. The audit reports `ADDED`, `MODIFIED`, and `REMOVED` paths.

- No semantic finding + no document changes = `PASS`.
- No semantic finding + document changes = `PASS WITH CHANGES`.
- Any semantic/runtime finding = `DRIFT DETECTED`.

Document changes are evidence for review, not automatic failures. The baseline is never updated by the auditor.
