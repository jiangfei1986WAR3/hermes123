# 入场滑点归因 + Hermes Cron 节奏真相（2026-08-25 实测，62 笔账本）

用户问"滑点是不是有点大 / 能不能优化"时用本文。先量化再归因，禁凭印象。

## 一、滑点真值（作废旧口径）

旧文档写"常规 0.3-0.7%"，是印象值，偏高。62 笔实盘账本真值：

```
不利滑点(按多空方向校正符号,正=吃亏): 均值 +0.275%  中位 +0.165%
>0.7%: 10/62    >1.0%: 4/62    实际占便宜(负): 9/62    最差 +1.78%
折算: 每笔吃掉 均值 0.177R / 中位 0.086R;41 笔可算 R 的累计 7.27R ≈ 18.80U
```

⚠️ **必须按方向校正符号**：做多成交更高=不利，做空成交更低=不利。只看 `actual_entry - trigger` 的正负号会把做空的有利滑点误判成不利。53/62 落在不利方向（随机应为 50/50）→ 证明滑点是**结构性偏向**，不是运气。

## 二、根因三段拆分（XMR 08-25 逐秒还原）

触发 436 → 成交 441.28（+1.21%，排第 2 差）。用 1m K 线拆开：

| 来源 | 金额 | 占比 |
|---|---|---|
| 15m 收盘价本身超出触发价（收 437.05 vs 触发 436） | +1.05 | 20% |
| **收盘确认→市价成交之间的延迟漂移**（02:29:59 收盘 → 02:32:28 成交，**149 秒**） | +4.23 | **80%** |
| 盘口吃单深度（441.28 落在 02:32 那根 1m 的 [440.48,442.16] 内） | ≈0 | ≈0% |

那 149 秒正是放量拉升段（1m 量 49→497→427→288）。**结论：主因是链路延迟，不是流动性、不是市价单、不是行情针对。**

**滑点的真实代价有两层**（第二层易被漏掉）：
1. 目标位被推高（TP1 466.40→471.68，只涨到 469 就拿不到）
2. **止损位从"结构外"挪进"结构内"** ← 更重要。原 SL 424.50 在 15m 支撑下方；平移后 429.78 站在支撑上方 5.28 处。正常回踩到 424-425 再起涨会被扫掉，而原计划不会。等距平移保住了 R 倍数，但没保住结构位。回答用户时别只说"R 完好"。

## 三、Hermes Cron `every 1m` 实际跑 120s（根因已定位）

**现象**：两个 job 配置 `every 1m`，`hermes cron runs <id>` 显示 20 次运行间隔**全是 120s**。

**根因（0.43 秒的错位）**：
- `cron/jobs.py:99` `TICKER_INTERVAL_SECONDS = 60`；实测心跳周期 **60.07s**
- `compute_next_run` 对 interval：`next_run = last_run_at + 60s`
- 而 `last_run_at` 记的是**执行完成**时刻，比 tick 起点晚 ~0.55s（点火记录 08:00:13.290 vs jobs.json `last_run=08:00:13.840`）
- → next_run 08:01:13.840，下一个 tick 落在 08:01:13.4x → **差 0.43s 判未到期 → 空转一轮**
- 每轮稳定差这 0.43s，所以是 **100% 必然空转，非偶发**

**对交易链路的影响**：真实链路 = 监控跳 0~120s + 事件处理跳 0~120s = **0~240s（期望 ~120s）**，不是按配置算的 0~120s。XMR 的 149s 正落此区间。

**修法**：schedule 由 `every 1m` 改 5 字段 cron **`* * * * *`**。croniter 把 next_run 吸附到整分钟边界（08:21:00），tick 固定落在 :13.4 → 永远已过期 13 秒 → 每轮必点火。真实代码仿真 8 轮：`every 1m` 点火 4/8（间隔 120s）vs `* * * * *` 点火 8/8（间隔 60s）。

**秒级粒度不可达（别再提"改 30s"）**：
- `parse_duration` 正则无秒单位；`multipliers={'m':1,'h':60,'d':1440}`。`every 30s`/`every 0.5m` 直接 ValueError
- 6 字段 cron（`0 * * * * */30`）能过解析、croniter 也真算出 30 秒后的 next_run，但 **ticker 60s 是物理下限**（全代码库仅 1 处定义 + 1 处引用，无配置项可覆盖），每 tick 最多点火一次
- 改 `TICKER_INTERVAL_SECONDS` 常量 = 改 Hermes 源码，git 安装升级会被覆盖 ❌

**改动安全性（已验证）**：
- 工具路径 `cronjob(action='update', job_id=…, schedule='* * * * *')`：`tools/cronjob_tools.py:1708` 只在 `schedule is not None` 时入 updates，其余字段同样有 `is not None` 守卫
- `update_job` 用 `{**job, **updates}` **字典合并** → `script`/`no_agent`/`deliver`/`repeat`/`last_run_at` 原样保留
- `update_job:2323` 重算 next_run **不传 last_run_at**（锚点=now）→ 改完 ≤60s 首次点火
- 全代码库把 `cron` 与 `interval` 当同类循环任务（`{"cron","interval"}` 成对出现 8 处）；两处 interval 专属分支均良性
- 副作用：signal_monitor API 从 ~4/min → ~9/min（币安权重上限 2400/min，占用 <0.5%）；微信推送与日志量**不变**（事件写入受 `cooldown_seconds=600` 控制，与 tick 频率无关）
- 回滚 = schedule 改回 `every 1m`，一条命令

## 四、查证命令与踩坑

**查真实节奏**（配置值不可信）：
```bash
hermes cron runs <job_id>          # 看相邻时间戳差,这是发现空转的关键手段
# 测 ticker 真实周期: 采样 ~/.hermes/cron/ticker_heartbeat 的 mtime 变化
```

**滑点全量审计**：
```bash
grep '滑点校准' ~/.hermes/trading-executor.log        # 拉全量样本(计划价→实际/平移)
# 方向与 R 换算须读 ~/.hermes/trading-history/*.json 的 plan.direction/stop_loss/risk.quantity
```

三个踩坑（都真踩过）：
1. **`/proc/<PID>/exe` 会误报模块缺失**：它指向底层 uv CPython（`/usr/local/share/uv/python/…`），绕过 venv 的 site-packages。判断 gateway 进程能 import 什么，要看 `cmdline` 第一段（`/usr/local/lib/hermes-agent/venv/bin/python`）或查模块 `__file__` 物理路径
2. **系统 `python3` ≠ Hermes 运行时**：croniter 只在 Hermes venv 里。测 Hermes 内部行为必须用 `/usr/local/lib/hermes-agent/venv/bin/python`（用系统 python3 测出"croniter 缺失"是假警报，差点否掉可行方案）
3. **仿真 `compute_next_run` 必须显式传 anchor**：不传时它用真实 `_hermes_now()`，伪造的 tick 时间线会全部错乱（第一次仿真因此翻车，输出"差 1110s 未到期"）

## 五、优化方向清单（探讨项，勿自行实施）

按性价比排序，2026-08-25 已向用户列出，等拍板：

1. **零代码**：建 plan 时 R 预检预扣滑点（预期入场 = 触发价 ×1.003），R 不达标不建；触发价避开整数关口/24h 高点正上方 1 tick
2. **修 2 倍空转**（推荐）：两个 job schedule 改 `* * * * *`，链路延迟上限 240s→120s，期望滑点砍半（≈9.4U/62 笔）。不碰 executor/plan/规则/阈值
3. **收紧偏差门**（现阈值=1 个止损距离，允许吃掉 1R）：改 0.5R 或 0.5% 取小。**必须先用账本回测**（见 `rule-backtest.md`，08-10"弱市禁多"就是这么被否决的）
4. **按结构止损反推仓位**（滑点大时不平移 SL，保住结构位，改减 qty）：治第二层代价，但会撞名义价值偏差门 ±25%，改动面最大
5. 限价 IOC 封顶滑点 / 合并两跳（有并发双开风险，需文件锁）/ systemd timer 对齐 K 线边界（脱离 Hermes Cron 体系）——收益不确定或风险 > 收益，暂缓
