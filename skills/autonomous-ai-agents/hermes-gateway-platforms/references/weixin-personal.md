# Weixin (Personal WeChat) — iLink Bot API

Personal WeChat connects through Tencent's official **iLink Bot API**
(`https://ilinkai.weixin.qq.com`). This is a QR-login flow — like web WeChat —
NOT an API-key flow. Adapter source: `gateway/platforms/weixin.py` (~2300 lines).

## How it works

- **Inbound:** long-poll on `ilink/bot/getupdates` drives message delivery.
- **Outbound:** every reply must echo the latest `context_token` for the peer
  (the adapter tracks and persists these automatically).
- **Media:** files move through an AES-128-ECB encrypted CDN protocol
  (`novac2c.cdn.weixin.qq.com`).
- **Login:** `ilink/bot/get_bot_qrcode` → poll `get_qrcode_status` → on confirm,
  the credential payload (token + account_id) is saved automatically.

## Runtime dependencies

`check_weixin_requirements()` returns True only when BOTH are importable:
- `aiohttp`
- `cryptography` (hazmat ciphers — AES-128-ECB for the CDN)

`certifi` is optional but recommended: Tencent's iLink cert doesn't verify
against some system CA stores (notably Homebrew OpenSSL on Apple Silicon);
certifi's Mozilla bundle fixes that.

Verify with the HERMES venv python (not system python3):
```bash
/usr/local/lib/hermes-agent/venv/bin/python -c "import aiohttp, cryptography, certifi; print('ok')"
```

## Configuration

Connected-check requires BOTH a token AND an account_id — a token alone
won't mark the platform connected.

Env vars (read by `gateway/config.py`):
- `WEIXIN_TOKEN` — the iLink bot token
- `WEIXIN_ACCOUNT_ID` — the account identifier
- `WEIXIN_HOME_CHANNEL` — home channel for delivery

Do NOT hand-set these for a first setup. Run `hermes gateway setup` →
**Weixin / WeChat** and scan the QR; the wizard saves the full bundle.

## Account / credential storage

- Accounts dir: `~/.hermes/weixin/accounts/` (under `$HERMES_HOME`)
- Per-account JSON holds token + persisted `context_token`s (restored on
  restart so replies keep working across gateway restarts).
- `save_weixin_account()` / `load_weixin_account()` manage these.

## Setup steps

```bash
hermes gateway setup        # pick "Weixin / WeChat", scan QR with phone WeChat
hermes gateway install      # durable service
hermes gateway start
hermes gateway status       # confirm Weixin connected
```

## DM authorization (first message blocked)

The connected-check only confirms the adapter is wired; it does NOT authorize
inbound senders. With the default `pairing` DM policy, even the account
owner's first WeChat message is rejected with a log line like:

```
WARNING gateway.run: Unauthorized user: <user_id>@im.wechat on weixin
```

This is expected, not a break. Resolve by either:
- approving the pairing request (`hermes pairing list` / `hermes pairing approve`), or
- switching to an allowlist and adding the owner's `user_id` (printed by the
  login flow / stored in the account JSON) to `WEIXIN_ALLOWED_USERS`.

Relevant env vars: `WEIXIN_DM_POLICY` (pairing|open|allowlist|disabled),
`WEIXIN_ALLOW_ALL_USERS` (true/false), `WEIXIN_ALLOWED_USERS` (comma-separated
user IDs). After changing them the gateway must be reloaded — see the restart
pitfall in the main SKILL.md (you cannot restart it from inside the session).

## Assisted / programmatic login (no user terminal)

`hermes gateway setup` is interactive (needs the user to scan a QR). To drive
it headlessly, call `gateway.platforms.weixin.qr_login(hermes_home)` from the
Hermes venv python in a **background** process, capture the printed QR URL
(`https://liteapp.weixin.qq.com/q/...`) to hand to the user, and read the
returned credential dict. ⚠️ `qr_login()` calls `save_weixin_account()` which
writes the account JSON under `~/.hermes/weixin/accounts/` but does **NOT**
write `~/.hermes/.env` — the setup wizard does that step separately. After a
programmatic login you must manually append the env vars (token, account_id,
base_url, DM policy) to `.env`, then start/restart the gateway.

## Pitfalls

- **Vendor risk control:** Tencent restricts non-official-client logins.
  Fresh accounts or frequent reconnects can get flagged. Use a stable,
  well-established account; avoid rapid drop/reconnect cycles.
- **Session expiry:** errcode `-14` (and ret=-2/errcode=-2 with
  "unknown error") signal a stale session — re-run `hermes gateway setup`
  to re-scan the QR.
- **Rate limit:** errcode `-2` (genuine) = iLink frequency limit; the adapter
  backs off and retries automatically.
- **Long idle:** after long inactivity the credential may expire; messages
  stop flowing until you re-auth via setup.
- **Multi-line replies:** `platforms.weixin.extra.split_multiline_messages`
  (true/false) controls whether long replies are split for WeChat delivery.
