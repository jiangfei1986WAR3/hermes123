# 路径解析与脚本验证

## 目的

候选深查需要调用 200 日阻力/支撑复核脚本时，必须从 `skill_view` 返回的 `skill_dir` 拼接实际路径，不要凭技能名称猜目录。

当前脚本路径：

```text
/root/.hermes/skills/trading/trading-candidate-screening/scripts/resistance_above.py
/root/.hermes/skills/trading/trading-candidate-screening/scripts/support_below.py
```

## 调用前检查

1. 先读取技能，确认 `skill_dir` 与脚本清单。
2. 用绝对路径调用：

```bash
BASE=/root/.hermes/skills/trading/trading-candidate-screening
python3 "$BASE/scripts/resistance_above.py" SYMBOL1,SYMBOL2 --ref=SYMBOL1=PRICE
python3 "$BASE/scripts/support_below.py" SYMBOL1,SYMBOL2 --ref=SYMBOL1=PRICE
```

3. `--ref` 必须使用等号三段格式 `--ref=SYMBOL=触发价`；参考价必须是执行触发价，不是当前价或破位位。
4. 脚本返回路径错误时，不得报告“脚本缺失”；先搜索 `skill_dir` 下的实际文件并修正调用路径。
5. 只有在正确路径调用并获得输出后，才能声明 200 日阻力/支撑复核已完成。

## 本次纠错

曾误用 `/root/.hermes/skills/trading-candidate-screening/scripts/`，漏掉中间层 `trading/`，导致已存在脚本被错误报告为缺失。正确路径调用后，阻力与支撑脚本均正常返回结果。