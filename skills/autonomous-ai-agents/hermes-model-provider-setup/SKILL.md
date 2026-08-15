---
name: hermes-model-provider-setup
description: 添加/切换Hermes第三方中转大模型API(custom provider)时用。终端命令流程。
---

# Hermes 第三方中转 API 接入/切换

用户环境：`~/.hermes/config.yaml` 已有 `custom_providers:` 列表（百炼Token Plan 为模板条目）。切换权威文档：`~/.hermes/模型切换指南.md`（含 TeamoRouter 两套配置与已知问题）。

## 方式二：交互式向导（`hermes setup model`）

用户手把手操作时用向导（2026-08 实走通）。逐步流程：

1. `hermes setup model` → provider 菜单选 **Custom endpoint (enter URL manually)**（别选 Remove saved provider / Leave unchanged）
2. **API base URL**：粘贴中转 `/v1` 地址；若显示 `Current key: sk-teamo...` 说明 key 已存在，下一步 **API key 直接回车沿用**
3. 端点自动验证：`Verified endpoint via <url>/models (N model(s) visible)` 出现即连接 OK
4. **Select API compatibility mode**：OpenAI 兼容中转选 **1 Auto-detect**（或直接回车）
5. **Select model**：输编号或模型名（这是默认模型，不是随便选）
6. **Context length**：留空回车（auto-detect）
7. **Display name**：建议改好认的名字（如 TeamoRouter），默认是 URL 去协议后的字符串

向导保存后 `model.api_key` 引用环境变量（如 `${HERMES_CUSTOM_API_TEAMOROUTER_COM_API_KEY}`），key 不进 config 明文。

## 覆盖恐惧（用户必问：加了新的会不会覆盖百炼？）

**不会。** 源码 `hermes_cli/main.py::_save_custom_provider`：按 `base_url` 去重——URL 已存在→只更新该条的 model/context_length；URL 不存在→**追加**到列表末尾。custom_providers 是通讯录，加新联系人不会删旧的。唯一"更新"场景：填的 base_url 与已有条目完全相同。

## 添加新中转（6 步）

1. **Key 写 .env**：`echo 'XXX_API_KEY=sk-...' >> /root/.hermes/.env`。密钥只放 .env，config.yaml 只放配置
2. **备份 + custom_providers 加条目**：跑 `python3 ~/.hermes/skills/autonomous-ai-agents/hermes-model-provider-setup/scripts/add_custom_provider.py --name ... --base-url ... --key-env ... --model ... --models a,b,c`（文本锚点插入，保留注释；脚本内置备份+yaml验证）。**禁用 yaml.safe_load/safe_dump 整文件重写**——会抹掉 config.yaml 全部注释
3. `hermes model --refresh` — custom_providers 是配置时快照，不刷新新 provider 不会出现在选择列表
4. 切换默认模型 4 条：`hermes config set model.provider custom` / `model.base_url <中转 /v1 地址>` / `model.default <模型>` / `model.context_length 128000`（DeepSeek 系 1048576）
5. `systemctl restart hermes-dashboard && systemctl --user restart hermes-gateway`
6. 验证：`hermes doctor` + `hermes chat -q "测试"`

## 坑

- **provider 必须填 `custom`**；填 openai-api → 请求打 api.openai.com → 用中转 key 必然 401（用户踩过）
- 改 config 一律 `hermes config set` 或本技能脚本；禁手动/sed 改 config.yaml（YAML 缩进错会挂 gateway）
- custom_providers 是列表，`hermes config set` 只支持标量键，列表元素只能脚本插行
- 切换模型不改 .env（key 一次配好长期用）
- 用户未确认前不改 model（禁未确认改 model）
- **配置/重启后当前运行会话仍用旧模型**（会话启动时模型固定），重启服务后新会话/微信端才走新模型；用户问"怎么还在用 deepseek"时先解释这点
