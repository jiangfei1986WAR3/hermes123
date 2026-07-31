#!/usr/bin/env bash
# SOLUSDT 价格监控 - signal_monitor.py wrapper
python3 ~/.hermes/skills/auto-signal-monitor/scripts/signal_monitor.py \
  --plan ~/.hermes/trading-plans/SOLUSDT-plan.json 2>&1 | grep -E 'ALERT|TRIGGER|EXPIRED|EVENT_WRITTEN|ERROR|WARNING' || true
