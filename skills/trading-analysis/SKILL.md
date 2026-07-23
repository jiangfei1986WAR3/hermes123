---
name: trading-analysis
description: Analyze cryptocurrency futures and Binance trading pairs using the user's trading documents. Use when the user asks about crypto futures trend, support/resistance, entry, exit, stop loss, take profit, holding, adding/reducing position, liquidation risk, leverage risk, volume-price behavior, market sentiment, funding/OI crowding, or trading pair selection.
---

# Trading Analysis

Use the user's trading framework as a decision aid for crypto futures analysis. Treat all conclusions as probabilistic trade planning, not guaranteed prediction or financial advice.

## Reference Routing

Read only the relevant reference files for the user's question:

- `references/crypto-futures-system.md`: Use for the full crypto perpetual futures framework, market cycle, trading pair screening, entry modes, holding rules, adding/reducing position, exits, risk control, scoring, alerts, and daily checklist.
- `references/entry-exit-position-management.md`: Use for concrete rules on entry, holding, protection lines, adding, reducing, exiting, leader/follower selection, and translating A-share short-term logic to crypto contracts.
- `references/volume-price-analysis.md`: Use for volume-price interpretation, high/low position context, divergence, shrinking volume, expanding volume, intraday execution confirmation, washout, distribution, and warning signals.
- `references/source.pdf`: Keep as the original source material. Prefer the Markdown references first; inspect the PDF only when the Markdown files are insufficient or the user explicitly asks about the original source.

## 数据拉取脚本（分析前必跑）

分析任何交易对之前，必须先运行数据拉取脚本获取原始K线数据：

```bash
python3 ~/.hermes/skills/trading-analysis/scripts/fetch_klines.py \
  --symbols <SYMBOL1>,<SYMBOL2> \
  --timeframes 15m,1h,4h,1d \
  --bars 100
```

脚本输出每个币每个周期的：
- 原始OHLCV（最近5根K线明细）
- MA7/MA25/MA99 + 均线排列状态
- MACD（DIF/DEA/柱 + 金叉死叉状态）
- RSI(14) + 超买超卖判断
- 布林带（上/中/下轨 + 位置）
- ATR(14)
- 支撑/阻力位（基于近期高低点）
- 量价分析（量比、主动买盘占比、放量K线标注）
- K线形态检测（十字星、锤子线、吞没、大阳/阴线）
- 资金费率、OI、24h行情

⚠️ 不要跳过此步骤直接用扫描器数据代替。扫描器是海选（52个币浅层筛选），本脚本是精选分析（≤3个币深度数据）。

## Analysis Workflow

When analyzing a live pair or position:

1. **运行 fetch_klines.py 拉取原始K线数据**（不可跳过）。
2. Identify the task type: trend analysis, entry setup, holding decision, stop loss, take profit, add/reduce position, exit, or trading pair selection.
3. Read the relevant reference file(s) based on Reference Routing.
4. 基于 fetch_klines.py 的输出数据（不是扫描器结果），进行独立分析：
   - 逐周期解读均线排列、MACD动能、RSI状态、布林带位置
   - 量价关系独立分析：哪根K线放量、放量方向、主动买盘占比变化
   - K线形态解读：是否有吞没、锤子、十字星等反转/确认信号
   - 支撑/阻力位标注：从实际K线高低点推导，不是拍脑袋
5. Separate the response into observed facts, framework interpretation, actionable scenarios, and risk controls.
6. Prefer protection-line logic over prediction: define what condition allows continued holding and what condition invalidates the trade. 保护线必须说明推导依据（基于哪个支撑位/均线/形态）。
7. 操作场景必须给分支：如果突破A则B，如果跌破C则D。不能只给一个方向。
8. For leveraged positions, prioritize capital preservation, liquidation distance, and profit protection over maximizing theoretical upside.

## Core Rules

- First judge market environment, then the trading pair, then the entry/holding/exit condition.
- Treat volume-price signals as context-dependent. The same volume pattern can mean continuation or distribution depending on position, trend, and market sentiment.
- For long positions, continued holding generally requires price above the protection line, healthy pullback behavior, no clear high-volume stagnation, and no obvious market-cycle deterioration.
- For short positions, continued holding generally requires price below the rebound pressure/protection line, weak rebound behavior, and no obvious reversal volume.
- Do not average down losing futures positions as a default response. Adding is allowed only when the original logic has been further validated.
- When profit reaches a meaningful multiple of initial risk, consider partial reduction and move the protection line into profitable territory.
- If price breaks the protection line, treat the original trade logic as damaged. Prefer exit or reduction over emotional holding.
- For follower or catch-up coins, use faster profit-taking and stricter invalidation than for clear leaders.

## Output Style

For trading analysis, answer in this structure unless the user asks for something shorter:

```text
结论：
事实：
按你的文档框架：
关键位置：
操作场景：
风险提醒：
```

When giving stop-loss or protection-line suggestions, provide a range and one practical reference price, plus the reasoning and tradeoff. Avoid claiming that a price is certain to hold.

When the user asks whether to hold or close, do not make a single absolute decision for the user. Give a risk-based preference such as "更偏向先减仓保护利润" or "继续持有的条件是..." and define invalidation levels.
