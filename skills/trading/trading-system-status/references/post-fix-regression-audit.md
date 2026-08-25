# 修复后回归审计：Cron 调度与交易系统（2026-08-25）

当一次修改同时涉及 Cron、技能模板和文档时，不能只看“修改成功”；必须把线上执行层与知识/模板层分开验证。

## 审计顺序

1. **线上配置**：读取 `~/.hermes/cron/jobs.json` 与 `cronjob(action='list')`。长期监控/事件处理应为 `kind=cron, expr='* * * * *'`，并保留 `script`、`no_agent=true`、`deliver=all`、`enabled/state`、永久 repeat。
2. **实际节奏**：运行 `hermes cron runs <job_id>`，计算相邻时间戳。不要用配置字符串代替实测；修复后应约 60s，旧 interval 可能约 120s。
3. **字段 diff**：与修改前完整快照比对。正常变化：`schedule`、`schedule_display`、`next_run_at`；`last_run_at`/`repeat.completed` 变化先核对是否为期间正常点火。
4. **交易链健康**：检查 plan/state/events、持仓、交易所 `get_open_algo_orders`、`manage`、Gateway、executor 日志。不要手动执行 `process-events` 作为测试，它可能真实下单。
5. **回归检查**：确认没有新 job、重复事件、重复开仓、保护单丢失、脚本路径改变、`no_agent` 变更、微信交付错误或 failure streak。
6. **错误过滤**：精确筛选带时间戳的 `[ERROR]`/`[WARNING]`/rate-limit 行。宽泛 grep 的 `429` 可能只是价格文本（例如 `0.3429`），必须追溯原始行。

## 模板/文档层检查

- 新建长期 Cron 的操作模板必须使用 `* * * * *`，禁止把 `every 1m` 当现行模板。
- 历史记录可以保留旧 `every 1m`，但要标注为修复前状态；回滚命令中的 `every 1m` 要明确“仅用于紧急回滚，禁止新建”。
- 主技能中的统计基准必须来自真实账本审计，不要保留未经验证的“常规滑点”印象值。
- 同主题 reference 需要避免重复；若多个文件重叠，明确一个主文档和其余用途，防止未来版本分叉。

## 独立待办不要混改

`market_filter` 使用实时 `last` 而非已收盘 close 的抖动，是原有策略设计问题；下一笔自然成交才能验证滑点改善。两者都不要被误报为 Cron 修复回归，也不要与调度修复捆绑修改。

## 结论口径

“调度节奏修复成功”只证明 Cron 从约 120s 恢复约 60s；不能提前宣称每笔实际滑点一定减半。最终效果需下一笔自然开仓后，用收盘时间、事件写入时间、事件处理时间、成交时间和 userTrades 成交价复盘。