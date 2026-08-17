# watch 机制详解（Position Change Detection 内部实现）

从主 SKILL.md 拆出（2026-08-17 瘦身）。主文档保留通知覆盖表 + 清理四步 + 延迟数字；本文件是机制细节。

## 快照对比循环

`binance_executor.py watch` compares current positions against a saved snapshot (`~/.hermes/trading-state.json`)，每 ≈2 分钟跑一次（trading-cron.sh step 3；配置 every 1m 实际 ≈2m）：

```
① Query current positions from Binance API
② Read previous snapshot from trading-state.json
③ Compare:
   - Position disappeared → determine cause (SL/TP/manual) → notify
   - Position quantity reduced >20% → partial TP → notify
   - No change → silent
④ Save current positions as new snapshot
```

**Cause determination logic:**
- Current price ≤ stop_loss × 1.002 → "🔴 已止损"
- Current price ≥ TP1 × 0.998 → "🟢 已止盈"
- Otherwise → "⚪ 仓位已平（可能手动）"

## TP1 后 TP2 自动重挂（07-25 起）

TP1 reduce + 保本移位成功后，manage_position 自动：
1. Finds all remaining TAKE_PROFIT_MARKET Algo orders for the symbol
2. Cancels them all (best-effort, try/except per order)
3. Re-places TP2+ orders with quantities proportional to the **remaining** position (not original)
4. Last TP absorbs rounding error: `remaining_qty - allocated` ensures total = exact remaining position
5. Logs each re-placed TP; failures only log warnings, never block the already-placed breakeven SL

**安全设计**: TP 重挂只在保本 SL 确认挂上后执行；保本失败则 TP 重挂不跑；全部 best-effort。最坏 = 无 TP 单（保本 SL 仍保护），绝不崩溃或孤儿状态。

**背景问题**（为何需要重挂，NEAR 07-25 实例）：TP1 减半后 TP2 仍挂原数量（SL28+TP27=55 但只剩 28）。都是 reduceOnly 不会反手，但：TP2 先触发 → 剩 1 单位贱平；SL 先触发 → TP2 变孤儿单污染下一笔同币交易。watch 清理只在仓位**消失**时触发，部分减仓不触发 → 需要 manage 主动重挂。

## Key design decisions

- Does NOT depend on Binance callbacks (none exist)
- Does NOT depend on INVALIDATION events (they can pile up unprocessed)
- Only depends on: "position was there, now it's not" — universally reliable
- Max notification delay: **~2-3 minutes**（2m 调度 + ~1m 执行）。TP1 成交→保本损挂上实际 ~2-3 分钟（UNI 08-03 实测 2'53"：TP1 23:35:44 → 保本 23:38:37，错过 tick 8 秒）
- 条件单是单动作（触发只执行一个市价单，不会自动改 SL）；保本价=入场价，TP1 前无法预挂（会立即触发），逻辑上必须等 TP1 成交后
- **窗口期三层保护**：TP2 单（利润继续）+ 保本损（~2-3 分钟补挂）+ 原始止损（全程生效，reduceOnly 不反手）。最坏 = 窗口内价格反向穿过原始止损（需极端行情，如 UNI 从 TP1 涨 4.7%），剩余仓按原始止损离场——有界、可量化、概率极低。历史 8/8 保本移动无事故
- **30s 轮询方案评估（2026-08-03，用户决定不改）**：脚本三步实测总耗时 0.556s（30s 周期不会重叠），API ≈12 次/分钟（远低于限流），通知频率不变（静默设计）。但收益趋近 0（窗口已有原始止损兜底），按"能跑就不改"保持现状；仓位变大或保本延迟真造成过损失再改
- First run after deployment: creates empty snapshot, no false notifications
