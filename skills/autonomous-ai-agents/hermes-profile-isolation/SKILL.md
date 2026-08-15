---
name: hermes-profile-isolation
description: "Create isolated Hermes profile, keep chat/memory separate."
---

# Hermes Profile Isolation (多项目隔离)

用户有一个运行中的交易系统（默认 profile），**不想新项目的聊天记录、记忆、技能互相污染**时用。核心：**用 `hermes profile` 隔离，不是 `hermes project`**。

## Profiles vs Projects（先讲清，用户常搞混）

| | Profiles (`hermes profile`) | Projects (`hermes project`) |
|---|---|---|
| 聊天记录 (state.db) | **独立** | 共享，不隔离 |
| 记忆 (memory) | **独立** | 共享 |
| 技能 (skills) | **独立** | 共享 |
| 定时任务 (cron) | **独立** | 共享 |
| 配置 (config) | **独立** | 共享 |
| 用途 | 彻底隔离的独立项目 | 只是切换工作区文件夹 |

用户要"聊天记录不互相影响" → **必须是 Profiles**。Project 只是把会话锚到某个文件夹，记忆照样共享。

## 建隔离 profile（复用现有模型配置）

目标：全新干净 profile，只复用当前模型/provider，不带走任何技能/记忆/聊天记录。

1. **建 profile**：`hermes profile create <name> --description "..."`
   - 生成 `~/.hermes/profiles/<name>/`，含独立 skills/memories/cron/sessions
   - 建 wrapper：`~/.local/bin/<name>`（**不在 PATH 里**，用绝对路径 `/root/.local/bin/<name>` 调用）
   - `--clone` 会复制技能 → 新项目通常**不要**用，否则带走全套交易技能
2. **新 profile 首次无 config.yaml/.env**（首次 `config set` 或启动才生成）。先设模型段：
   - `/root/.local/bin/<name> config set model.default <model>`
   - `/root/.local/bin/<name> config set model.provider 'custom:<provider名>'`
3. **custom_providers 是列表，`config set` 不支持**：
   - `config set 'custom_providers[0].name' ...` 会**静默写成一个字面顶层 key `custom_providers[0]:`**，Hermes 读不到（明明显示 ✓ 但无效）
   - 必须按主配置 (`~/.hermes/config.yaml`) 的 `custom_providers:` 段，把同款 YAML 列表结构直接写进新 profile 的 config.yaml（write_file/patch 整段），含 name/base_url/key_env/model/models[]
   - 改完跑 `python3 -c "import yaml;yaml.safe_load(open(path))"` 校验 + 打印确认
4. **复制 API key**：`grep '^KEY_NAME' ~/.hermes/.env >> ~/.hermes/profiles/<name>/.env`（key 只在 .env，不进 config）
5. **验证**：`/root/.local/bin/<name> chat -q "当前是什么模型?"` → 正常回答即配置生效

## Web 面板（`hermes dashboard`）切 profile

用户常问\"Web 端能不能进新 profile\"——**能**，且无需重启面板：

- Web 面板是**机器级统一服务**（默认模式），已检测到 ≥2 个 profile 时，顶部自动出现 **ProfileSwitcher**（源码 `web/src/components/ProfileSwitcher.tsx`：`if (profiles.length < 2) return null`）。选 `kronos` → 聊天侧边栏、模型 config、技能、MCP 全部切到该 profile 独立空间
- 聊天记录按 profile 过滤（`ChatSessionList` + `ProfileScopeBanner`），隔离生效
- 若想给某 profile 开**独立面板**（不共用机器级服务）：`hermes dashboard --host 127.0.0.1 --port <p> --isolated -p <name>`（`--isolated` 帮助里明确：profile 启动默认 attach 到机器级统一服务并预选该 profile；`--isolated` 才起专属独立实例）
- 面板版本不同切换器位置可能不同，找不到就让用户在顶部找写有当前 profile 名的下拉

## 坑

- **wrapper 不在 PATH**：`kronos` 直接敲报 `command not found`，用 `/root/.local/bin/<name>`。可把 `$HOME/.local/bin` 加进 `~/.bashrc`
- **PATH 验证别用 `bash -lc`**：登录 shell（`-l`）加载 `~/.profile`，而 PATH 常在 `~/.bashrc` 里，`bash -lc 'command -v kronos'` 会误报找不到。要模拟交互式用 `bash -i -c 'command -v <name>'`（会加载 `.bashrc`），或直接跑 `/root/.local/bin/<name> --version` 验证文件可执行。用户实际开终端是交互式 shell，`.bashrc` 生效
- **新 profile 记忆是空白的**：这是隔离的预期效果，它不会记得现有交易系统的任何守则/经验
- `hermes config set` 对嵌套/列表结构不可靠；标量键（model.default 等）可用，**列表段（custom_providers）只能整段写文件**
- 验证 profile 用 `chat -q`（oneshot），别开交互式会话去试