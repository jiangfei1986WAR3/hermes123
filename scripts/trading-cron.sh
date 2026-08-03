#!/usr/bin/env bash
# trading-cron.sh - 交易事件处理 + 持仓管理（配置1m≈实际2分钟由cron调用）
# 静默设计：无事发生时不输出任何内容

EXECUTOR="/root/.hermes/scripts/binance_executor.py"
OUTPUT=""

# 1. 处理事件（触发开仓、TP1、过期清理）
EVENT_RESULT=$(python3 "$EXECUTOR" process-events 2>&1 | grep -v '^\[' | grep -v '^[0-9]')
if [ "$EVENT_RESULT" != "[]" ] && [ -n "$EVENT_RESULT" ]; then
    OUTPUT="📋 事件处理:\n$EVENT_RESULT\n"
fi

# 2. 管理持仓（TP1平半仓+移保本）
MANAGE_RESULT=$(python3 "$EXECUTOR" manage 2>&1 | grep -v '^\[' | grep -v '^[0-9]')
if [ "$MANAGE_RESULT" != "[]" ] && [ -n "$MANAGE_RESULT" ]; then
    OUTPUT="${OUTPUT}📊 持仓管理:\n$MANAGE_RESULT\n"
fi

# 3. 检测持仓变动（止损/止盈/平仓通知）
WATCH_RESULT=$(python3 "$EXECUTOR" watch 2>&1 | grep -v '^\[' | grep -v '^[0-9]')
if [ -n "$WATCH_RESULT" ]; then
    OUTPUT="${OUTPUT}🔔 持仓变动:\n$WATCH_RESULT\n"
fi

# 只在有内容时输出（静默模式）
if [ -n "$OUTPUT" ]; then
    echo -e "$OUTPUT"
fi
