"""Cross-platform alert sound + TTS helpers.

Drop-in replacements for the Windows-only beep()/speak() functions found in
Codex-era alert scripts (which use ``winsound`` and PowerShell). Copy these two
functions over the originals and remove ``import winsound`` / ``import ctypes``.

Needs only the stdlib: ``os``, ``sys``, ``subprocess``.
"""

import os
import subprocess
import sys


def beep(alerts, level):
    """Play an alert sound cross-platform.

    Tries ``aplay``/``paplay``/``afplay`` for a WAV file, then falls back to the
    terminal bell (\\a). ``alerts`` is a dict; ``level`` is "ALERT" or "WATCH".
    """
    sound = alerts.get("sound", "none")
    if sound == "none":
        return
    wav = alerts.get("wav_path")
    if sound == "wav" and wav and os.path.exists(wav):
        for player in ("aplay", "paplay", "afplay"):
            try:
                subprocess.Popen([player, wav],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                return
            except FileNotFoundError:
                continue
    # Fallback: terminal bell (works in most terminals); more rings for ALERT.
    try:
        sys.stdout.write("\a" * (3 if level == "ALERT" else 1))
        sys.stdout.flush()
    except Exception:
        pass


def speak(text):
    """Cross-platform TTS. Tries espeak / say (macOS) / festival; silent if none."""
    for cmd in (["espeak", text], ["say", text], ["festival", "--tts"]):
        try:
            p = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE if cmd[0] == "festival" else None,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if cmd[0] == "festival":
                p.communicate(input=text.encode())
            return
        except FileNotFoundError:
            continue
