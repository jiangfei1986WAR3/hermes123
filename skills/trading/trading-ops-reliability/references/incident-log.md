# Incident Log（事故档案，一行一条）

主 SKILL.md 瘦身时（2026-08-17）从正文搬出的事故完整经过。格式：日期｜现象｜根因｜修法/教训。排查同类问题时先在这里按日期/关键词找。

## 部署与流程类

- **2026-07-22｜WeChat 会话重启后台监控进程与 TUI 打架**｜WeChat 端没查 cronjob list/近期会话就重启了 signal_monitor --loop 后台进程，而 TUI 端已迁移到 Cron｜根因：跨会话操作前不查现状。教训：动手前必须 cronjob list + session_search + pgrep 三查（→ 主文档 Cross-Session 节）
- **2026-07-26｜write_file 覆盖已修复的监控脚本**｜用旧模板覆盖了含 EVENT_WRITTEN 修复的 uni-monitor-check.sh，脚本退化｜教训：覆盖前先 `[ -f ]` 检查，已存在不覆盖（→ 主文档 Monitor Deployment 节）
- **2026-08-03｜验证拦截跑 monitor-check.sh 误开 BNB 仓**｜验证 BNB 时没带 --dry-run 跑 monitor-check.sh，写出 TRIGGER 事件，2 分钟内 executor 开了 0.16@592.41——正是验证刚否决的那笔｜教训：验证=只跑 `--dry-run` 一条命令；monitor-check.sh 是生产通道，验证阶段碰都不碰
- **2026-08-05｜XLM dry-run 已 ALERT 后仍跑生产脚本**｜同款复发：dry-run 报警后为看输出又跑了 monitor-check.sh → 写出 TRIGGER 事件（及时删除未开仓）｜教训：同上，规则两次验证
- **2026-08-04｜全部 Cron 消失**｜另一会话（微信/Web）执行了"清空所有监控和计划"，连 trading-cron 一起删｜诊断法：jobs.json 68字节=空列表，用 mtime 推清空时刻 + session_search 找执行者；重建 trading-cron 用 every 1m，建后看 cron/output 时间戳验证节奏

## 执行器 BUG 修复史（全部已修复）

- **2026-07-23｜TP1 双平风险**｜交易所 Algo 单与 manage Cron 可同时触发 TP1｜修：manage 先查 TP1 Algo 单是否还在，已成交则跳过减仓只做保本
- **2026-07-23｜条件单 -4120 全被误诊为账户限制**｜实为 Binance 2025-11 API 迁移：条件单改走 Algo Order API（/fapi/v1/algoOrder）｜修：executor 全改 Algo 端点（→ 主文档 Algo API 节）
- **2026-07-24｜TP1 成交后价格回落则永不移保本**｜manage 用 `mark_price >= tp1_price` 当"TP1 是否发生过"的代理，价格回落后条件为 False，SL 永停原宽止损（RE 实例：SL 0.49 未移到入场 0.5113）｜根因教训：**绝不用现价代理历史事件**，交易所订单状态才是权威信号｜修：删除价格门槛，只看 Algo 单存在性
- **2026-07-24｜manage_position 稳态刷屏**｜无持仓返回"check"动作、TP1 后每分钟报 tp1_pending/tp1_already_handled → 微信每 2 分钟一条｜修：稳态返回空，只有状态迁移才输出（→ 主文档 Silence Rules）
- **2026-07-24｜通知丢失 4 连**｜RE 开仓+TP1+watch 两分钟内 4 条通知全撞 iLink 30s 限流，静默丢弃｜用户靠手动问才知道持仓；2026-08-01 ADA 保本通知再次丢失（两起）｜至今无修复，网关丢消息不重试（→ 主文档 iLink 限流节）
- **2026-07-25｜TP2 残留单污染下一笔交易**｜保本损平掉剩余仓后无人撤 TP2，同币再交易时旧 TP2 意外触发减仓｜修：watch 检测到仓位消失时 cancel_all_orders（→ 主文档 watch 清理四步）
- **2026-07-25｜TP1 减仓后 TP2 数量不匹配**｜TP1 减半后 TP2 仍挂原数量（SL28+TP27=55 但只剩 28），reduceOnly 兜底但 TP2 先触发会剩 1 单位贱平｜修：manage 在保本成功后自动撤全部 TP 单、按剩余数量重挂，末单吸收舍入误差；保本挂单失败则不重挂 TP（安全设计）
- **2026-07-26｜UNI 触发被误判为失效、错过交易**｜事件分类靠 rule_id 子串匹配，"breakout" 命中 "break" → TRIGGER 被写成 INVALIDATION → executor 删了计划（UNI 3.85→3.88+ 没吃到）｜修：分类改走显式 rule_type 字段，rule ID 可自由命名；教训：**永不靠自由文本子串做逻辑分支路由**
- **2026-07-26→28｜INVALIDATION 撤单剥掉持仓保护（组合 BUG）**｜首版修复撤单前不查持仓；失效线=止损价同数值，开仓后价格碰失效线 → INVALIDATION 触发撤掉 SL/TP，仓位裸奔｜每个零件单独看都对，组合起来是 BUG｜再修三点：INVALIDATION 分支先查持仓（有仓跳过）；cancel_all_orders 加 position guard（force 参数）；CLI cancel-all 活仓需 --force｜教训：**任何撤交易所单的代码路径必须先验证没有活跃持仓依赖这些单**
- **2026-07-26→28｜AAVE 触发排队 13h 后裸奔 -2.43U**｜max_positions 满导致触发排队 13 小时，市场漂移后入场价 93.22 > 计划 SL 93.2，止损单被币安拒挂（触发价会立即成交），用户手动平 95.65，本可只亏 0.87U｜修：Gate 6 入场偏差门（现价偏离触发价 > 止损距离 → 拒开仓）+ Gate 7 滑点校准（实际成交后等距平移 SL/TP 并写回 plan）｜⚠️ Gate 7 铁律：`avgPrice` 市价单常为 null，必须 fallback 到 `get_positions()[symbol].entry_price`，否则校准静默失效
- **2026-07-28｜止损挂单失败假成功 + grep 吞 JSON**｜execute_plan 的 SL except 块无 return，SL 挂了仍报 success=True 仓位裸奔；trading-cron.sh 用 `grep -v 'ERROR'` 过滤日志把 JSON 里的 "status":"ERROR" 也滤掉，失败报告和 7 条安全检查 REJECTED 全被吞｜修：except 内市价平掉新仓+返回 success=False；grep 改 `grep -v '^[0-9]'`（按行首时间戳过滤，JSON 以 { 开头不受伤）｜教训：**混合 stdout 永不按关键词过滤，按行格式过滤或分流**
- **2026-07-28｜滑点不校准 SL/TP**｜Gate 7 旧版只处理"止损跑到入场价错误一侧"的极端情形，正常滑点让实际 R 静默退化（1% 滑点+2.7% 止损 → R 从 1.0 掉到 0.44），TP 从不调整｜修：Option A 等距平移（delta=实际入场-计划入场，SL/TP 全移，保 R 结构）+ 校准价写回 plan 文件（manage 匹配依赖它，容差 0.0001×price）｜通用教训：**任何市价成交后按预计算价挂单的系统，必须按实际成交价重新校准——"差不多"会跨周期累积，污染正在测量的 R 分布**
- **2026-07-28｜平仓类型判断硬编码多单**｜仓位消失分支 direction 默认 long 且依赖 plan 文件存在；plan 被删后空单用多单公式 → 盈亏符号反、TP1 止盈报成止损｜修：方向从 state 快照 amount 符号推断（不依赖 plan 文件），止盈止损判断分多空两分支｜教训：**推断方向用持仓带符号数量，不用依赖可选文件的默认值**
- **2026-07-28｜计划过期不执行/无条件删 plan**｜首版：expires_at 无人检查，过期计划永续监控。修后：过期写 PLAN_EXPIRED 事件。二版 BUG（XRP 08-08 事故）：过期**无条件删 plan** → 持仓还在时 manage 按 plan 遍历找不到该币 → TP1 成交后移保本永不执行（SL 96.2@1.0523 全量未动，`updateTime==createTime` 铁证）｜二修：过期时先查持仓，有仓保留 plan（入场监控停、持仓管理续），平仓后照旧删；副作用=保留期间每分钟重复写 PLAN_EXPIRED 事件，executor 幂等处理，无害｜**移保本是否执行过的铁证**：挂单 `updateTime>createTime` 或 SL 数量==剩余持仓=执行过；`updateTime==createTime`+SL 全量=从未被动过
- **2026-07-28｜market_filter 纯摆设**｜过滤规则 level=WATCH → write_event_file 丢弃，突破照发不管大盘｜修：run_once 检测到 market_filter 激活时拦截 breakout/pullback_reclaim 事件（INVALIDATION 不拦，崩盘也要能失效清理）；数据拉取失败=fail-open 不拦｜已知局限+升级方向（用户选标准版但 DEFERRED，**未经批准勿实施**）：改 4h 收盘 close 判断（非实时 last）+ plan 模板 timeframes=["4h"]、min_volume_ratio=0（纯趋势门）；代价=会拦掉 08-01 ADA/BEAT 类多单
- **2026-07-30｜用错端点误判"仓位裸奔"**｜查 SL/TP 用了 /fapi/v1/openOrders 和 allOrders（只列普通单，Algo 条件单完全不可见）→ 得出"executor 从没挂过单"的错误结论，用户说"我币安后台能查到挂单啊"｜教训：**查 SL/TP 永远用 get_open_algo_orders / openAlgoOrders 端点**（→ 主文档 Quick Diagnostic 第 7 步）
- **2026-08-03｜保本移位静默失败（IDOL 事故）**｜TP1 +0.81U 后剩余半仓仍按原宽 SL 止损 -1.81U。根因：滑点校准写回 plan 的是**未取整**浮点（0.023115274...），交易所挂单是取整价（0.02312），差 4.7e-6 > manage 匹配容差 2.3e-6 → 匹配失败走"已处理"分支，保本永不触发｜触发条件：低价币+多笔成交均价长尾（任何 delta 在 0.0001×price 内不能 round-trip 的情形）；与本金大小无关｜修：写回前先 round_price（Option A，commit 6b74138）；验证过三档 tickSize（IDOL 1e-5/UNI 1e-3/BTC 0.1）｜教训：**任何写入文件后要与交易所挂单价匹配的价格，必须先按交易所 tickSize 取整**；取整用交易所 PRICE_FILTER 不是自选小数位；取整幂等，只改本地账本不碰交易所挂单
- **2026-08-05｜手写签名查询用 v1 positionRisk 404**｜账户查询端点是 v2（/fapi/v2/positionRisk、/fapi/v2/balance）｜教训：手写查询复制 executor 的 v2 路径

## 监控引擎修复史

- **2026-08-06｜pullback_reclaim 现价已越过 reclaim=建完立即触发**｜触发判断用实时价，touched_zone 只看 20 根内是否碰过回踩区 → 现价高于 reclaim 时建完第一分钟就触发=变相追高（AVAX 例 reclaim 6.62 现价 6.86）；镜像=现价低于 reclaim 追空（XLM 例）｜修：新增 had_pullback 顺序判定（多：需"最早收盘≥reclaim 之后出现过收盘<reclaim"；空镜像反之），直接路过不触发｜配套纪律：建完必跑 dry-run，**"构造正确"≠必静默，dry-run 是唯一裁判**（XLM 按 LINK 构造法仍 ALERT）；反弹空的正确构造=pullback 区设在 20 根区间之上（LINK 例）；pullback_reclaim 不走 require_close
- **2026-08-08｜空 rules 计划死计划静默永不触发（HYPE 例）**｜Web 面板格式（entry.trigger_price+monitor.* 无 rules[]）的 plan，signal_monitor 静默跳过 → 永不触发｜修：引擎硬校验，空/缺 rules → stderr ERROR + exit 2（包装脚本 grep ERROR 推微信）；`sys.exit()` 配套在 run_directory_once/--loop 两处循环加 `except SystemExit` 隔离（单个坏计划不拖垮其他）｜教训：**引擎新增"终止类"异常时必须检查所有循环调用方的捕获——except Exception 接不住 SystemExit/KeyboardInterrupt**

## 工具坑

- **2026-08-06｜fetch_klines.py 输出 ANSI 色码 → read_file 判 binary**｜剥色码后仍可能判 binary（残留控制字符）｜别卡在 read_file 重试，用 terminal `sed -n` 分段读（→ 主文档 fetch_klines 节）
- **2026-07-22｜ENA 实盘踩的 Hedge Mode API 参数冲突**｜-1106（reduceOnly+positionSide 冲突，全库删 reduceOnly）/-4136（MARKET+closePosition）/-1102（STOP_MARKET 缺 quantity）/科学计数法陷阱（filter 字符串 "0.0000100" 经 str(float()) 变 "1e-05" → decimals=0 → 价格数量归零；必须解析原始字符串）｜完整 10 BUG 审计见 binance-executor 技能 references/code-audit-2026-07-22
- **2026-07-28｜round_qty 浮点截断**｜`math.floor(qty/step)*step` 撞 IEEE754 边界（0.3/0.1=2.99999... → 0.2），约半数输入中招；manage 重挂 TP 时留粉尘仓位永不平｜修：`floor(qty/step + 1e-9)*step`；stepSize="1" 时必须返回 int（币安收 1142 拒 1142.0）

## 待办与用户决策（非事故）

- **2026-07-24｜plan 层重复问题**：用户决定手动"清掉所有监控和计划"解决，**勿加自动预检**（执行层硬锁已防超开，plan 层混乱烦但不危险）
- **2026-07-26｜满仓排队刷屏**：用户选手动清理，**勿自动清监控**；Gate 6 偏差门已兜底（排队漂移>止损距离会拒开仓），现在只是烦不是险
- **2026-07-28｜仓位模型不一致（DEFERRED）**：plan 层固定风险模型 vs executor 固定保证金模型，executor 忽略 plan.risk.quantity。用户决定加本金时一起重设计；重议时推荐 Option C（固定风险+名义上限）
- **2026-08-15｜文档膨胀管理共识**：当时与用户达成"主 SKILL.md >20万字节才拆，到阈值先提醒"。2026-08-17 用户主动发起提前优化（第 1 期），本档案即该次优化产物；此后新案例默认进本文件，主文档只留规则+指针
