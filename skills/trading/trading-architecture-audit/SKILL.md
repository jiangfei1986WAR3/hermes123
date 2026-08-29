---
name: trading-architecture-audit
description: Audit trading architecture drift without changing runtime.
version: 0.1.0
author: User, Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [trading, audit, drift, read-only]
    related_skills: []
---

# Trading Architecture Audit

Read-only, on-demand audit for the user's trading architecture. It detects rule ownership drift, unapproved hard gates, broken references, deleted-tool revival, unexpected execution-file changes, and added/modified/removed files across the approved trading knowledge directories. It never scans markets, imports trading code, reads credentials, changes files, updates baselines, creates Cron jobs, or operates the account.

## When to Use

- Before a complete scan-to-plan workflow (`pre`).
- After that workflow (`post`).
- After a trading-related Self-improvement patch.
- Before pushing trading-system changes.
- When different sessions disagree about process or rules.

Do not use it for balances, positions, market analysis, plan generation, monitoring, or execution.

## Safety Boundary

- Run only `scripts/audit.py` with Python standard library.
- The script opens a fixed allowlist of Markdown, Python, shell, and JSON baseline files read-only.
- It does not import or execute scanner, monitor, executor, or Cron scripts.
- It does not use network APIs, exchange credentials, `cronjob`, or account endpoints.
- It never writes or auto-updates `references/approved-hashes.json`.
- It never repairs, reverts, deletes, pauses, approves, commits, or pushes anything.

## How to Run

Use `terminal`:

```bash
python3 ~/.hermes/skills/trading/trading-architecture-audit/scripts/audit.py --mode pre
python3 ~/.hermes/skills/trading/trading-architecture-audit/scripts/audit.py --mode post
```

Optional machine-readable output:

```bash
python3 ~/.hermes/skills/trading/trading-architecture-audit/scripts/audit.py --mode pre --json
```

## Procedure

1. Run `pre` before the complete trading workflow.
2. If result is `PASS`, continue with the normal trading command-center flow.
3. If result is `PASS WITH CHANGES`, no known architecture drift was found, but review the listed `ADDED/MODIFIED/REMOVED` trading documents before approving a new document baseline. This status does not block the workflow by itself.
4. If result is `DRIFT DETECTED`, stop only new scan/plan creation. Existing exchange SL/TP and position-management Cron remain untouched.
5. Review each finding and classify it as retain, downgrade to reference/proposed, or revert the exact patch. The auditor does not choose or act.
6. After an approved targeted repair, rerun `pre`; continue after `PASS` or reviewed `PASS WITH CHANGES`.
7. Run `post` after the workflow. A post failure blocks the next new workflow, not existing position custody.

## Severity

- `P0`: approved execution-file hash changed or a forbidden executable tool reappeared. Stop new plans and inspect the exact diff; never auto-close positions.
- `P1`: layer ownership drift, unapproved hard gate, Top candidates skipped before deep analysis, or fixed-margin rules replaced. Stop new scan-to-plan workflows.
- `P2`: an indicator is promoted to a standalone market conclusion, or a historical case is treated as an active rule. Do not use the new conclusion until reviewed.
- `P3`: broken reference, main-document case sediment, or maintenance issue. Report; it need not interrupt status checks.

## Baseline Changes

The approved runtime and document baselines are immutable during normal audits. `references/approved-hashes.json` contains five execution hashes. `references/approved-documents.json` inventories approved `.md/.json/.py/.sh` files in twelve trading knowledge directories. Updating either requires an explicit user instruction after reviewing the intended diff. The auditor itself has no update command.

## New Content Admission Check

Before adding or modifying any trading skill, reference, or incident-log entry, perform this lightweight manual check:

1. Is this a stable reusable rule, or a single incident?
2. Which system layer owns it?
3. Does it change another layer's final decision authority?
4. Does it introduce an unapproved hard gate? If so, mark it `PROPOSED / NOT ACTIVE` and do not deploy it.
5. Is there real evidence and a reproducible source?

Placement:
- Stable cross-scenario workflow → the owning skill.
- Detailed but stable mechanism → a reference file.
- Single incident or one-off numeric example → `incident-log.md`.
- Unapproved suggestion → a reference with `PROPOSED / NOT ACTIVE`.
- Runtime behavior change → a separate code-change audit; do not treat documentation approval as runtime approval.

This is a manual admission checklist only. It does not modify runtime behavior, auto-update baselines, or make the auditor enforce policy automatically.

## Pitfalls

- `PASS` proves the checked architecture invariants, not that a trade will win.
- A new legitimate trading file produces `PASS WITH CHANGES` until explicitly incorporated into the approved document baseline.
- Historical words such as “red line” are allowed only when the same document clearly marks them historical or `PROPOSED / NOT ACTIVE`.
- `post` can run before a session-end Self-improvement patch. The next `pre` remains the hard protection.

## Verification

A valid installation must satisfy all three:

1. `--mode pre` returns exit 0 and `PASS` on the approved current system.
2. A temporary fixture containing a candidate-owned final decision returns exit 1 without touching live files.
3. A temporary ordinary reference addition returns exit 0 and `PASS WITH CHANGES`.
4. A Jaccard-to-flat conclusion in `scan-json-structure.md` returns exit 1 and `JACCARD_OVERREACH`.
5. Hash and mtime checks confirm no trading runtime file changed during any test.
