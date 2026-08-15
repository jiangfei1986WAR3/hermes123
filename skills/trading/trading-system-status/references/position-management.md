# 移保本机制与 plan 过期断链（2026-08-08 XRP 实例）

## 机制

开仓时 executor 挂三张 algo 条件单（全部 reduceOnly）：
- TP1 = 50% 仓位（如 48.1）、TP2 = 50% 仓位（48.1）、SL = **100% 全量**（96.2）

TP1 成交后，应由 `manage` 路径执行移保本：
1. `get_open_algo_orders(symbol)` 查 `/fapi/v1/openAlgoOrders`
2. 判定条件：TP1 单消失 + SL 仍在原位（triggerPrice ≈ plan.stop_loss）→ TP1 已被交易所执行
3. 动作：撤旧 SL → 挂新 SL（triggerPrice=入场价、qty=剩余仓位）→ 撤未触发 TP → 按剩余仓位重挂
4. 成功日志：`止损移到保本 {new_sl}（剩余 {qty}）✅`、`重挂 TP2 price=... qty=... ✅`

该币是否在管理名单 = PLANS_DIR 下是否存在 `{SYMBOL}-plan.json`（manage_all_positions 按文件遍历）。

## XRP 时间线（断链实例）

| 时间 | 事件 |
|------|------|
| 08-07 02:47 | 开空 96.2 @ 1.0368；挂 TP1 48.1@1.0125 + TP2 48.1@0.9983 + SL 96.2@1.0523 |
| 08-07 22:00 | plan 过期（expires_at 到）→ executor 删 plan.json（日志 `计划过期: XRPUSDT`） |
| 08-08 01:00 | TP1 在交易所自动成交（BUY 48.1 @ 1.0125，+1.17U）——条件单执行不依赖 plan 文件 |
| 01:00 后 | manage 循环每分钟跑但找不到 XRP plan → 跳过 → **无人更新挂单** |
| 01:00:50 | 唯一痕迹：detect_position_changes 发 `🟡 部分止盈` 通知（只通知不调单） |

事后币安后台验证（08-08 08:56）：
- 条件单仅剩 2 张：TP 48.1@0.9983、SL **96.2@1.0523**（全量、原止损位）
- 两张单 `updateTime = createTime` = 08-07 02:47 开仓时刻 → **从未被修改过**
- 原 TP1 已从 openAlgoOrders 消失；普通挂单 `/fapi/v1/openOrders` 为空

## 识别要点

- 持仓减半但 SL 仍 qty>持仓 且挂在原止损位 → 移保本断链特征
- reduceOnly 兜底：SL 超量触发时交易所按可平量成交（=全平剩余），**不会反向开仓**；实际代价是已实现利润可能被反弹止损回吐（XRP：SL 触发约 -0.75U，吃掉 TP1 已实现 1.17U 的一半），不是仓位失控
- 对照：plan 仍在的币（NEAR 例，expires 2026-08-08 22:30）TP1 触发后下一分钟即移保本，机制本身工作正常
- 判断 plan 是否开仓时：有 `actual_entry` = 开仓完成；无 plan 文件 ≠ 无持仓（过期/止损都会删 plan）

## 其他

- 查持仓直接 `import get_positions`（executor 封装）；直接调 `/fapi/v1/positionRisk` 会 404
- 修复方向（2026-08-08 已向用户提出，暂缓未实施）：PLAN_EXPIRED 分支检测有持仓 → 保留 plan 文件或管理标记，平仓后再删；或 manage 改为不依赖 plan 文件（直接查持仓 + algo 挂单状态）
