---
name: porting-skills-across-agents
description: "Port skills/backups from other agent frameworks (Codex ~/.codex/skills, Claude Code, etc.) or a user's skill-backup git repo into Hermes (~/.hermes/skills). SKILL.md frontmatter is largely portable; scripts need cross-platform fixes."
version: 1.0.0
metadata:
  hermes:
    tags: [skills, migration, porting, codex, cross-platform, adaptation]
    related_skills: [hermes-agent, claude-code, codex, opencode]
---

# Porting Skills Across Agent Frameworks

Use when a user wants to reuse skills created for another agent (OpenAI Codex,
Claude Code, OpenCode) inside Hermes, or asks to "restore my skills from my
backup repo" onto a new machine. Codex and Claude-style `SKILL.md` frontmatter
(`name`, `description`) is close enough to Hermes that the files load as-is once
copied into `~/.hermes/skills/` — but bundled **scripts** usually carry
Windows-isms that break on Linux.

## Workflow

1. Get the source (clone the user's backup repo, or locate `~/.codex/skills`).
2. Copy each skill directory into `~/.hermes/skills/` (keep the `SKILL.md` +
   `scripts/`, `references/`, `templates/` subdirs).
3. Find hardcoded paths & Windows-only code (see grep recipes below).
4. Replace paths with Hermes/Linux equivalents (see table).
5. Make any Windows-only Python imports cross-platform (winsound/ctypes/PowerShell TTS).
6. Verify: `python3 -m py_compile <script>` + `python3 <script> --help` for each script.
7. Reload skills (`/reload-skills` in-session, or they appear in the next session)
   and confirm with `hermes skills list`.

## Path & interpreter replacements

| Source (Codex/Windows) | Hermes/Linux replacement |
|---|---|
| `C:\Users\<u>\.codex\skills\<skill>\scripts\x.py` | `~/.hermes/skills/<skill>/scripts/x.py` |
| `D:\Projects\codex1\<workdir>` (default output dirs) | a Linux project path, e.g. `~/Documents/<project>/<workdir>` (create it with `mkdir -p`) |
| `python "<path>"` (in SKILL.md code blocks) | `python3 "<path>"` (this host has `python3` only; `python` is missing) |

## Detection grep recipes

```bash
# hardcoded Windows paths in skill docs/scripts
grep -rn 'C:\\Users\|D:\\Projects\|\.codex\\skills' ~/.hermes/skills/<skill>/

# Windows-only Python imports
grep -rn 'winsound\|ctypes\|msvcrt\|winreg\|winsound' ~/.hermes/skills/<skill>/scripts/
```

## Pitfalls

- **sed escaping backslashes is unreliable** for `C:\Users\...` paths — the
  single-backslash form rarely matches. Do the path replacement in Python
  (`content.replace(old, new)` over the file text) instead of `sed`.
- A skill can load fine in Hermes while its **scripts still crash at runtime**
  on `import winsound`. The SKILL.md loading and the script's runtime imports
  are independent — always py_compile + `--help` every bundled script.
- `agents/openai.yaml` (or other `agents/*.yaml`) files in a Codex skill are
  metadata for that other agent; harmless in Hermes — leave them.
- Don't restructure a user's domain skill set when porting. Keep their folder
  layout and umbrella intact; only fix portability. Restructuring is a separate
  decision the user should drive.
- PEP 668 hosts: scripts using only stdlib need no install; if a script needs a
  third-party package, install into a venv or via `uv`, not bare `pip`.

## Support files

- `scripts/cross_platform_sound.py` — drop-in replacement for a `beep()`/`speak()`
  pair that uses Windows `winsound`/PowerShell; copy the functions over the
  Windows versions to make alert scripts portable.
- `references/windows-import-replacements.md` — table of Windows-only Python
  imports and their cross-platform substitutes.
- `references/ported-trading-skills-runtime.md` — end-to-end notes from porting
  the user's Codex trading-skill set: install/adapt steps, the
  `binance-market-scanner` JSON shape, the "execution layer only fires on
  TRIGGER_OR_CLOSE, so empty `executableNow` is normal" pitfall, and the
  top-scores → plan_calculator fallback for producing WAIT_TRIGGER plans.
