# Server Disaster Recovery（阿里云镜像 + 部署拓扑，2026-08-15 实测）

用户核心关切：服务器出问题后，交易系统 + Hermes 能否完整恢复。回答前先查证实际部署，别凭印象。

## 部署拓扑（2026-08-15 实测，本机）

| 组件 | 位置 | 备注 |
|---|---|---|
| Hermes 本体 | `/usr/local/lib/hermes-agent/venv`，launcher `/usr/local/bin/hermes` | pip/uv 安装（非 git），在系统盘 |
| 全部数据 | `/root/.hermes/` 一个目录 | config.yaml、.env(密钥)、skills、memories、state.db(会话)、cron/、trading-*(交易全套)、weixin/(登录态) |
| 开机自启 | systemd `hermes-dashboard.service`（enabled + Restart=always） | 一个 unit 管三样：Dashboard + Cron 调度器 + Gateway（描述行 "Cron scheduler + Web UI + Gateway"；gateway 进程的父进程是 systemd --user，由该服务拉起） |
| 备份 | `/root/hermes-backup`（git, SSH remote → GitHub jiangfei1986WAR3/hermes123） | 2026-08-15 从 /tmp 迁至永久位，详见主 SKILL.md Backup 节 |

## 阿里云自定义镜像恢复语义（"老照片"陷阱）

- 镜像 = 系统盘快照，磁盘上一切（软件+数据+自启服务）都会回来，开机即用
- **但恢复到的是"构建镜像那一刻"的状态**：构建之后的改动（新会话/记忆/交易计划/监控任务/技能补丁）全不在镜像里
- ⚠️ 镜像构建时间未知时必须先确认：`ls -la ~/.hermes/gateway-starts.log` 的 mtime、会话/交易文件最新 mtime 与"用户印象中的最新数据"对比，判断镜像落后多少天
- 对策：迁移前**重新构建最新镜像**；或镜像 + git 备份双路恢复（git 补 8-08 后增量——但 git 只有 skills/scripts/config-example/trading-plans，**没有** memories/state.db/trading-history/会话，这些只能靠镜像）

## 不随镜像走的东西（迁移后要重配）

1. **安全组规则**（实例级网络配置，非磁盘）→ 新实例重新配置端口
2. **公网 IP**（除非绑弹性公网 IP）→ 域名解析需改；有回调地址的通道（iLink 等）注意 IP 变化
3. **微信 iLink token**：登录状态文件（weixin/）随镜像走，但通道 token 可能因环境变化失效 → 大概率要重新扫码一次
4. API key（DeepSeek/百炼）在 .env 里，随镜像走，无需重配

## 恢复后第一动作（体检清单）

1. `systemctl status hermes-dashboard` + `ps aux | grep -E 'gateway|dashboard'` — 自启是否拉起
2. `cronjob action=list` — Cron 是否恢复调度（trading-cron + 各监控）
3. 跑 trading-system-status 例行检查：持仓/余额/挂单交叉验证
4. 检查 plan 是否已过期（停机期间市场在动，过期 plan 会被自动清理——零成本，但用户可能不知道）
5. `git -C /root/hermes-backup status -sb` + push 一次，确认备份链路可用

## 技能文档膨胀管理（用户 2026-08-15 问"会不会越来越大"）

- 本技能 SKILL.md 两周长到 100KB（每 4 天 +15KB 增速）。影响面：仅 agent 加载时吃上下文（≈5 万 token），**交易系统运行零影响**（Cron/executor 是纯代码，不读 SKILL.md）
- 向用户解释时用三层框架：①交易系统自动运行→不用；②找机会流程→不加载这本；③运维类任务→才翻
- 拆分阈值（与用户达成）：**主 SKILL.md >20 万字节时拆**（历史案例归档到 references/，主文件留核心规则+索引；trading-system-status 已是此模式）。用户明确"不擅自动，到阈值先提醒"
- 影响范围口径：拆分 = 动 1 个主文件 + 新建 2-4 个 references 子文件，全在一个技能目录内，不碰代码/Cron/plan
