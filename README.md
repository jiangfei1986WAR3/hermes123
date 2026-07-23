# Hermes 交易技能备份

## 包含内容

### 9 个交易技能（skills/）

| 技能 | 功能 |
|---|---|
| trading-command-center | 总调度中心，串联所有技能 |
| binance-market-scanner | 扫描币安 200+ 币对，海选候选 |
| trading-analysis | 多周期深度分析（趋势/量价/形态） |
| trade-execution-planner | 把分析转成执行计划（触发/止损/TP） |
| risk-manager | 仓位计算、杠杆对比、强平预警 |
| auto-signal-monitor | 价格监控，触发条件检测 |
| binance-executor | 自动下单执行（5重安全门） |
| trade-review | 交易复盘，总结教训 |
| trading-ops-reliability | 运维可靠性（通知/清理/故障处理） |

### 配套脚本（scripts/）

| 脚本 | 功能 |
|---|---|
| binance_executor.py | 执行器（5重安全门自动下单） |
| trading-cron.sh | 事件处理+持仓管理 Cron |
| *-monitor-check.sh | 各币种监控包装脚本（示例） |

## ⚠️ 不包含（需手动配置）

- `trading-config.json`（含 API Key，不上传）
- `trading-plans/`（临时计划文件）
- `trading-events/`（临时事件文件）
- Cron 任务（需重新创建）

## 恢复方法

```bash
# 1. 新服务器装好 Hermes 后
git clone https://github.com/jiangfei1986WAR3/hermes123.git
cd hermes123

# 2. 运行恢复脚本
bash restore.sh

# 3. 手动配置 API Key
# 编辑 ~/.hermes/trading-config.json 填入币安 API Key

# 4. 让 Hermes 重建 Cron 监控
# 在对话中说"帮我重建交易监控 Cron"
```

## 完整交易链路

```
扫描选币 → 深度分析 → 出计划 → 算仓位 → 监控触发 → 自动下单 → 持仓管理 → 复盘
```
