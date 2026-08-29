#!/usr/bin/env python3
"""Quick, read-only review of recent trading-document changes.

This deliberately reports only; it never repairs, moves, deletes, commits,
pushes, executes trading code, calls APIs, or changes the audit baseline.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERMES_HOME = Path(os.environ.get("TRADING_AUDIT_HERMES_HOME", "~/.hermes")).expanduser()
AUDIT_DIR = Path(__file__).resolve().parent.parent
BASELINE = AUDIT_DIR / "references" / "approved-documents.json"
CHECKPOINT = AUDIT_DIR / "references" / "quick-drift-checkpoint.json"
SELF_RELATIVE_PATH = "skills/trading/trading-architecture-audit/scripts/quick_drift_check.py"
EXCLUDED_SELF_PATHS = {
    "skills/trading/trading-architecture-audit/references/approved-documents.json",
    "skills/trading/trading-architecture-audit/references/approved-hashes.json",
    "skills/trading/trading-architecture-audit/references/audit-rules.md",
    "skills/trading/trading-architecture-audit/scripts/audit.py",
    SELF_RELATIVE_PATH,
}

# Only high-confidence, known patterns are flagged.  This is a triage tool,
# not a natural-language decision engine.
TARGET_ROOTS = (
    "skills/trading-command-center",
    "skills/trade-execution-planner",
    "skills/trading-analysis",
    "skills/auto-signal-monitor",
    "skills/binance-market-scanner",
    "skills/risk-manager",
    "skills/trade-review",
    "skills/trading/binance-executor",
    "skills/trading/trading-candidate-screening",
    "skills/trading/trading-ops-reliability",
    "skills/trading/trading-plan-format",
    "skills/trading/trading-system-status",
)
TEXT_EXTENSIONS = {".md", ".py", ".sh", ".json"}
RUNTIME_PATHS = (
    "skills/auto-signal-monitor/scripts/signal_monitor.py",
    "skills/binance-market-scanner/scripts/scan_binance_usdt_perps.py",
    "scripts/binance_executor.py",
    "scripts/trading-cron.sh",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def inventory() -> dict[str, str]:
    out: dict[str, str] = {}
    for rel_root in TARGET_ROOTS:
        root = HERMES_HOME / rel_root
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS and "__pycache__" not in path.parts:
                out[str(path.relative_to(HERMES_HOME))] = sha256(path)
    return out


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def save_checkpoint(data: dict[str, str]) -> None:
    # Checkpoint is deliberately opt-in; normal runs never write it.
    CHECKPOINT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def baseline_inventory() -> dict[str, str]:
    data = load_json(BASELINE, {})
    return data.get("document_hashes", {}) if isinstance(data, dict) else {}


def changed_since_checkpoint(current: dict[str, str], baseline: dict[str, str], use_baseline: bool) -> tuple[list[str], str]:
    if use_baseline:
        old = baseline
        label = "approved document baseline"
    else:
        saved = load_json(CHECKPOINT, None)
        if not isinstance(saved, dict) or not isinstance(saved.get("inventory"), dict):
            repo = Path("/root/hermes-backup")
            if repo.is_dir():
                result = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True)
                if result.returncode == 0:
                    changed = []
                    for line in result.stdout.splitlines():
                        if len(line) > 3:
                            rel = line[3:]
                            if rel in current or rel in baseline:
                                changed.append(rel)
                    if changed:
                        return sorted(set(changed)), "working-tree changes in /root/hermes-backup"
            return sorted(set(current) | set(baseline)), "no checkpoint or backup working-tree changes (showing baseline differences)"
        old = saved["inventory"]
        label = "last quick-check checkpoint"
    return sorted(set(current) | set(old)), label


def diff_text(old_text: str, new_text: str) -> str:
    return "\n".join(difflib.unified_diff(
        old_text.splitlines(), new_text.splitlines(),
        fromfile="previous", tofile="current", lineterm=""
    ))


def previous_text(path: str, old_hash: str | None, baseline: dict[str, str]) -> str:
    # The approved baseline is a hash-only inventory, so obtain previous text
    # from git when available.  If unavailable, report current content without
    # pretending that a line-level diff was recovered.
    repo = Path("/root/hermes-backup")
    if old_hash and baseline.get(path) == old_hash and repo.is_dir():
        candidates = (f"HEAD:{path}", f"HEAD:skills/{path.removeprefix('skills/')}")
        for spec in candidates:
            p = subprocess.run(["git", "-C", str(repo), "show", spec], capture_output=True, text=True)
            if p.returncode == 0:
                return p.stdout
    return ""


def findings_for(path: str, text: str) -> list[tuple[str, str]]:
    low = text.lower()
    findings: list[tuple[str, str]] = []
    if path.endswith("trading-system-status/SKILL.md"):
        groups = ["first_above", "first_below", "last_below", "last_above", "touched_zone"]
        if sum(x in low for x in groups) >= 3 and "had_pullback" in low:
            findings.append(("P1", "system-status contains a complete had_pullback/preflight-like rule; owner is trading-plan-format"))
    if path.endswith("trading-candidate-screening/SKILL.md"):
        if re.search(r"风险额\s*>?\s*2\.6u\s*→\s*watch_only|严格按2\.6u硬边界", low):
            findings.append(("P1", "candidate-screening appears to promote the unapproved 2.6U suggestion to an active gate"))
        if re.search(r"扫描阶段即可排除|fetch_klines预算留给", text, re.I):
            findings.append(("P1", "candidate-screening appears to filter before required deep analysis"))
        if "不能自行标 `plan_ready/watch_only/not_executable`" not in low and re.search(r"直接.*(plan_ready|watch_only|not_executable)", low):
            findings.append(("P1", "candidate-screening may claim final plan status authority"))
    if path.endswith("binance-market-scanner/SKILL.md") or path.endswith("binance-market-scanner/references/scoring.md"):
        if re.search(r"历史.*(禁手|案例).*(提前|直接).*(淘汰|排除)|扫描阶段.*(淘汰|排除)", text, re.I):
            findings.append(("P1", "scanner appears to apply historical filters before the required deep-analysis handoff"))
    if "every 1m" in low and "禁" not in low and "old" not in low and "旧" not in low and not path.endswith("quick_drift_check.py"):
        findings.append(("P2", "old interval-style 'every 1m' wording may revive the stale 120-second cadence"))
    if "actual cadence ≈2 minutes" in low or "actual cadence ~2 minutes" in low:
        findings.append(("P2", "stale approximately-2-minute Cron cadence wording reappeared"))
    if path.endswith("SKILL.md") and re.search(r"jaccard[^\n]{0,180}(?:空仓|不生成计划|一律不建|高潮确定)", text, re.I):
        if not re.search(r"不是|不能单独|只反映|须结合", text, re.I):
            findings.append(("P2", "Jaccard may have been promoted to a standalone market conclusion"))
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline", action="store_true", help="compare against approved document baseline")
    ap.add_argument("--save-checkpoint", action="store_true", help="explicitly save current inventory as the next checkpoint")
    args = ap.parse_args()

    current = inventory()
    for excluded in EXCLUDED_SELF_PATHS:
        current.pop(excluded, None)
    baseline = baseline_inventory()
    paths, label = changed_since_checkpoint(current, baseline, args.baseline)
    findings: list[dict] = []
    changed_count = 0

    print("Trading quick drift check (read-only)")
    print(f"Comparison: {label}")
    print(f"Current documents scanned: {len(current)}")
    print("\nChanged or added documents:")
    for path in paths:
        old_hash = baseline.get(path)
        current_hash = current.get(path)
        if old_hash == current_hash:
            continue
        changed_count += 1
        print(f"- {path}: {'ADDED' if old_hash is None else 'REMOVED' if current_hash is None else 'MODIFIED'}")
        if current_hash is not None:
            p = HERMES_HOME / path
            text = p.read_text(errors="replace")
            for severity, message in findings_for(path, text):
                finding = {"severity": severity, "path": path, "message": message}
                findings.append(finding)
                print(f"  {severity} {message}")

    print(f"\nChanged document count: {changed_count}")
    print(f"Finding count: {len(findings)}")
    if findings:
        print("Result: REVIEW REQUIRED")
        for runtime in RUNTIME_PATHS:
            p = HERMES_HOME / runtime
            print(f"Runtime check: {runtime} = {'present' if p.exists() else 'missing'}")
        print("No files were modified by this check.")
        code = 1
    else:
        print("Result: PASS")
        print("No known high-confidence drift pattern found in the changed documents.")
        print("No files were modified by this check.")
        code = 0

    if args.save_checkpoint:
        save_checkpoint({"inventory": current})
        print(f"Checkpoint saved explicitly: {CHECKPOINT}")
    return code


if __name__ == "__main__":
    sys.exit(main())
