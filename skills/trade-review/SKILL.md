---
name: trade-review
description: Review cryptocurrency futures trades using the user's trading documents and execution framework. Use when the user asks to复盘, review a trade, analyze why a trade won or lost, evaluate entry/exit/stop-loss/take-profit/add/reduce decisions, compare actual execution with the plan, find mistakes, or turn a completed Binance futures trade into lessons and rules.
---

# Trade Review

Use this skill to review completed or in-progress crypto futures trades. The goal is not to judge the user; it is to separate valid trade logic from execution mistakes and produce a tighter rule for next time.

## Inputs To Collect

Ask for missing facts only when they materially change the review. Useful fields:

- symbol, direction, futures type, margin mode, leverage
- entry price, exit price, current/mark price if still open
- position size or margin used
- stop/protection line planned before entry
- take-profit plan
- entry reason and timeframe watched
- screenshots or notes, if available
- whether add/reduce/exit actions happened
- BTC/ETH market context at entry

## Workflow

1. Identify the trade state: planned, open, partially closed, closed, or stopped out.
2. Reconstruct the original plan:
   - Why enter?
   - Where was the invalidation/protection line?
   - What was the expected target or exit condition?
   - What would prove the trade wrong?
3. Compare plan vs execution:
   - entry timing
   - stop/protection handling
   - take-profit handling
   - add/reduce decisions
   - whether the user moved rules emotionally
4. Interpret with the user's trading framework:
   - market environment first
   - trend and volume-price structure
   - protection line over prediction
   - no averaging down losing futures positions
   - reduce or exit when protection line breaks
5. Produce rule improvements:
   - one or two concrete next-time rules
   - avoid vague advice such as "be disciplined"

## Reference Routing

Read `references/review-framework.md` for the review checklist and scoring rubric.

When deeper market interpretation is needed, also use `trading-analysis` and read its relevant references:

- `entry-exit-position-management.md` for entry/exit/add/reduce/protection line logic
- `volume-price-analysis.md` for volume-price review
- `crypto-futures-system.md` for futures risk and market cycle framing

## Output Format

Answer in Chinese unless the user asks otherwise:

```text
结论：
交易事实：
原计划 vs 实际执行：
按你的文档框架：
做得对的地方：
主要问题：
下次规则：
风险提醒：
```

Do not claim certainty. If account operation is requested, refuse to trade or operate funds and provide manual review guidance only.
