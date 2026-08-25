#!/usr/bin/env python3
"""Hermes Cron 真实节奏探针（2026-08-25 实测可用）。

用途：回答"监控是不是每分钟真的跑了一次""能不能提频"之前先跑这个。
背景：interval 型 job 配置 `every 1m` 实际每 120s 才点火（确定性 2 倍空转，
      根因见 references/cron-cadence-and-latency.md）。

做两件事：
  1) 对比每个 job 的「配置间隔」vs「run 历史实测中位间隔」，给出倍数
  2) 采样 ticker 心跳文件，测 ticker 真实周期（代码常量 TICKER_INTERVAL_SECONDS=60）

用法：  python3 cron_cadence_check.py [--heartbeat-sample 135]
        --heartbeat-sample 0 可跳过心跳采样（省 2 分钟）
"""
import argparse
import json
import os
import re
import statistics
import subprocess
import time
from datetime import datetime

CRON_DIR = os.path.expanduser("~/.hermes/cron")
JOBS_FILE = os.path.join(CRON_DIR, "jobs.json")
HEARTBEAT = os.path.join(CRON_DIR, "ticker_heartbeat")


def load_jobs():
    try:
        raw = json.load(open(JOBS_FILE))
    except Exception as e:
        print(f"读不到 {JOBS_FILE}: {e}")
        return []
    return raw if isinstance(raw, list) else raw.get("jobs", [])


def configured_seconds(job):
    """从 job 的 schedule 结构推出配置间隔（秒）；cron 表达式返回 None。"""
    sch = job.get("schedule") or {}
    if sch.get("kind") == "interval" and sch.get("minutes"):
        return sch["minutes"] * 60
    return None


def run_intervals(job_id):
    """调 `hermes cron runs <id>` 解析时间戳，返回间隔秒列表。"""
    try:
        out = subprocess.run(
            ["hermes", "cron", "runs", job_id],
            capture_output=True, text=True, timeout=60,
        ).stdout
    except Exception:
        return []
    ts = []
    for line in out.splitlines():
        m = re.search(r"(\d{4}-\d{2}-\d{2}T[\d:.]+)\+", line)
        if m:
            try:
                ts.append(datetime.fromisoformat(m.group(1)))
            except ValueError:
                pass
    ts.sort()
    return [(ts[i + 1] - ts[i]).total_seconds() for i in range(len(ts) - 1)]


def sample_heartbeat(seconds):
    seen = []
    t0 = time.time()
    while time.time() - t0 < seconds:
        try:
            m = os.path.getmtime(HEARTBEAT)
        except OSError:
            m = None
        if m and (not seen or m != seen[-1]):
            seen.append(m)
        time.sleep(2)
    return seen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--heartbeat-sample", type=int, default=135,
                    help="心跳采样秒数（默认 135 才能拿到 2-3 个点；0=跳过）")
    a = ap.parse_args()

    jobs = load_jobs()
    if not jobs:
        return
    print(f"{'job':<26}{'配置':>9}{'实测中位':>10}{'倍数':>8}  判定")
    print("-" * 68)
    for job in jobs:
        name = (job.get("name") or job.get("id") or "?")[:24]
        cfg = configured_seconds(job)
        d = run_intervals(job.get("id") or "")
        if not d:
            print(f"{name:<26}{'-':>9}{'无历史':>10}{'-':>8}")
            continue
        med = statistics.median(d)
        if cfg:
            ratio = med / cfg
            verdict = "✅ 按配置跑" if ratio < 1.5 else f"⚠️ 空转 {ratio:.0f} 倍"
            print(f"{name:<26}{cfg:>8.0f}s{med:>9.0f}s{ratio:>7.1f}x  {verdict}")
        else:
            print(f"{name:<26}{'cron表达式':>9}{med:>9.0f}s{'-':>8}  (croniter 调度)")

    if a.heartbeat_sample > 0:
        print(f"\n采样 ticker 心跳 {a.heartbeat_sample}s ...")
        seen = sample_heartbeat(a.heartbeat_sample)
        if len(seen) > 1:
            ds = [seen[i] - seen[i - 1] for i in range(1, len(seen))]
            for i, m in enumerate(seen):
                d = f"  (+{seen[i] - seen[i-1]:.2f}s)" if i else ""
                print(f"  {datetime.fromtimestamp(m).strftime('%H:%M:%S.%f')[:-3]}{d}")
            print(f"ticker 实测周期 ≈ {statistics.mean(ds):.2f}s  "
                  f"(代码常量 TICKER_INTERVAL_SECONDS=60，不可配置)")
        else:
            print("  采样点不足，加大 --heartbeat-sample 或确认 gateway 在跑")

    print("\n空转 2 倍的根因与修法：references/cron-cadence-and-latency.md")


if __name__ == "__main__":
    main()
