# 架构审计基线更新流程（用户批准后人工执行）

适用：`trading-architecture-audit` 报 `PASS WITH CHANGES` 且用户审阅 diff 后说"更新基线/批准"（2026-08-28 首次实操验证）。审计器无更新命令，此为批准后的人工步骤。

## 第 1 步：生成自基线的 diff 供用户审阅

- 基线 = `~/.hermes/skills/trading/trading-architecture-audit/references/approved-documents.json` 的 `document_hashes`（sha256），`approved_at` 记批准时刻。
- 备份仓库 `/root/hermes-backup` 的最后一次提交若消息含"更新文档基线"且提交时间 ≈ approved_at（晚几分钟内），该提交即基线快照：`git show <commit>:<rel-path>` 与 `~/.hermes/<rel-path>` diff。
- 先核对 live 文件 mtime > 基线提交时间（08-28 例：approved_at 08-27 16:15、提交 a5fdadd 16:21、三文件 mtime 21:33/22:36 ✓）。
- 审计报告列出的 MODIFIED 文件逐个 diff，向用户按"改动内容 + 对应会话案例 + 分类建议（retain/downgrade/revert）"汇报，等用户拍板。

## 第 2 步：更新 document_hashes（全量重算，不手改单条）

全量重算而非只更改变动项——顺带验证有无审计未列出的漂移：

1. 读 approved-documents.json；
2. 遍历 `roots` 下所有匹配 `extensions` 的文件重算 sha256，键 = 相对 `~/.hermes` 路径；
3. 断言 ADDED=空、REMOVED=空、CHANGED == 审计列出的 MODIFIED 清单、文件总数不变（08-28 例：98=98，CHANGED 恰为 3 份已审阅文件）；
4. 更新 `approved_at`（`datetime.now().astimezone()` 本地时区 ISO）与 note（注明用户审阅后批准）；
5. 写回 `json.dumps(ensure_ascii=False, indent=2) + '\n'`。

## 第 3 步：验证

- 重跑 `audit.py --mode pre` → 期望 `PASS` + exit 0。

## 注意事项

- 写回基线后不自动 push 备份仓库——用户惯例：等用户说"推"才 push。
- 若 ADDED/REMOVED 非空或 CHANGED 与用户审阅清单不一致 → 停止并重新汇报，不得把未审阅改动吸收进基线。
- `trading-architecture-audit` 技能本身是用户自有（未 curator adopt），其 SKILL.md 不能由后台 curator 修改；本流程文件放在这里作为替代落点。
