---
name: shell-command-pitfalls
description: Use when shell commands from docs fail or need auditing.
---

# Shell Command Pitfalls (docs & examples)

## 1. Quoted `~` paths — deterministic failure

**Root cause**: `~` is shell syntax — only expanded when UNQUOTED at word start. Inside double quotes it is passed literally; Python's `open()` does not expand it either, so the path resolves as RELATIVE to cwd (e.g. `python3 "~/.hermes/x.py"` from `/root` → `/root/~/.hermes/x.py` → "can't open file"). Deterministic, not intermittent; identical failure in foreground or background.

**Fix**: use absolute paths (`/root/.hermes/...`) or unquoted `~` (`~/.hermes/...`). Keep quotes only around non-`~` args (`--out-dir "/root/..."`).

**Rule**: when copying any command from a skill doc, prefer absolute paths — docs drift and get quoted.

## 2. Doc audit recipe (find all similar problems at once)

Sweep `~/.hermes/skills` + `~/.hermes/scripts` + root `*.md` with these regexes:

| Pattern | Finds |
|---------|-------|
| `"(~|~/)[^"]*"` | double-quoted `~` paths |
| `'~/[^']*'` | single-quoted `~` paths |
| ` ```powershell ` | code-fence marker wrapping bash/python commands |
| `powershell\|\.ps1\|D:\\\|C:\\\|\\\.hermes` | Windows residue |

**False positives to exclude** (look like problems, are not):
- `os.path.expanduser("~/.hermes/...")` in Python code — CORRECT pattern
- Config-file values (e.g. TOML `db-path = "~/.mail/..."`) — program expands its own config
- npm bundled docs, LaTeX `.bst` `{ "~" }` (non-breaking space), ASCII art, docs that intentionally document Windows paths (e.g. porting guides)

**Known instance (2026-08-04, user deferred the fix)**: trading docs carry 8 quoted-`~` command examples — binance-market-scanner/SKILL.md:38,44,50,56,62; trade-execution-planner/SKILL.md:116; risk-manager/SKILL.md:46,52 — plus 3 `powershell` fence markers (trade-execution-planner:115, risk-manager:45,51) left over from a partial powershell→bash cleanup. Until fixed, ALWAYS run those scripts via absolute path.

## 3. Verify attribution with git BEFORE claiming cause

User pattern: asks "is this intermittent?" / "was this introduced by that fix?" — never answer from memory or impression.

1. `session_search` historical invocations — often past runs used absolute paths, which explains "why it never failed before"
2. `git log --oneline --all -- <file>` in the backup repo (`/tmp/hermes-backup`)
3. `git show <commit> -- <file>` and inspect `-`/`+` lines: if deleted lines ALSO contain the defect, it pre-dates that commit
4. `git log -S '<string>' --oneline` to find which commit introduced a literal string

**Pitfall (committed 2026-08-04)**: claimed quoted-`~` was introduced by the 8/1 scanner-fix commit WITHOUT checking git. The diff proved quotes existed on both `-` and `+` lines — only parameter values changed. User challenged the wrong attribution; evidence forced a correction. Check first, then state.

## 4. Response style for these questions

User wants: root cause + concrete analogy (e.g. 邮递员/地址简写), evidence table (file/line/impact), honest severity assessment (≈0 impact vs real risk), and NO unsolicited changes — present the fix list, wait for explicit confirmation ("先不修改" = keep as-is, document only).

## 5. Hermes background curator ("Self-improvement review: Memory updated")

A background curator periodically rewrites MEMORY.md with session lessons and attempts to patch skills. User-owned skills are protected (refused with "User-owned skills are off-limits to autonomous curation"). When the user asks what that message means: it is the curator writing session lessons to memory; it cannot modify user skills or code.
