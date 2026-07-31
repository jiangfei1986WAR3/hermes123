#!/usr/bin/env bash
# cleanup-plans.sh - 清理交易计划（手动删监控Cron后使用）
# 用法：
#   ./cleanup-plans.sh          → 清理所有plan（全清）
#   ./cleanup-plans.sh ENA UNI  → 只清理指定币种

PLANS_DIR="$HOME/.hermes/trading-plans"
SCRIPTS_DIR="$HOME/.hermes/scripts"

if [ $# -eq 0 ]; then
    # 全清模式
    echo "🧹 全清模式：删除所有交易计划..."
    rm -f "$PLANS_DIR"/*-plan.json "$PLANS_DIR"/*-plan.state.json
    # 清理对应的监控脚本（保留 trading-cron.sh 和 binance_executor.py）
    rm -f "$SCRIPTS_DIR"/*-monitor-check.sh
    echo "✅ 已清理："
    echo "   - 所有 plan + state 文件"
    echo "   - 所有 *-monitor-check.sh 监控脚本"
    echo ""
    echo "⚠️  记得去 Hermes 定时任务里删除对应的监控 Cron"
    echo "   （trading-cron.sh 事件处理Cron 不要删）"
else
    # 指定币种清理
    for sym in "$@"; do
        SYM_UPPER=$(echo "$sym" | tr '[:lower:]' '[:upper:]')
        SYM_LOWER=$(echo "$sym" | tr '[:upper:]' '[:lower:]')
        
        # 补全USDT后缀
        if [[ "$SYM_UPPER" != *USDT ]]; then
            SYM_UPPER="${SYM_UPPER}USDT"
        fi
        if [[ "$SYM_LOWER" != *usdt ]]; then
            SYM_LOWER="${SYM_LOWER}usdt"
        fi
        
        deleted=0
        for f in "$PLANS_DIR/${SYM_UPPER}-plan.json" "$PLANS_DIR/${SYM_UPPER}-plan.state.json" "$SCRIPTS_DIR/${SYM_LOWER}-monitor-check.sh"; do
            if [ -f "$f" ]; then
                rm -f "$f"
                echo "  🗑️  $f"
                deleted=$((deleted + 1))
            fi
        done
        
        if [ $deleted -eq 0 ]; then
            echo "  ⚪ $SYM_UPPER - 没有找到相关文件"
        else
            echo "  ✅ $SYM_UPPER 已清理 ($deleted 个文件)"
        fi
    done
    echo ""
    echo "⚠️  记得去 Hermes 定时任务里删除对应的监控 Cron"
fi

echo ""
echo "📋 当前剩余计划："
ls "$PLANS_DIR"/*-plan.json 2>/dev/null || echo "   （无）"
