# Windows-only Python imports → cross-platform substitutes

Scripts written on Windows for Codex commonly import modules that don't exist on
Linux. Map and fix before running on a Linux Hermes host.

| Windows-only import | Purpose | Cross-platform replacement |
|---|---|---|
| `winsound` | Beep / play WAV | `aplay`/`paplay` (Linux), `afplay` (macOS), or terminal bell `\a`. See `scripts/cross_platform_sound.py`. |
| `ctypes` (Win32 calls) | WinAPI, message boxes | Usually removable; for GUI use `tkinter` (cross-platform). |
| `msvcrt` | Console I/O, `_getch` | `tty`/`termios` on POSIX, or `getpass`. |
| `winreg` | Windows registry | N/A on Linux; move config to files. |
| `winsound` + `System.Speech` via `subprocess` PowerShell | Windows TTS | `espeak` / `say` / `festival` subprocess. |

## Detection

```bash
grep -rn 'winsound\|ctypes\|msvcrt\|winreg' ~/.hermes/skills/<skill>/scripts/
```

## Rule of thumb

- If the import is only used for **optional feedback** (sound/TTS), guard it or
  replace with the cross-platform fallback so the script still runs headless.
- If the import is **core logic**, rewrite around POSIX equivalents rather than
  guarding.
- After fixing, always verify with `python3 -m py_compile <script>` and
  `python3 <script> --help` — a SKILL.md can load while its script still fails
  at runtime.
