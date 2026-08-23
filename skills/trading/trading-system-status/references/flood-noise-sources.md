# 限流噪声源诊断（iLink rate limited 两种刷屏，2026-08-19 实测）

监控 Cron 的 `last_delivery_error` 报 iLink 限流时,先看该币 plan 状态再归因——两种刷屏都是**正常机制**:

## 1. EXPIRED 每分钟刷（过期保留仓）
- 触发条件:plan 过期 + 有持仓 → plan 保留 → signal_monitor 每分钟写 PLAN_EXPIRED 事件 → 包装脚本 grep EXPIRED → 每分钟推微信
- 处置:停用该币价格监控 Cron(保留 plan,持仓托管不受影响)或用户选择保持(08-19 SOL/AAVE 用户选保持,勿反复推销)
- 案例:SOL 08-19(21:00 过期)、AAVE 08-19(12:45 过期)

## 2. TRIGGER 每 10 分钟刷（持仓中冷却期重复触发）
- 触发条件:未过期 + 已开仓的 plan,价格持续站触发价上方 → 每冷却期(600s)signal_monitor 重写 TRIGGER 事件 → 包装脚本 grep TRIGGER → 推微信(executor 侧被"已有持仓"安全门拦截,不重复开仓)
- 案例:LINK/PUMP 08-19 23:01 事件目录同时出现两个 TRIGGER 事件;23:02 检查时两币监控 Cron 均报限流
- 处置:无需处置——平仓删 plan 后噪声源自动消失(08-19 23:27-23:29 LINK/XRP TP2 平仓、AAVE TP2 平仓后,00:00 检查全部 Cron last_delivery_error=null,限流全部清零)

## 诊断一句话
EXPIRED 每分钟刷=过期保留仓;TRIGGER 每10分钟刷=持仓中冷却期重复触发。限流只丢微信通知、不碰交易执行(SL/TP 交易所条件单+托管链独立)。

## 附带验证(08-19 实盘)
- 4 次 TP1→移保本→TP2 全流程走通(SOL/AAVE/XRP/LINK),其中 AAVE plan 过期后移保本照常执行(过期保留修复二次验证)
- 残留批量清理:3 币 × 3 样(Cron+脚本+state)一次清完,ls 验证,用户一句"清理"即执行
