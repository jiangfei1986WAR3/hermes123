# 过期刷屏处置：用户可能选择"保持不停用"（2026-08-19）

## 场景
SOL 计划过期+有持仓 → plan 保留 → signal_monitor 每分钟写 PLAN_EXPIRED → 监控包装脚本 grep EXPIRED 推微信 + trading-cron.sh 输出非空 → iLink 限流（两个 Cron 的 last_delivery_error 都报 rate limited）。

## 技能内标准处置是"停用过期币监控 Cron"
但 08-19 用户明确选"就这样 保持，清理残留就行"——**停用是推荐处置不是自动执行**：
1. 呈现选项时把后果说清：限流只影响微信通知及时性，不碰交易执行（SL/TP 交易所条件单+托管链独立）
2. 用户选择保持 → 尊重，不重复推销停用；后续每次状态检查如实报告限流仍在即可
3. 用户说"清理残留" → 按清单执行：残留=监控 Cron + monitor-check.sh 脚本 + state 文件（plan 已随平仓自动删、事件无）

## 残留清理实例（HYPE 08-19，三样）
- Cron：HYPEUSDT 价格监控（job_id 62eff95e78d6）→ cronjob remove
- 脚本：~/.hermes/scripts/hypeusdt-monitor-check.sh → rm
- state：~/.hermes/trading-plans/HYPEUSDT-plan.state.json → rm
- 验证：ls 全无 + cronjob list 确认消失
- HYPE 止损路径交叉验证：08-19 00:25:40 两笔 SELL（0.95+0.73@58.346/58.343，pnl -1.0327/-0.7957）平掉 08-17 15:32 BUY 1.68@59.433；58.343 = 原止损 58.2 平移 +0.133 后的保本 SL，日志"⚪已平仓"→ 止损自动删 plan ✓

## 顺带确认（本轮状态检查）
- SOL TP1 成交后移保本在 plan 过期后仍生效（plan 文件保留 → manage 照管）：03:28 TP1 SELL 0.66@77.35 +1.17U，03:29 "止损移到保本 75.57（剩余 0.66）✅"，挂单 SL 75.57/TP 77.9@0.66 与日志一致
- AAVE 08-19 07:37 开仓 1.1@87.54，SL 86.59 + TP1 0.5@90.39 + TP2 0.5@92.88 在位；TP 数量 0.5+0.5<1.1 尾差 0.1 只受 reduceOnly SL 保护（执行层取整，非故障）
