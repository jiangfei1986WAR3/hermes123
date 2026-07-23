---
name: risk-manager
description: Calculate cryptocurrency futures position size, stop distance, risk amount, notional exposure, leverage effects, margin usage, and liquidation-risk warnings for 5x, 10x, 20x or custom leverage. Use when the user asks how much to open, how much they can lose, where stop loss risk sits, whether leverage is too high, position sizing for Binance futures, or risk comparison across leverage levels.
---

# Risk Manager

Use this skill to turn a trade idea into risk numbers before execution or to audit the risk of an open position. It does not place orders or operate funds.

## Safety

- Do not log in, place orders, set stop-loss/take-profit, or operate funds.
- Treat calculations as estimates. Exchange maintenance margin, fees, funding, slippage, and cross-margin account state can change actual liquidation risk.
- For futures, emphasize that risk is controlled by stop distance and position size, not by leverage alone.
- Prefer account-risk sizing over "use all margin" sizing.

## Workflow

1. Collect:
   - account equity or available margin
   - symbol and direction
   - entry price
   - stop/protection price
   - leverage: default compare `5x`, `10x`, `20x` unless user gives one
   - risk percent per trade, default `0.5%` if unspecified
   - optional target price
2. Run `scripts/risk_calculator.py` when exact numbers are needed.
3. Explain:
   - stop distance percent
   - risk amount in USDT
   - risk-based notional position
   - estimated initial margin at each leverage
   - approximate adverse move to liquidation
   - whether stop is too close to liquidation
   - R multiple if target is provided
4. Tie the result back to the user's framework:
   - single-trade risk commonly `0.3%` to `1%`
   - avoid high leverage for unclear signals
   - do not average down losing futures positions

## Script Usage

Example:

```powershell
python3 "~/.hermes/skills/risk-manager/scripts/risk_calculator.py" --equity 68 --entry 0.7975 --stop 0.781 --side long --risk-pct 0.5 --leverages 5,10,20
```

Optional target:

```powershell
python3 "~/.hermes/skills/risk-manager/scripts/risk_calculator.py" --equity 68 --entry 0.7975 --stop 0.781 --target 0.84 --side long --risk-pct 0.5
```

## Reference Routing

Read `references/risk-rules.md` when explaining risk principles, leverage warnings, or how the calculator maps to the user's trading framework.

Use `trading-analysis` if the user also asks whether the entry/stop is technically valid.

## Output Format

Answer in Chinese unless the user asks otherwise:

```text
结论：
输入：
止损距离：
仓位建议：
5x/10x/20x 对比：
强平/爆仓风险：
按你的文档框架：
风险提醒：
```

If inputs are missing, compute what can be computed and state the assumptions clearly.
