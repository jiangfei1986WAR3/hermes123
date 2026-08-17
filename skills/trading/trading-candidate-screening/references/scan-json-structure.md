# 扫描结果 JSON 结构（binance-market-scanner 输出）

文件：`/root/Documents/trae_projects/zhuandaqian/market-scans/*_binance-usdt-perp-scan.json`
顶层：`{"errors": [], "results": [...], "summaryRows": [...], "topLong": [...], "topShort": [...]}`

两种行结构混用会 KeyError（2026-08-16 会话烧了 3 次解析才发现）：

## topLong / topShort（嵌套结构，用于排名榜）

- 分数：`r['long']['score']` / `r['short']['score']`（int）
- 理由/警告：`r['long']['reasons']` / `r['long']['warnings']`（list[str]）
- **没有**扁平的 `longScore` 键，**没有**按周期的时间框架字典
- 顶层还有 `symbol/last/mark/changePct/quoteVolume/funding/oi/fetchedAt/state`

## summaryRows（扁平结构，用于逐币细节和大盘 filter 检查）

- `longScore` / `shortScore` / `state` / `last` / `changePct` / `funding` / `quoteVolume`
- 15m：`m15Close` `m15MA7` `m15MA25` `m15VolRatio` `m15BuyRatio`
- 1h：`h1Close` `h1MA7` `h1MA25` `h1VolRatio` `h1RangePos` `h1High20` `h1Low20`
- 4h：`h4Close` `h4MA7` `h4MA25`
- 1d：`dClose` `dMA7` `dMA25`
- **没有**嵌套 `long`/`short` 字典，**没有** `'15m'` 风格的时间框架键

## 用法

- 排名榜（分数+理由）→ 读 topLong / topShort
- 候选逐周期细节 + BTC/ETH 大盘 filter（日线空头排列？15m 放量方向？）→ 读 summaryRows

BTC/ETH 大盘 filter 速查（summaryRows）：`dClose < dMA7 < dMA25` = 日线空头排列；`m15VolRatio > 1.5` 且 `m15BuyRatio < 0.48` = 15m 放量下压。
