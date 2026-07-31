# WeChat (Weixin) — iLink Bot API Setup

Connects personal WeChat to Hermes via Tencent's iLink Bot API
(`ilinkai.weixin.qq.com`). Uses QR-code login — no API key needed.

## Architecture

- Adapter: `<hermes-install>/gateway/platforms/weixin.py`
- Auth: QR scan via iLink Bot API (long-poll `getupdates` for inbound)
- Login function: `gateway.platforms.weixin.qr_login(hermes_home)` (async)
- Credential storage: `~/.hermes/weixin/accounts/<account_id>.json`
- Outbound replies must echo the latest `context_token` for the peer
- Media goes through AES-128-ECB encrypted CDN (`novac2c.cdn.weixin.qq.com`)

## Dependencies

Check in Hermes venv (`<install>/venv/bin/python`), not system Python:
```python
import aiohttp          # required
from cryptography.hazmat.primitives.ciphers import Cipher  # required
import certifi          # optional but helps SSL on some systems
import qrcode           # optional — renders ASCII QR in terminal
```

## QR Login Flow (programmatic / headless)

`qr_login()` is async and prints the QR to stdout. To drive it from a
script (e.g., when assisting a user who can't run the interactive wizard):

```python
import asyncio, sys
sys.path.insert(0, "<hermes-install-path>")
from hermes_constants import get_hermes_home
from gateway.platforms.weixin import qr_login

async def main():
    creds = await qr_login(str(get_hermes_home()))
    # creds = {"account_id": "...@im.bot", "token": "...", "base_url": "...", "user_id": "...@im.wechat"}
    # Returns None on timeout/failure

asyncio.run(main())
```

The QR URL looks like:
`https://liteapp.weixin.qq.com/q/<code>?qrcode=<hex>&bot_type=3`

Poll statuses: `wait` → `scaned` → `confirmed` (or `expired` → auto-refresh).

## ⚠️ Critical Pitfall: Credential Writing Gap

`qr_login()` calls `save_weixin_account()` which writes
`~/.hermes/weixin/accounts/<account_id>.json` — but does **NOT** write
`~/.hermes/.env`. The interactive wizard (`hermes gateway setup` → Weixin)
handles the `.env` step separately via `save_env_value()`.

If you drive `qr_login()` programmatically, you must ALSO write these
env vars to `~/.hermes/.env`:

```
WEIXIN_ACCOUNT_ID=<account_id>          # e.g. 11e1e6896a8a@im.bot
WEIXIN_TOKEN=<account_id>:<hex_token>   # from the JSON file's "token" field
WEIXIN_BASE_URL=https://ilinkai.weixin.qq.com
WEIXIN_CDN_BASE_URL=https://novac2c.cdn.weixin.qq.com/c2c
WEIXIN_DM_POLICY=pairing
WEIXIN_ALLOW_ALL_USERS=false
WEIXIN_ALLOWED_USERS=
WEIXIN_GROUP_POLICY=disabled
WEIXIN_GROUP_ALLOWED_USERS=
```

## Env Var Reference

| Var | Purpose |
|-----|---------|
| `WEIXIN_ACCOUNT_ID` | Bot identity (e.g. `...@im.bot`) |
| `WEIXIN_TOKEN` | Auth token (`account_id:hex`) |
| `WEIXIN_BASE_URL` | iLink API base URL |
| `WEIXIN_CDN_BASE_URL` | Media CDN base URL |
| `WEIXIN_DM_POLICY` | `pairing` / `open` / `allowlist` / `disabled` |
| `WEIXIN_ALLOW_ALL_USERS` | `true` / `false` |
| `WEIXIN_ALLOWED_USERS` | Comma-separated user IDs (for allowlist) |
| `WEIXIN_GROUP_POLICY` | `disabled` / `open` / `allowlist` |
| `WEIXIN_GROUP_ALLOWED_USERS` | Comma-separated group IDs |
| `WEIXIN_HOME_CHANNEL` | Home channel for delivery |

## Connectivity Check

Platform is "connected" when BOTH are present:
```python
config.extra.get("account_id") and (config.token or config.extra.get("token"))
```

## Limitations

- iLink bot identity (`...@im.bot`) is NOT a scriptable personal WeChat
  account — it's a bot identity linked to your WeChat.
- Ordinary WeChat groups typically cannot invite an @im.bot identity.
- iLink does not deliver ordinary-group events to most bot accounts.
- DM is the reliable channel regardless of group settings.
- QR credentials expire over time — re-run login if messages stop flowing.

## Access Policy Notes

- **pairing** (recommended): unknown DM users request access, you approve
  via `hermes pairing approve`.
- **open**: anyone can DM the bot (use with caution).
- **allowlist**: only listed user IDs can interact.
- **disabled**: no DMs at all.
