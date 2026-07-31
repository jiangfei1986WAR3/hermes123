#!/usr/bin/env bash
# LINKUSDT 价格监控 - signal_monitor.py wrapper
# grep无匹配时exit 1是正常的"无告警"，用|| true吞掉
python3 ~/.hermes/skills/auto-signal-monitor/scripts/signal_monitor.py \
  --plan ~/.hermes/trading-plans/LINKUSDT-plan.json 2>&1 | grep -E 'ALERT|TRIGGER|EXPIRED|EVENT_WRITTEN|ERROR|WARNING' || true
