# Hermes Cron 调度标准与节奏验证（2026-08-25 起生效）

**建任何长期监控 / 事件处理 Cron，schedule 一律写 5 字段 cron `* * * * *`，不要写 `every 1m`。**

## 为什么（0.43 秒的锚点错位）

`every 1m`（interval 型）实测**每 120 秒才跑一次**，慢一倍，且是 100% 必然空转而非偶发：

- `cron/jobs.py:99` `TICKER_INTERVAL_SECONDS = 60`，实测心跳周期 **60.07s**
- interval 型 `next_run = last_run_at + 60s`，而 `last_run_at` 记的是**执行完成**时刻，比 tick 起点晚约 0.55s
- → next_run 落在 `xx:13.840`，下一 tick 落在 `xx:13.4x`，**差 0.43s 判未到期 → 跳过一轮**

`* * * * *`（cron 型）由 croniter 把 next_run 吸附到**整分钟边界**，tick 固定落在 :13.4 → 永远已过期 13 秒 → 每轮必点火。

类比（用户偏好）：闹钟每 60 秒响一次，但你起床后要 0.55 秒才写好"下次 60 秒后"的便签——闹钟再响时便签还差 0.4 秒没到，你翻身继续睡，于是两分钟起一次床。

## 已执行状态（勿回退）

2026-08-25 用户授权，两个 job 已改并验证：

```
事件处理 61e562582aa9: 08:42 前 120.07~120.21s → 08:43:16 起连续 7 轮 60.05~60.08s ✅
XMR监控 0aeb7c20d92f: 08:44 前 120.13~120.15s → 08:45:16 起连续 5 轮 60.06~60.08s ✅
失败条目 0；持仓/挂单/plan mtime/日志错误数零变化
```

⚠️ **Cron 列表里 schedule 显示 `* * * * *` 是正常的，别当异常"修"回 `every 1m`。**
回滚点 `~/.hermes/cron/jobs.json.bak_20260825_084241`；回滚 `hermes cron edit <id> --schedule 'every 1m'`。

## 秒级粒度不可达（别再提"改 30s"）

- `parse_duration` 正则无秒单位，`multipliers={'m':1,'h':60,'d':1440}`；`every 30s` / `every 0.5m` 直接 ValueError
- 6 字段 cron（`0 * * * * */30`）能过解析、croniter 也真算出 30 秒后 next_run，但 **ticker 60s 是物理下限**（全代码库仅 1 处定义 + 1 处引用，无配置项可覆盖），每 tick 最多点火一次
- 改常量 = 改 Hermes 源码，git 安装升级即被覆盖 ❌ **此路已封闭**

## 改 schedule 的安全性（已验证，可复用）

- `cronjob(action='update', job_id=…, schedule='* * * * *')`：`tools/cronjob_tools.py:1708` 只在 `schedule is not None` 时入 updates，其余字段同样有 `is not None` 守卫
- `update_job` 用 `{**job, **updates}` **字典合并** → `script`/`no_agent`/`deliver`/`repeat` 原样保留
- `update_job:2323` 重算 next_run 不传 last_run_at（锚点=now）→ 改完 ≤60s 首次点火
- 全代码库把 `cron` 与 `interval` 当同类循环任务（`{"cron","interval"}` 成对出现 8 处），两处 interval 专属分支均良性
- **diff 验证法**：改前存 jobs.json 全量快照，改后逐字段比对，只允许 `schedule`/`schedule_display`/`next_run_at` 变化。若 `last_run_at`+`repeat.completed` 也变了，先对照 `hermes cron runs` 查是不是期间正常点火，别急着报"意外变更"

## 验证节奏的命令

```bash
hermes cron runs <job_id>     # 看相邻时间戳差 —— 发现空转的关键手段,配置值不可信
```
一键探针 `scripts/cron_cadence_check.py`（run 间隔 + 心跳周期，直接给"配置 vs 实际"倍数）。
测 ticker 周期：采样 `~/.hermes/cron/ticker_heartbeat` 的 mtime。

⚠️ **测 Hermes 内部模块必须用它自己的解释器** `/usr/local/lib/hermes-agent/venv/bin/python`：
- 系统 `python3` 缺 croniter → 会误得出"cron 表达式不可用"的错误结论（08-25 踩过，当场向用户纠正）
- `/proc/<PID>/exe` 指向底层 uv CPython，绕过 venv site-packages，**会误报模块缺失**；判断 gateway 能 import 什么要看 `cmdline` 第一段或模块 `__file__` 物理路径
- 仿真 `compute_next_run` 必须显式传 anchor，否则它用真实 `_hermes_now()`，伪造时间线全乱

## 仍是旧口径的位置（改动需用户授权）

以下写着 `every 1m` 或"实际节奏≈配置+1分钟"，属过时口径，照抄会重新引入 2 倍空转：
- 本技能 SKILL.md「观察哨兵」第 2 步、「开仓滑点」行的 `0.3-0.7%`
- `trading-command-center/SKILL.md` 第 31 / 41 / 198 行（198 行是建监控 Cron 的操作模板，影响最大）
- `references/event-write-vs-process-race-20260824.md`「1m 配置≈实际 2 分钟」（现象描述，根因见本文）

## 链路延迟预算（讲滑点根因时用）

```
修复前: 监控跳 0~120s + 事件处理跳 0~120s = 0~240s (期望 ~120s)
修复后: 监控跳 0~60s  + 事件处理跳 0~60s  = 0~120s (期望 ~60s)
```
滑点真值与根因三段拆分见 `references/entry-latency-and-slippage-audit.md`。
