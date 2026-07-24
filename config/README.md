# trading-config 恢复说明

`trading-config.example.json` 是脱敏备份，不含真实 API 密钥。

## 恢复步骤

1. 复制到正确位置：
   ```bash
   cp config/trading-config.example.json ~/.hermes/trading-config.json
   ```

2. 编辑填入真实密钥：
   ```bash
   nano ~/.hermes/trading-config.json
   ```
   替换 `YOUR_BINANCE_API_KEY_HERE` 和 `YOUR_BINANCE_API_SECRET_HERE`

3. 设置权限（必须）：
   ```bash
   chmod 600 ~/.hermes/trading-config.json
   ```

## 注意

- API Key 只需 read + trade 权限，**绝不启用提现权限**
- 此文件含密钥，已被 .gitignore 排除，不会上传
