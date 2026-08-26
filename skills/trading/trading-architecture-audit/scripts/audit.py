#!/usr/bin/env python3
"""Read-only architecture drift audit for the trading system."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path


HERMES_HOME = Path(os.environ.get("TRADING_AUDIT_HERMES_HOME", "~/.hermes")).expanduser()
SKILL_DIR = Path(__file__).resolve().parent.parent
BASELINE_PATH = Path(os.environ.get(
    "TRADING_AUDIT_BASELINE",
    str(SKILL_DIR / "references" / "approved-hashes.json"),
)).expanduser()
DOCUMENT_BASELINE_PATH = Path(os.environ.get(
    "TRADING_AUDIT_DOCUMENT_BASELINE",
    str(SKILL_DIR / "references" / "approved-documents.json"),
)).expanduser()

PRIMARY = {
    "command": HERMES_HOME / "skills/trading-command-center/SKILL.md",
    "candidate": HERMES_HOME / "skills/trading/trading-candidate-screening/SKILL.md",
    "planner": HERMES_HOME / "skills/trade-execution-planner/SKILL.md",
    "planner_rules": HERMES_HOME / "skills/trade-execution-planner/references/execution-rules.md",
    "ops": HERMES_HOME / "skills/trading/trading-ops-reliability/SKILL.md",
}
CANDIDATE_REF_DIR = HERMES_HOME / "skills/trading/trading-candidate-screening/references"
FORBIDDEN_TOOLS = ("space_gate.py", "pivot_gate.py")


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    path: str
    message: str
    line: int | None = None


@dataclass(frozen=True)
class DocumentChange:
    change: str
    path: str


def read_text(path: Path, findings: list[Finding]) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        findings.append(Finding("P0", "READ_FAILED", str(path), f"cannot read: {exc}"))
        return ""


def line_for(text: str, needle: str) -> int | None:
    pos = text.find(needle)
    return None if pos < 0 else text[:pos].count("\n") + 1


def require(text: str, needle: str, path: Path, code: str, message: str, findings: list[Finding]) -> None:
    if needle not in text:
        findings.append(Finding("P1", code, str(path), message))


def forbid(text: str, pattern: str, path: Path, code: str, message: str, findings: list[Finding], severity: str = "P1") -> None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if match:
        findings.append(Finding(severity, code, str(path), message, text[:match.start()].count("\n") + 1))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def audit_hashes(findings: list[Finding]) -> None:
    try:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        findings.append(Finding("P0", "BASELINE_FAILED", str(BASELINE_PATH), f"cannot load baseline: {exc}"))
        return
    hashes = baseline.get("execution_hashes")
    if not isinstance(hashes, dict) or not hashes:
        findings.append(Finding("P0", "BASELINE_EMPTY", str(BASELINE_PATH), "execution_hashes is missing or empty"))
        return
    for raw_path, expected in hashes.items():
        path = Path(raw_path.replace("~/.hermes", str(HERMES_HOME), 1)).expanduser()
        if not path.is_file():
            findings.append(Finding("P0", "RUNTIME_MISSING", str(path), "approved runtime file is missing"))
            continue
        actual = sha256(path)
        if actual != expected:
            findings.append(Finding("P0", "RUNTIME_HASH_CHANGED", str(path), f"sha256 changed: expected {expected}, actual {actual}"))



def load_document_baseline(findings: list[Finding]) -> dict:
    try:
        data = json.loads(DOCUMENT_BASELINE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        findings.append(Finding("P0", "DOCUMENT_BASELINE_FAILED", str(DOCUMENT_BASELINE_PATH), f"cannot load document baseline: {exc}"))
        return {}
    if not isinstance(data.get("roots"), list) or not isinstance(data.get("document_hashes"), dict):
        findings.append(Finding("P0", "DOCUMENT_BASELINE_INVALID", str(DOCUMENT_BASELINE_PATH), "roots or document_hashes is missing"))
        return {}
    return data


def audit_document_changes(findings: list[Finding]) -> list[DocumentChange]:
    baseline = load_document_baseline(findings)
    if not baseline:
        return []
    extensions = set(baseline.get("extensions", [".md", ".json", ".py", ".sh"]))
    current: dict[str, str] = {}
    for rel_root in baseline["roots"]:
        root = HERMES_HOME / rel_root
        if not root.is_dir():
            findings.append(Finding("P3", "DOCUMENT_ROOT_MISSING", str(root), "approved trading document root is missing"))
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in extensions and "__pycache__" not in path.parts:
                current[str(path.relative_to(HERMES_HOME))] = sha256(path)
    approved = baseline["document_hashes"]
    changes: list[DocumentChange] = []
    for rel in sorted(set(current) - set(approved)):
        changes.append(DocumentChange("ADDED", rel))
    for rel in sorted(set(approved) - set(current)):
        changes.append(DocumentChange("REMOVED", rel))
    for rel in sorted(set(current) & set(approved)):
        if current[rel] != approved[rel]:
            changes.append(DocumentChange("MODIFIED", rel))
    return changes


def audit_frontmatter(texts: dict[str, str], findings: list[Finding]) -> None:
    for key in ("command", "candidate", "planner", "ops"):
        path = PRIMARY[key]
        text = texts[key]
        if not text.startswith("---\nname:") or "\n---\n" not in text[4:]:
            findings.append(Finding("P1", "FRONTMATTER_INVALID", str(path), "skill frontmatter is missing or malformed"))


def audit_layers(texts: dict[str, str], findings: list[Finding]) -> None:
    command = texts["command"]
    candidate = texts["candidate"]
    planner = texts["planner"]
    planner_rules = texts["planner_rules"]
    ops = texts["ops"]

    require(command, "Every selected Top candidate must run `fetch_klines.py`", PRIMARY["command"], "TOP_DEEP_ANALYSIS_MISSING", "Top candidates are not guaranteed deep analysis before historical review", findings)
    require(command, "avoid-only example does not reserve a Top-3 slot", PRIMARY["command"], "TOP3_SLOT_DRIFT", "avoid-only candidate may reserve an opportunity slot", findings)
    require(candidate, "不能自行标 `PLAN_READY/WATCH_ONLY/NOT_EXECUTABLE`", PRIMARY["candidate"], "CANDIDATE_OWNER_DRIFT", "candidate checklist no longer explicitly forbids final status", findings)
    require(planner, "single final decision layer", PRIMARY["planner"], "PLANNER_OWNER_MISSING", "planner is no longer the explicit single final decision layer", findings)
    require(ops, "Top候选全部 `fetch_klines` + `trading-analysis`", PRIMARY["ops"], "OPS_FLOW_DRIFT", "ops skill no longer preserves Top-candidate deep-analysis order", findings)

    forbid(ops, r"扫描出候选\s*→\s*先粗筛", PRIMARY["ops"], "OPS_PRE_FILTER", "ops skill restored pre-deep-analysis filtering", findings)
    forbid(ops, r"分数\s*[≥>]\s*60\s*→\s*盈亏比粗筛", PRIMARY["ops"], "OPS_PRE_FILTER", "ops skill restored score-to-R prefilter", findings)
    forbid(candidate, r"扫描阶段即可排除|fetch_klines预算留给", PRIMARY["candidate"], "CANDIDATE_PRE_FILTER", "candidate checklist is filtering before deep analysis", findings)
    forbid(candidate, r"同样判本轮无达标候选|同样判.*空仓|直接判本轮无达标候选", PRIMARY["candidate"], "CANDIDATE_FINAL_DECISION", "candidate checklist directly decides the round result", findings)

    require(planner, "Fixed margin: 10 USDT.", PRIMARY["planner"], "FIXED_MARGIN_DRIFT", "fixed 10U margin override is missing", findings)
    require(planner, "Leverage: BTC 20x; all other symbols 10x.", PRIMARY["planner"], "LEVERAGE_DRIFT", "approved leverage override is missing", findings)
    require(planner, "2.6U is historical guidance, not an active hard gate", PRIMARY["planner"], "HARD_GATE_STATUS_MISSING", "2.6U is not explicitly marked inactive", findings)
    require(planner_rules, "No fixed USDT amount is an automatic rejection threshold", PRIMARY["planner_rules"], "FIXED_USDT_GATE_DRIFT", "planner rules may allow a fixed-USDT automatic gate", findings)
    require(planner, "entry_trigger − structural_stop", PRIMARY["planner"], "RISK_BASIS_DRIFT", "risk is not explicitly based on entry_trigger and structural stop", findings)

    forbid(candidate, r"风险额\s*>?\s*2\.6U\s*→\s*WATCH_ONLY|严格按2\.6U硬边界", PRIMARY["candidate"], "UNAPPROVED_26_GATE", "2.6U was promoted to an active rejection gate", findings)
    forbid(command, r"Default risk per trade:\s*`?0\.5%|默认.*0\.5%", PRIMARY["command"], "RISK_MODEL_DRIFT", "generic 0.5% sizing appeared in command center", findings)

    jaccard_paths = [PRIMARY["candidate"], PRIMARY["command"], PRIMARY["ops"], CANDIDATE_REF_DIR / "scan-json-structure.md"]
    for path in jaccard_paths:
        text = read_text(path, findings)
        for match in re.finditer(r"jaccard[^\n]{0,220}", text, re.IGNORECASE):
            segment = match.group(0)
            overreach = re.search(r"(?:=|→|同样判|独立判据|佐证信号)[^\n]{0,100}(?:空仓|无达标候选|不生成计划|高潮确定|一律不建)", segment, re.IGNORECASE)
            safe = re.search(r"不是[^\n]{0,60}(?:独立判据|高潮|空仓)|只(?:表示|反映)[^\n]{0,60}(?:名单|稳定性)|须结合|不能单独", segment, re.IGNORECASE)
            if overreach and not safe:
                findings.append(Finding("P2", "JACCARD_OVERREACH", str(path), "Jaccard was promoted to a standalone climax/no-trade conclusion", text[:match.start()].count("\n") + 1))
                break
    require(candidate, "Jaccard只反映名单稳定性", PRIMARY["candidate"], "JACCARD_SCOPE_MISSING", "Jaccard is not explicitly limited to list stability", findings)


def audit_references(findings: list[Finding]) -> None:
    candidate = read_text(PRIMARY["candidate"], findings)
    for rel in sorted(set(re.findall(r"`(references/[^`]+\.md)`", candidate))):
        path = PRIMARY["candidate"].parent / rel
        if not path.is_file():
            findings.append(Finding("P3", "BROKEN_REFERENCE", str(path), "referenced file does not exist"))

    if not CANDIDATE_REF_DIR.is_dir():
        findings.append(Finding("P3", "REFERENCE_DIR_MISSING", str(CANDIDATE_REF_DIR), "candidate reference directory is missing"))
        return

    for path in CANDIDATE_REF_DIR.glob("*.md"):
        text = read_text(path, findings)
        if re.search(r"2\.6U|风险额红线|风险额上限", text):
            header = "\n".join(text.splitlines()[:8])
            if not re.search(r"PROPOSED / NOT ACTIVE|历史状态|历史假设|当前口径|状态说明|非现行规则|方法已部分作废", header):
                findings.append(Finding("P2", "HISTORICAL_GATE_UNMARKED", str(path), "2.6U/history gate lacks an inactive-status header"))

    for tool in FORBIDDEN_TOOLS:
        script_path = PRIMARY["candidate"].parent / "scripts" / tool
        if script_path.exists():
            findings.append(Finding("P0", "FORBIDDEN_TOOL_REVIVED", str(script_path), "deleted executable tool reappeared"))
        for path in CANDIDATE_REF_DIR.glob("*.md"):
            text = read_text(path, findings)
            for match in re.finditer(re.escape(tool), text):
                context = text[max(0, match.start() - 180): match.end() + 180].lower()
                if not any(word in context for word in ("已删除", "deleted", "不得", "不再生效", "历史")):
                    findings.append(Finding("P2", "FORBIDDEN_TOOL_ACTIVE_TEXT", str(path), f"{tool} is mentioned without deleted/historical context", text[:match.start()].count("\n") + 1))
                    break


def audit() -> tuple[list[Finding], list[DocumentChange]]:
    findings: list[Finding] = []
    texts = {key: read_text(path, findings) for key, path in PRIMARY.items()}
    audit_frontmatter(texts, findings)
    audit_layers(texts, findings)
    audit_references(findings)
    audit_hashes(findings)
    changes = audit_document_changes(findings)
    return sorted(findings, key=lambda f: (f.severity, f.path, f.line or 0, f.code)), changes


def render(findings: list[Finding], changes: list[DocumentChange], mode: str, as_json: bool) -> None:
    status = "DRIFT DETECTED" if findings else ("PASS WITH CHANGES" if changes else "PASS")
    payload = {
        "audit": "trading-architecture",
        "mode": mode,
        "status": status,
        "hermes_home": str(HERMES_HOME),
        "baseline": str(BASELINE_PATH),
        "document_baseline": str(DOCUMENT_BASELINE_PATH),
        "finding_count": len(findings),
        "document_change_count": len(changes),
        "document_changes": [asdict(c) for c in changes],
        "findings": [asdict(f) for f in findings],
    }
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"Trading architecture audit: {status}")
    print(f"Mode: {mode.upper()}")
    if changes:
        print("\nDocument changes since approved baseline:")
        for change in changes:
            print(f"{change.change:<8} {change.path}")
    if not findings:
        print("Checked: layer ownership, Top-candidate flow, sizing, hard gates, references, deleted tools, runtime hashes, and trading document inventory.")
        return
    for finding in findings:
        location = finding.path + (f":{finding.line}" if finding.line else "")
        print(f"\n{finding.severity} {finding.code}\n{location}\n{finding.message}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("pre", "post"), required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings, changes = audit()
    render(findings, changes, args.mode, args.json)
    return 0 if not findings else 1


if __name__ == "__main__":
    sys.exit(main())
