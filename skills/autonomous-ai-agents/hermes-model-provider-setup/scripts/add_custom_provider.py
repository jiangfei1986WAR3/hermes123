#!/usr/bin/env python3
"""向 ~/.hermes/config.yaml 的 custom_providers 列表追加一条中转 provider。

文本锚点插入以保留文件注释（禁用 yaml.safe_dump 整文件重写——会丢注释）。
内置：备份 -> 插入 -> yaml 验证 -> 失败自动回滚。

用法:
  python3 add_custom_provider.py --name "新中转" --base-url https://api.xxx.com/v1 \
      --key-env MYRELAY_API_KEY --model 模型A --models 模型A,模型B
"""
import argparse, shutil, sys, time

CONFIG = "/root/.hermes/config.yaml"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--key-env", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--models", required=True, help="逗号分隔")
    args = ap.parse_args()

    with open(CONFIG, encoding="utf-8") as f:
        lines = f.readlines()

    # 找 custom_providers: 的下一行（应是一个 2 空格缩进的列表项）
    start = None
    for i, ln in enumerate(lines):
        if ln.strip() == "custom_providers:":
            start = i + 1
            break
    if start is None:
        sys.exit("未找到 custom_providers: 段")
    if start >= len(lines) or not lines[start].startswith("  - "):
        sys.exit(f"custom_providers: 后首行不是列表项: {lines[start]!r}")

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    block = [f"  - name: {args.name}\n",
             f"    base_url: {args.base_url}\n",
             f"    key_env: {args.key_env}\n",
             f"    model: {args.model}\n",
             "    models:\n"] + [f"      - {m}\n" for m in models]

    # 插入点：新条目放在现有第一条之前（顺序无关），避免解析末尾边界
    new_lines = lines[:start] + block + lines[start:]

    # 备份 + 验证 + 落盘（验证失败回滚）
    bak = f"{CONFIG}.bak.{int(time.time())}"
    shutil.copy2(CONFIG, bak)
    try:
        import yaml
        yaml.safe_load("".join(new_lines))  # 写入前验证
    except Exception as e:
        sys.exit(f"YAML 验证失败，未写入: {e}")
    with open(CONFIG, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
    print(f"OK: 已追加 {args.name} -> custom_providers (备份: {bak})")
    print("".join(block))

if __name__ == "__main__":
    main()
