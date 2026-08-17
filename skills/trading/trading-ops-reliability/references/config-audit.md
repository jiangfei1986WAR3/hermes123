# Config Change Audit Procedure (MANDATORY before any config change)

改 `trading-config.json` 任何值（max_positions、margin、leverage 等）前的强制审计流程。从主 SKILL.md 拆出（2026-08-17 瘦身）。

When the user asks to change any value in `trading-config.json`:

1. **Search ALL scripts AND skills** for references to the old value. Use BOTH the snake_case token AND every natural-language phrasing:
   ```
   search_files pattern="max_positions" path=~/.hermes/scripts
   search_files pattern="max_positions" path=~/.hermes/skills
   search_files pattern="最多.*仓|持仓.*[0-9]|≥[0-9]则" path=~/.hermes/skills
   # ⚠️ English prose form — binance-executor/SKILL.md uses "max positions (N)"
   #    (NO underscore). A grep for only max_positions SILENTLY SKIPS this file.
   search_files pattern="max positions" path=~/.hermes/skills
   ```
   **Pitfall (hit 2026-07-30 during 2→6 change)**: the first audit grep covered only `max_positions` + Chinese phrases and missed `binance-executor/SKILL.md` ("max positions (2)" — English, no underscore). Always run the English-prose grep too.
2. **Categorize each hit** into one of four types:

   | Type | Example | Action | Risk |
   |------|---------|--------|------|
   | **Functional code** (reads config dynamically) | `CFG.get("max_positions", 1)` | NO change needed — auto-reads new value | Zero |
   | **Code comment** | `# 检查是否有其他持仓（最多1个）` | Update text | Zero |
   | **Documentation/description** | Skill SKILL.md "最多同时1个持仓" | Update text | Zero |
   | **Behavioral rule** (logic embedded in Skill text) | "有仓位则不开新计划" | ⚠️ Must rewrite the LOGIC, not just swap the number | **HIGH — naive number swap introduces logic bug** |

3. **Present the full categorized list to the user BEFORE making changes.** User explicitly requires this audit step.
4. **Never state "N places need changing" from memory** — always check code first. A prior session incorrectly said "3 places" when the actual count was 8, causing user frustration.
5. **Cross-check against the LAST change of this same value via git history** (user's instinct, proven right 2026-07-30):
   ```bash
   cd /root/hermes-backup && git log --oneline --all | grep -i "max_positions\|持仓"
   git diff <prev_commit>^..<prev_commit>   # shows every file the last change touched
   ```
   Any file in the old diff that's missing from your current list = a location your grep missed (usually the English-prose one).

## Known Complete Location List: max_positions (verified 2026-07-30)

When changing max_positions to N, these are ALL 9 locations (1 functional + 8 documentation):

| # | File | Type | Content to change |
|---|------|------|-------------------|
| 1 | `~/.hermes/trading-config.json` | **Functional** | `"max_positions": N` — the ONLY functional change |
| 2 | `skills/trading-command-center/SKILL.md` | Doc | "最多同时 N 个持仓，逐仓模式" |
| 3 | `skills/trading-command-center/SKILL.md` | **Behavioral rule** | "查持仓数（最多N仓；持仓数≥N则不建计划；<N正常执行用户请求）" |
| 4 | `skills/trading/binance-executor/SKILL.md` | Doc (⚠️ English prose "max positions (N)", no underscore) | "max positions (N)" |
| 5 | `skills/trading/trading-ops-reliability/references/system-architecture.md` | Doc | "Check no conflicting position (max_positions=N)" |
| 6 | `skills/trading/trading-ops-reliability/references/system-architecture.md` | Doc | "Up to N positions can be open at a time (max_positions=N config)..." |
| 7-9 | `skills/trading/trading-ops-reliability/SKILL.md` | Doc | 文中"最多N仓"示例（grep "最多.*仓" 定位现行行号；行号随版本漂移） |

**NOT changed**: `binance_executor.py` uses `CFG.get("max_positions", 1)` — dynamic read, zero code change needed.

**Historical incident records are NOT changed**: 历史记录里的旧值描述当时事实，必须原文保留。残留 grep 命中时识别为历史，不是过时引用。

**Still verify with search_files (all three patterns above) AND the git-history cross-check before executing** — line numbers drift as skills evolve, and new references may have been added since this list was compiled.

## Behavioral Rule Pitfall (discovered 2026-07-24)

`trading-command-center/SKILL.md` 原句 "查是否有持仓（互斥：最多1仓，有仓位则不开新计划）" 若机械改成 "最多6仓，有仓位则不开新计划" → **WRONG**——with 1 position the system would refuse to find new opportunities even though 1 slot is still available.

Correct fix: "查持仓数（最多6仓；持仓数≥6则不建计划；<6正常执行用户请求）" — the LOGIC changed, not just the number.

**Rule: when a Skill sentence contains an if/then condition, changing a number inside it requires re-examining the entire condition.**
