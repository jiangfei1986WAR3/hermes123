# 死计划检测（rules[] 缺失，零警告）

2026-08-08 HYPEUSDT 例：另一会话/模型（kimi-k3，走 trading-command-center 全流程）建了 breakdown_short 计划，写成**分析快照格式**而非监控引擎格式——只有 `entry.trigger_price` + `monitor.trigger_condition`（字符串 "15m close <= 53.75"）+ `setup_type`/`status`/`analysis_snapshot`，**没有 `rules[]` 数组**，也没有 `expires_at`。

signal_monitor 只遍历 `rules[]` → 每分钟跑一遍实际评估 0 条规则 → 输出 "no trigger" 静默退出。永不触发、不报错、永不过期。

## 为什么验证没抓住

建计划的会话跑了 `--dry-run`，看到 "静默 DONT_NOTIFY" 就判验证通过、建了 Cron。但静默有两种含义：
1. 规则存在、还没触发（正常等待）
2. 根本没有规则（死计划）

两者 stdout 长得一模一样。dry-run 只测"触不触发"，不测"有没有规则"。

## 关键陷阱

executor 字段（entry_trigger/stop_loss/take_profits）可以**全对**而监控侧同时是**死的**——signal_monitor 和 binance_executor 读同一 plan 文件但看**不同字段**（前者看 rules[]，后者看 entry/stop/tp）。所以"挂单参数看着对"不能证明监控活着。

## 识别（一条命令）

```bash
python3 -c "import json;print(len(json.load(open('<plan>')).get('rules',[])))"
```

输出 `0` = 死计划（rules 缺失）。>0 且每条 type 在白名单内（breakout/invalidation/pullback_reclaim/market_filter）才算活。

## 处理

- 确认是否用户所建（陌生计划先问，见 memory 规则）
- 用户要删 → 清五样：Cron + plan + state + 脚本 + 事件残留
- 用户要修 → 按原参数重写成标准格式（单触发 breakout + 失效线 invalidation + market_filter + expires_at），重写后先验规则数 >0 再 dry-run，再让现有 Cron 接管

## 根治：引擎硬校验（已实施 2026-08-08，commit 3db1fb1 已推送）

signal_monitor `run_plan_path` 在过期检查之后校验：plan 无 `rules[]` 或为空 → stderr 打 `ERROR ... 缺少 rules 数组（或为空）...死计划。请用标准格式重建` + `sys.exit(2)`。效果：

- **建计划时**：dry-run 立刻报错，不再"假静默"骗过验证（上面"两种静默"的盲区被封死）
- **监控运行时**：包装脚本 `2>&1` + grep ERROR → 报错原样推微信；exit 2 非零退出另发错误告警。死计划最多存活 1 分钟即暴露，双保险
- **配套隔离（同一 commit）**：`--plans-dir` 目录循环和 `main()` 循环各加 `except SystemExit`——单个坏计划报错后不拖垮同批其他计划（SystemExit 不是 Exception 子类，只捕 Exception 接不住，这是本次审计发现的自引隐患）

**它管不了的边界**：rules 格式全对但价位/方向定错（分析判断问题），任何格式校验都查不出来，仍靠 dry-run 后人工过目。"未知规则类型"WARNING（TRUMP 例）本来就有输出、包装脚本也抓 WARNING，两类静默死亡故障模式至此都有告警覆盖。
