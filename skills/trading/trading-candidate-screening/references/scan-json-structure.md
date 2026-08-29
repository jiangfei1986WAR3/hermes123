# 扫描结果 JSON 结构（binance-market-scanner 输出）

文件：`/root/Documents/trae_projects/zhuandaqian/market-scans/*_binance-usdt-perp-scan.json`
顶层：`{"generatedAt", "filter", "counts", "errors": [], "results": [...], "summaryRows": [...], "topLong": [...], "topShort": [...], "stability"}`

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

## stability（跨轮名单稳定性）

`stability` = {jaccard: 0~1, prevAt: 上一轮扫描时间, added: [...], dropped: [...], warning: 名单跳变异常}。jaccard < 0.5 时 scanner 报 warning，只表示相邻两轮候选名单变化较大；原因可能是高潮轮动、方向切换、闪崩修复、成交额门槛变化等。它是市场切换提示，不是高潮或空仓的独立判据，须结合Top候选深度分析、量价、R与大盘结构解释。

## 机械化读取（两次踩坑后固化，2026-08-29）

嵌套/扁平两结构对扁平键 .get() 的静默 None 陷阱已实测两次（08-17 与 08-29：`r.get('longScore',0)` 对嵌套行全返回 0，Top20 排名输出全是 0 分，白跑一轮）。**读扫描 JSON 一律先跑防御脚本，不再手写解析**：

```bash
python3 ~/.hermes/skills/trading/trading-candidate-screening/scripts/read_scan_json.py            # 最新文件 Top15
python3 ~/.hermes/skills/trading/trading-candidate-screening/scripts/read_scan_json.py latest 20  # Top20
```

脚本自适应两种行结构、输出分数排名榜 + stability + BTC/ETH 大盘速查。需要自定义字段时以脚本里 `_flat()` 的取值路径为基准改写，勿再按扁平键直接 .get()。
