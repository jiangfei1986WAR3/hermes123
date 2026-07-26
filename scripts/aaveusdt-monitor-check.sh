#!/usr/bin/env bash
PLAN="$HOME/.hermes/trading-plans/AAVEUSDT-plan.json"
MONITOR="$HOME/.hermes/skills/auto-signal-monitor/scripts/signal_monitor.py"
[ ! -f "$PLAN" ] && exit 0
OUTPUT=$(python3 "$MONITOR" --plan "$PLAN" 2>&1 | grep -v "DONT_NOTIFY")
if echo "$OUTPUT" | grep -qiE "ALERT|TRIGGER|EXPIRED|EVENT_WRITTEN"; then
    echo "$OUTPUT"
fi
