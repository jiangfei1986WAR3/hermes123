#!/bin/bash
# Hermes 交易技能一键恢复脚本
# 用法：在新服务器装好 Hermes 后，进入本目录运行 bash restore.sh

set -e

HERMES_DIR="$HOME/.hermes"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== Hermes 交易技能恢复 ==="
echo ""

# 1. 恢复技能
echo "[1/3] 恢复技能到 $HERMES_DIR/skills/ ..."
mkdir -p "$HERMES_DIR/skills/trading"
for skill_dir in "$SCRIPT_DIR/skills"/*/; do
    skill_name=$(basename "$skill_dir")
    case "$skill_name" in
        trading-ops-reliability|binance-executor)
            cp -r "$skill_dir" "$HERMES_DIR/skills/trading/$skill_name"
            echo "  ✅ trading/$skill_name"
            ;;
        *)
            cp -r "$skill_dir" "$HERMES_DIR/skills/$skill_name"
            echo "  ✅ $skill_name"
            ;;
    esac
done

# 2. 恢复脚本
echo ""
echo "[2/3] 恢复脚本到 $HERMES_DIR/scripts/ ..."
mkdir -p "$HERMES_DIR/scripts"
for script_file in "$SCRIPT_DIR/scripts"/*; do
    [ -f "$script_file" ] || continue
    cp "$script_file" "$HERMES_DIR/scripts/"
    chmod +x "$HERMES_DIR/scripts/$(basename "$script_file")"
    echo "  ✅ $(basename "$script_file")"
done

# 3. 提示
echo ""
echo "[3/3] 完成！还需要手动操作："
echo ""
echo "  ⚠️  1. 配置 API Key："
echo "     编辑 ~/.hermes/trading-config.json"
echo "     填入币安 API Key（只开读取+交易，不开提币）"
echo ""
echo "  ⚠️  2. 重建 Cron 监控："
echo "     在 Hermes 对话中说'帮我重建交易监控 Cron'"
echo ""
echo "=== 恢复完成 ✅ ==="
