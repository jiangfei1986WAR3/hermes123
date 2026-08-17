# Multi-Bug-Fix Rigor Protocol (MANDATORY for trading system code changes)

User explicitly demands: "严谨 不能因为修改这个问题引入新的逻辑BUG". 从主 SKILL.md 拆出（2026-08-17 瘦身）。When fixing multiple bugs in one session:

## Per-Fix Protocol
1. **Before patching**: enumerate ALL callers/consumers of the code being changed (`search_files` for function names, variable names). Confirm each caller's behavior after the change.
2. **Patch**: minimal change, only the error/edge path. Normal flow must be byte-identical.
3. **After patching**: syntax check (`py_compile` / `bash -n`), then walk through 5+ scenarios: normal flow, error flow, API failure, edge case, interaction with prior fixes.
4. **单元级测试（2026-08-06 pullback_reclaim 修复验证模板）**：直接 import 被改模块、构造 mock `data` 字典调用被改函数，覆盖：正常场景、缺陷场景（应不再触发）、镜像方向、字段缺失兼容（退回旧行为）、边界（数据不足/全同向）。改完函数内部逻辑的用 `py_compile` + 场景断言表（每行：场景/实际/预期/✅❌）。
   **⚠️ 用真实持仓币测试"有持仓保留"分支的安全技巧（2026-08-08 PLAN_EXPIRED 修复验证）**：可以构造临时 plan + 事件文件跑 `process-events` 真实验证，但临时 plan 的 SL/TP 价必须故意写成**不匹配现有挂单**的值（如 XRP 实际 SL 1.0523 就写 1.20 / TP 0.9983 就写 0.50）——这样即使测试窗口内 cron 的 manage 循环碰到该 plan，`manage_position()` 的价格匹配全失败、走静默分支，**绝不会真的撤单重挂**。测试后立即删临时 plan，并复查 `openAlgoOrders` 确认各单 `updateTime` 未变（= 全程没碰交易所）。
5. **真实历史数据验证**：用币安公开 klines API（`startTime`/`endTime`，窗口 ≥22 根 15m K 线）拉真实历史走势构造 candle，验证"缺陷案例应不触发、正常案例应触发"（2026-08-06 实测：ADA 刚突破案例旧逻辑误触发/新逻辑拦截 = 修复生效的实证；注意先看走势形态再定预期，别把"刚突破"当"回踩站回"）。
6. **回归**：对全部在跑 plan 跑 `--plans-dir --dry-run`（或逐 plan），确认无 ERROR/未知规则警告、输出与改前一致。
7. **文档同步（易漏）**：改完引擎行为后 `search_files` 全系统 grep 相关规则名/行为描述（技能文档、SKILL.md、记忆），过时描述必须同步（标注已修复+新行为）；历史 incident 记录保留原文。
8. **推送前核对**：目标文件在备份仓库的对应路径（部分技能在 `skills/trading/` 子目录），`git add` 精确文件/目录，commit + push 后 `git status -sb` 确认无 ahead/behind。

## Cross-Fix Verification (after ALL fixes applied)
1. **Re-read ALL modified files in full** (not just the diff hunks).
2. **Cross-check every pair of fixes**: does fix N change any assumption that fix M relies on? Key interactions to check:
   - **新引入的异常类型 vs 所有调用方的 except 子句**：修复若用 `sys.exit()`/raise 新异常，grep 全部调用点确认捕获范围——`except Exception` 接不住 `SystemExit`/`KeyboardInterrupt`（2026-08-08 rules 硬校验例：`sys.exit(2)` 会杀死 `--plans-dir` 目录循环和 `--loop` 循环里后续计划的评估，自审时发现并补了两处 `except SystemExit` 隔离）。同样检查：新 exit code 会不会被包装脚本的 `set -e` 或 Cron 的"非零退出=错误告警"语义放大
   - Shared variables (e.g. `stop_loss` modified by slippage calibration → read by manage_position matching)
   - Shared files (e.g. plan file written by calibration → read by detect_position_changes)
   - Shared functions (e.g. `cancel_all_orders` guard → called from INVALIDATION + detect_position_changes + CLI)
   - Event flow (e.g. market filter blocks TRIGGER → but must NOT block INVALIDATION)
3. **Full lifecycle walkthrough**: trace one trade from plan creation → monitoring → trigger → open → calibrate → manage → TP1 → close → cleanup. Every branch must reach a valid end state.
4. **Report**: present a table of all fixes with status, then the cross-check results, then the lifecycle walkthrough. User needs to see the proof, not just "it's fine".

## User Communication During Code Changes
- **Explain with analogies FIRST, code SECOND.** User says "我有点看不懂" or "通俗举例" → use real-life scenarios (门卫/保险/菜市场/糖果). Map each element: "门卫 = signal_monitor, 锁门 = cancel_all_orders, 你 = 仓位".
- **Discuss feasibility BEFORE writing code.** User asks "是否可以...?" or "我们先探讨先不修改任何代码" → analyze pros/cons, present trade-offs, wait for explicit "OK 进行修复" before touching code.
- **Present severity assessment honestly.** If a bug only triggers under specific conditions (e.g. "only when you first short"), say so. User appreciates knowing "现在不咬你" vs "每笔都在发生".
- **Tables for status tracking.** After each fix, show a cumulative table: bug#, description, severity, status. User tracks progress this way.
- **改技能文档前也先交代性质（2026-08-03 教训）**：用户对"修改交易系统文件"敏感（看到 patch 消息会警觉"你还修改了我们系统的 XX？？？"）。任何修改——包括 SKILL.md 技能文档——先明确"改的是文档/注释（零运行影响）还是代码（运行组件）"，列出原→新内容，用户确认后再动。类比：改的是操作手册，不是机器。
- **报告结论时附可验证证据链（2026-08-04 用户问"你要是偷懒了故意说没偷懒我怎么知道"）**：用户重视可验证证据而非口头声明。报告系统状态/修复结果时主动附证据位置（文件路径、日志行、时间戳、Cron job_id、可复核命令），如 `grep -n "滑点校准" ~/.hermes/trading-executor.log` 验证移保本根因、`ls ~/.hermes/trading-events/` 验证 --dry-run 无副作用。用户会抽查，给证据链比"我检查过了"更省事；关键环节（选币/验证/建Cron）展示痕迹文件本身。

**两类流程质疑的固定应对（2026-08-08 ESP/AAVE 轮验证）**：①用户问"有没有偷懒跳过环节"→ 对照技能规定流程逐条给时间线表（#/环节/执行/证据：命令+文件+时间戳+Cron ID），并**主动交代可更严格的点**（如漏加载的 reference 或估算的数量），只列"全做了"会被追问；②用户问"分析是当时做的还是现在补的"→ 用 **plan 参数↔K线数据行号对应表**证明（触发/止损/TP 每个价位指回原始数据的支撑阻力或 K 线高低点，如 ESP 触发 0.0704=klines 输出的 15m 区间高），结论：分析在决策时已完成，展示=整理已完成的决策格式，不是重新分析。别只答"当时做了"却不给对账证据。
