# 加密合约交易技术报告：量价与情绪系统工程化方案

> 本报告基于《超哥财经最新笔记.pdf》以及两份整理文档：《量价关系笔记整理与分析.md》《进出场持仓加减仓与交易对选择总结.md》。原始经验来自 A 股短线、题材、龙头、量价和分时体系；本报告将其迁移为适用于加密货币永续合约的可执行框架。本文仅用于交易研究、复盘和系统设计，不构成投资建议。

## 1. 核心思想

A 股笔记中的底层逻辑可以迁移到加密合约，但不能照搬形式。A 股里的“题材、龙头、板块梯队、涨停、换手、保护线”，在加密合约里应转换为“赛道叙事、强势币、成交额梯队、波动突破、OI 变化、资金费率、清算结构、动态止损”。

本系统的核心原则：

1. 先选方向，再选交易对，最后找入场点。
2. 价格只告诉你结果，成交量、OI、主动买卖量、资金费率告诉你资金状态。
3. 进场看确认，持仓看保护线，加仓看趋势验证，减仓看滞涨和拥挤，离场看破位和退潮。
4. 合约交易里，任何信号都必须服务于风险定义：哪里进、哪里错、哪里加、哪里减、哪里走。

## 2. A 股逻辑到加密合约的映射

| A 股笔记概念 | 加密合约对应概念 | 使用方式 |
| --- | --- | --- |
| 主线题材 | 当前资金最集中的赛道叙事 | AI、MEME、L2、SOL 生态、RWA 等 |
| 龙头股 | 龙头币 | 同赛道涨幅、成交额、承接最强的币 |
| 中军 | 大市值核心币 | 流动性更好、趋势更稳、资金容量大 |
| 后排补涨 | 补涨币、跟风币 | 只做套利，不按龙头持仓 |
| 换手 | 成交额、OI 周转、主动买卖量 | 判断筹码交换和资金接力 |
| 涨停突破 | 放量突破关键位 | 判断趋势启动 |
| 分时买点 | 1m/5m/15m 入场结构 | 执行层确认 |
| 止损/止盈保护线 | 动态失效位 | 合约风控核心 |
| 出货 | 高位滞涨、OI 拥挤、资金费率极端 | 减仓或离场 |
| 退潮 | 龙头转弱、板块普跌、BTC/ETH 破位 | 降仓或空仓 |

## 3. 系统总流程

工程化流程分为六层：

1. 市场状态层：判断 BTC/ETH 和全市场风险环境。
2. 赛道选择层：找当前资金最集中的方向。
3. 交易对筛选层：筛龙头、中军、补涨和可做空弱势币。
4. 信号识别层：识别突破、回踩、止跌、滞涨、破位。
5. 仓位管理层：决定进场、持仓、加仓、减仓、离场。
6. 风控执行层：处理止损、止盈、最大亏损、资金费率、滑点和极端波动。

## 4. 数据字段设计

### 4.1 基础行情字段

| 字段 | 含义 | 用途 |
| --- | --- | --- |
| `symbol` | 交易对 | 如 `BTCUSDT`、`SOLUSDT` |
| `price` | 最新价 | 当前市场价格 |
| `open/high/low/close` | K 线价格 | 判断趋势、突破和回踩 |
| `volume` | 成交量 | 判断放量、缩量 |
| `quote_volume` | 成交额 | 比单纯成交量更适合跨币比较 |
| `atr` | 平均真实波幅 | 设置止损距离和仓位 |
| `vwap` | 成交量加权均价 | 判断盘中强弱 |

### 4.2 合约专属字段

| 字段 | 含义 | 用途 |
| --- | --- | --- |
| `open_interest` | 持仓量 OI | 判断新资金入场还是平仓推动 |
| `oi_change_pct` | OI 变化率 | 判断多空拥挤或爆仓释放 |
| `funding_rate` | 资金费率 | 判断多空拥挤程度 |
| `taker_buy_volume` | 主动买入量 | 判断主动买盘 |
| `taker_sell_volume` | 主动卖出量 | 判断主动卖盘 |
| `taker_buy_ratio` | 主动买入占比 | 判断进攻方向 |
| `long_short_ratio` | 多空人数或账户比 | 反映市场倾向，不能单独使用 |
| `liquidation_long` | 多头清算量 | 判断多杀多和恐慌释放 |
| `liquidation_short` | 空头清算量 | 判断轧空和逼空 |
| `mark_price` | 标记价格 | 合约强平和风险判断 |
| `basis` | 合约与现货价差 | 判断过热或贴水 |

### 4.3 派生指标字段

| 字段 | 计算方式 | 含义 |
| --- | --- | --- |
| `volume_ratio` | 当前量 / N 周期均量 | 放量或缩量 |
| `range_position` | 当前价在 N 周期高低点区间的位置 | 判断高位、中位、低位 |
| `price_efficiency` | 涨跌幅 / 成交量变化 | 判断量价推进效率 |
| `trend_score` | 均线、HH/HL、ADX 等组合 | 趋势强弱 |
| `sector_rank` | 同赛道涨幅/成交额排名 | 判断龙头和补涨 |
| `crowding_score` | funding + OI + 多空比 | 判断拥挤风险 |
| `breakout_score` | 突破强度 + 放量 + OI | 判断突破有效性 |
| `reversal_score` | 清算释放 + 止跌 + 主动买盘 | 判断反转质量 |

## 5. 交易对筛选方案

### 5.1 第一层：排除不可交易标的

先排除风险过高的交易对：

1. 24 小时成交额过低。
2. 买卖盘深度差，点差过大。
3. 经常插针，K 线不连续。
4. 资金费率长期极端。
5. 刚上线、缺少历史数据。
6. 合约盘口深度明显小于你的计划仓位。

建议基础阈值：

```yaml
min_quote_volume_24h: 50_000_000
max_spread_pct: 0.05
min_history_days: 60
max_single_order_depth_pct: 0.2
```

说明：这些阈值不是固定真理，需要按交易所、账户规模和周期调整。小资金可以放宽成交额，大资金必须更严格。

### 5.2 第二层：判断市场方向

先判断 BTC/ETH 是否支持交易：

| 市场状态 | 条件示例 | 交易动作 |
| --- | --- | --- |
| 强多 | BTC/ETH 在 4H 和 1D 均线上方，回调缩量 | 优先做多强势币 |
| 震荡 | BTC/ETH 在区间内反复，方向不明 | 降低仓位，只做边界交易 |
| 弱空 | BTC/ETH 跌破关键支撑，反弹无量 | 优先空弱势币，不做补涨多 |
| 极端风险 | BTC/ETH 放量破位，市场普跌 | 空仓或只做小仓反抽 |

### 5.3 第三层：选择赛道

将交易对按叙事或板块分组，例如：

```yaml
sectors:
  AI: [TAO, FET, RNDR, WLD]
  L1: [SOL, AVAX, SUI, SEI]
  L2: [ARB, OP, STRK]
  MEME: [DOGE, PEPE, WIF, BONK]
  RWA: [ONDO, PENDLE]
```

赛道强度评分：

```text
sector_score =
  0.35 * sector_return_rank
  + 0.25 * sector_quote_volume_rank
  + 0.20 * sector_breadth
  + 0.20 * sector_leader_strength
```

判断原则：

1. 优先选择涨幅靠前且成交额同步放大的赛道。
2. 优先选择有龙头带动、多个币共振的赛道。
3. 不做只有单币独涨、板块无响应的方向。
4. 龙头已高位滞涨时，不再追后排补涨。

### 5.4 第四层：选择龙头、中军、补涨

龙头币评分：

```text
leader_score =
  0.25 * return_24h_rank
  + 0.20 * return_7d_rank
  + 0.20 * quote_volume_rank
  + 0.15 * oi_growth_quality
  + 0.10 * taker_buy_strength
  + 0.10 * drawdown_resilience
```

中军币标准：

1. 同赛道成交额最大或排名靠前。
2. 趋势稳定，回撤小。
3. OI 增长平稳，资金费率不过热。
4. 更适合趋势持仓和较大仓位。

补涨币标准：

1. 属于同一强势赛道。
2. 前期活跃，有成交额基础。
3. 涨幅落后龙头，但已经开始放量。
4. 龙头仍强，没有退潮信号。
5. 只按套利处理，不按趋势龙头持仓。

## 6. 市场周期模型

将 A 股笔记中的“冰点、启动、发酵、高潮、分歧、修复、退潮”迁移为加密市场状态：

| 周期 | 加密市场表现 | 交易策略 |
| --- | --- | --- |
| 冰点 | 多数币破位，清算量大，情绪极弱 | 不急抄底，等止跌 |
| 企稳 | 龙头不再新低，BTC/ETH 稳住 | 小仓试错 |
| 启动 | 龙头放量突破，赛道共振 | 做龙头或中军 |
| 发酵 | 补涨出现，成交额扩散 | 持仓，谨慎加仓 |
| 高潮 | 资金费率升高，后排乱涨 | 减仓，不追后排 |
| 分歧 | 龙头冲高回落，补涨分化 | 保留核心，卖弱 |
| 修复 | 龙头反包，板块回流 | 可低吸核心 |
| 退潮 | 龙头破位，后排补跌 | 空仓或做空弱势 |

工程化周期判断：

```yaml
market_state_inputs:
  btc_trend: 4h trend score
  eth_trend: 4h trend score
  market_breadth: percent of symbols above 20MA
  sector_leaders_above_vwap: count
  liquidation_zscore: abnormal liquidation level
  funding_median: market funding heat
  top_symbols_drawdown: leader drawdown
```

## 7. 入场系统

### 7.1 入场模式 A：突破做多

适用场景：

1. 大盘强多或企稳转强。
2. 赛道排名靠前。
3. 标的是龙头或中军。
4. 价格突破 N 周期高点或箱体上沿。

入场条件：

```yaml
long_breakout:
  price: close > range_high_20
  volume: volume_ratio >= 1.5
  oi: oi_change_pct >= 3
  taker_buy_ratio: ">= 0.55"
  funding_rate: "< funding_extreme_threshold"
  btc_filter: btc_trend_score > 0
```

确认条件：

1. 突破 K 线不能长上影。
2. 突破后 1 到 3 根小周期 K 线不跌回箱体。
3. 回踩突破位时缩量。
4. 再次上攻时主动买入占比提升。

失效条件：

```yaml
long_breakout_invalid:
  close_back_inside_range: true
  volume_on_pullback: volume_ratio > 1.2
  oi_rising_while_price_falling: true
```

### 7.2 入场模式 B：回踩确认做多

适用场景：

突破后不追第一波，等待回踩。

入场条件：

```yaml
long_pullback:
  prior_breakout: true
  pullback_to: breakout_level_or_vwap
  pullback_volume: volume_ratio <= 0.8
  price_structure: higher_low
  trigger: close_above_short_ma_or_previous_small_high
```

止损位置：

1. 平台下沿。
2. 突破位下方。
3. 回踩低点下方。
4. `1.2 * ATR` 下方，取更合理者。

### 7.3 入场模式 C：清算针反转低吸

适用场景：

市场经历快速杀跌，多头清算释放后出现承接。

入场条件：

```yaml
long_liquidation_reversal:
  price_drop_fast: true
  liquidation_long_zscore: ">= 2"
  volume_ratio: ">= 2"
  new_low_failed: true
  taker_buy_ratio_recover: ">= 0.52"
  oi_stabilize_or_rebuild: true
```

执行要求：

1. 不接第一根下杀针。
2. 等二次不破低点。
3. 等小周期重新站回 VWAP 或关键均线。
4. 初始仓位小于正常仓位的 30% 到 50%。

### 7.4 入场模式 D：做空破位

适用场景：

大盘弱空，赛道退潮，个币跌破关键支撑。

入场条件：

```yaml
short_breakdown:
  price: close < range_low_20
  volume: volume_ratio >= 1.5
  oi: oi_change_pct >= 3
  taker_sell_ratio: ">= 0.55"
  funding_rate: not_extreme_negative
  btc_filter: btc_trend_score < 0
```

谨慎条件：

1. 如果跌破时 OI 大幅下降，可能是多头爆仓末端，不适合追空。
2. 如果资金费率已经极端负，追空容易被反抽。
3. 低位放量大跌后要防止 V 型反转。

## 8. 持仓系统

持仓不是“买了就等”，而是持续检查交易逻辑是否还成立。

多单继续持仓条件：

```yaml
hold_long:
  price_above_protection_line: true
  trend_structure: higher_high_higher_low
  pullback_volume_shrink: true
  sector_rank_not_deteriorating: true
  funding_not_extreme: true
  leader_not_breaking_down: true
```

空单继续持仓条件：

```yaml
hold_short:
  price_below_protection_line: true
  trend_structure: lower_high_lower_low
  rebound_volume_weak: true
  sector_rank_weak: true
  funding_not_extreme_negative: true
```

保护线设置：

| 交易类型 | 保护线 |
| --- | --- |
| 突破多 | 突破位下方或回踩低点 |
| 回踩多 | 回踩低点下方 |
| 清算反转多 | 二次确认低点下方 |
| 破位空 | 跌破位上方 |
| 反弹空 | 反弹高点上方 |

动态保护线：

```text
protection_line_long =
  max(previous_protection_line, recent_swing_low, vwap_or_ma_support, entry_price_after_profit)
```

盈利后处理：

1. 盈利达到 `1R`，保护线移动到成本附近。
2. 盈利达到 `2R`，减仓 25% 到 50%，剩余仓位用趋势保护线持有。
3. 出现高位滞涨或资金费率极端，主动减仓。

## 9. 加仓系统

加仓只能发生在原逻辑被验证之后，不允许亏损摊平。

允许加仓条件：

```yaml
allow_add_long:
  position_pnl_r: ">= 1"
  protection_line_at_or_above_entry: true
  price_makes_new_high: true
  volume_not_diverging: true
  oi_growth_quality: healthy
  funding_rate_not_extreme: true
```

推荐三段式仓位：

| 阶段 | 条件 | 仓位 |
| --- | --- | --- |
| 第一笔 | 突破或低吸确认 | 30% 到 50% |
| 第二笔 | 回踩不破，再次放量上攻 | 20% 到 30% |
| 第三笔 | 趋势继续，保护线已上移 | 10% 到 20% |

禁止加仓条件：

1. 当前仓位亏损。
2. 高位放量滞涨。
3. 价格新高但 OI 和主动买盘背离。
4. 资金费率极端偏多。
5. 龙头币冲高回落，补涨币乱涨。
6. BTC/ETH 已经转弱。

## 10. 减仓系统

减仓用于保护利润，而不是等到破位才反应。

主动减仓条件：

```yaml
reduce_long:
  high_position: true
  volume_up_price_stall: true
  upper_wick_large: true
  funding_rate_extreme_positive: true
  oi_surge_price_stall: true
  sector_breadth_deteriorating: true
```

减仓比例建议：

| 情况 | 动作 |
| --- | --- |
| 第一次高位放量滞涨 | 减仓 25% |
| 巨量上影或冲高回落 | 减仓 30% 到 50% |
| 资金费率极端且价格不涨 | 减仓 30% 到 50% |
| 龙头转弱，补涨乱涨 | 减仓后排，保留少量核心 |
| 跌破保护线 | 不减仓，直接离场 |

空单减仓条件：

1. 低位放量大跌后 OI 大幅下降。
2. 多头清算量极端放大。
3. 价格不再创新低。
4. 主动买盘恢复。
5. 资金费率极端负。

## 11. 离场系统

离场分为止损离场、止盈离场、逻辑失效离场、周期退潮离场。

止损离场：

```yaml
stop_loss_exit:
  close_below_protection_line: true
  or_intrabar_break_with_high_volume: true
```

止盈离场：

```yaml
take_profit_exit:
  target_r_multiple: ">= 2"
  and_reversal_signal: true
```

逻辑失效离场：

```yaml
logic_invalid_exit:
  breakout_failed: true
  sector_leader_breakdown: true
  btc_eth_breakdown: true
  funding_extreme_plus_price_stall: true
```

周期退潮离场：

1. 龙头币破位。
2. 中军不再承接。
3. 补涨币冲高回落。
4. 市场广度快速下降。
5. BTC/ETH 跌破关键位。

## 12. 仓位与风险控制

### 12.1 单笔风险

建议每笔交易最大亏损控制在账户权益的 `0.3%` 到 `1%`。

仓位计算：

```text
position_size = account_equity * risk_pct / stop_distance_pct
```

例子：

```text
账户 10,000 USDT
单笔风险 0.5% = 50 USDT
止损距离 2%
名义仓位 = 50 / 0.02 = 2,500 USDT
```

### 12.2 杠杆建议

| 交易类型 | 建议杠杆 |
| --- | --- |
| 趋势突破 | 2x 到 4x |
| 回踩确认 | 2x 到 5x |
| 清算针低吸 | 1x 到 3x |
| 补涨套利 | 1x 到 3x |
| 逆势交易 | 尽量不做，最多 1x 到 2x |

杠杆不是用来放大贪心的，而是用于提高资金效率。真正控制风险的是止损距离和仓位。

### 12.3 每日风险限制

```yaml
risk_limits:
  max_daily_loss: 2%
  max_weekly_loss: 5%
  max_open_positions: 3
  max_correlated_positions: 2
  stop_trading_after_consecutive_losses: 3
```

## 13. 信号打分模型

可以将系统做成 100 分评分。

### 13.1 多头评分

```text
long_score =
  20 * market_trend
  + 15 * sector_strength
  + 15 * symbol_leadership
  + 15 * breakout_or_reversal_quality
  + 10 * volume_confirmation
  + 10 * oi_quality
  + 10 * taker_buy_strength
  + 5 * funding_safety
```

交易阈值：

| 分数 | 动作 |
| --- | --- |
| `< 60` | 不交易 |
| `60 - 70` | 观察或小仓试错 |
| `70 - 80` | 正常开仓 |
| `80+` | 高质量机会，但仍按风控下单 |

### 13.2 拥挤风险评分

```text
crowding_score =
  35 * funding_percentile
  + 25 * oi_growth_extreme
  + 20 * long_short_ratio_extreme
  + 20 * price_stall_at_high
```

处理规则：

| 拥挤分 | 动作 |
| --- | --- |
| `< 50` | 正常 |
| `50 - 70` | 降低追高意愿 |
| `70 - 85` | 不加仓，考虑减仓 |
| `85+` | 高风险，主动减仓或等待反向信号 |

## 14. 状态机设计

交易系统可以设计为状态机：

```text
WATCHLIST
  -> SETUP
  -> TRIGGERED
  -> ENTERED
  -> HOLDING
  -> ADDING
  -> REDUCING
  -> EXITED
  -> REVIEW
```

状态说明：

| 状态 | 含义 | 动作 |
| --- | --- | --- |
| `WATCHLIST` | 交易对进入观察池 | 只监控 |
| `SETUP` | 具备方向和结构 | 等触发 |
| `TRIGGERED` | 触发入场条件 | 准备下单 |
| `ENTERED` | 已开仓 | 设置保护线 |
| `HOLDING` | 持仓中 | 检查持仓条件 |
| `ADDING` | 满足加仓 | 加仓并更新保护线 |
| `REDUCING` | 出现减仓信号 | 分批止盈 |
| `EXITED` | 离场 | 停止交易该信号 |
| `REVIEW` | 复盘 | 记录结果 |

## 15. 告警与执行规则

### 15.1 观察池告警

```yaml
watchlist_alert:
  sector_score: ">= 70"
  symbol_leader_score: ">= 70"
  quote_volume_rank: top_20
```

### 15.2 入场告警

```yaml
entry_alert:
  long_score: ">= 70"
  trigger_pattern: breakout_or_pullback_or_reversal
  risk_reward: ">= 2"
  crowding_score: "< 70"
```

### 15.3 风险告警

```yaml
risk_alert:
  protection_line_distance: near
  crowding_score: ">= 70"
  leader_breakdown: true
  btc_eth_breakdown: true
```

## 16. 回测与验证方案

不要直接实盘使用，先做三层验证：

1. 历史回测：至少覆盖牛市、熊市、震荡市。
2. 样本外测试：用未参与调参的数据验证。
3. 模拟盘测试：至少连续 30 到 60 天。

回测指标：

| 指标 | 目标 |
| --- | --- |
| 胜率 | 不单独追求，高盈亏比可接受较低胜率 |
| 盈亏比 | 最好大于 1.5 |
| 最大回撤 | 必须可承受 |
| 连续亏损次数 | 用于设置暂停交易规则 |
| 持仓时间 | 判断策略类型 |
| 手续费和滑点 | 必须计入 |
| 资金费率成本 | 合约必须计入 |

## 17. 每日执行清单

盘前或交易前：

1. BTC/ETH 当前状态是什么？
2. 今天最强赛道是什么？
3. 龙头币、中军币、补涨币分别是谁？
4. 当前是启动、发酵、高潮、分歧、修复还是退潮？
5. 我要做突破、回踩、低吸、套利，还是做空破位？
6. 入场触发价在哪里？
7. 保护线在哪里？
8. 止损距离是多少？
9. 仓位是多少？
10. 什么条件加仓？
11. 什么条件减仓？
12. 什么条件无条件离场？

如果这 12 个问题答不清楚，不开仓。

## 18. 策略模板

```yaml
strategy_name: crypto_contract_volume_price_emotion_system
timeframes:
  trend: [4h, 1d]
  setup: [1h, 4h]
  execution: [5m, 15m]

universe_filter:
  min_quote_volume_24h: 50000000
  max_spread_pct: 0.05
  min_history_days: 60

market_filter:
  btc_trend_score_min_for_long: 0
  btc_trend_score_max_for_short: 0

entry:
  long_breakout_score_min: 70
  long_pullback_score_min: 70
  reversal_score_min: 75
  crowding_score_max: 70

risk:
  risk_per_trade_pct: 0.5
  max_daily_loss_pct: 2
  max_weekly_loss_pct: 5
  max_open_positions: 3
  no_add_to_losing_position: true

position_management:
  move_stop_to_breakeven_at_r: 1
  partial_take_profit_at_r: 2
  partial_take_profit_pct: 30

exit:
  exit_on_protection_line_break: true
  exit_on_leader_breakdown: true
  exit_on_btc_eth_breakdown: true
```

## 19. 最终结论

这套系统的核心不是预测行情，而是把交易拆成可执行流程：

1. 用 BTC/ETH 和市场广度判断大环境。
2. 用赛道强度选择方向。
3. 用成交额、涨幅、OI、主动买盘选择龙头、中军和补涨。
4. 用量价结构等待突破、回踩、止跌、反转等入场信号。
5. 用保护线决定持仓和离场。
6. 用拥挤度、滞涨、退潮信号做减仓。
7. 用固定风险和状态机防止情绪化交易。

一句话总结：

> 加密合约交易中，量价关系负责判断资金效率，OI 和资金费率负责判断合约拥挤度，BTC/ETH 和赛道强度负责判断环境，保护线和仓位规则负责决定你能不能活下来。

