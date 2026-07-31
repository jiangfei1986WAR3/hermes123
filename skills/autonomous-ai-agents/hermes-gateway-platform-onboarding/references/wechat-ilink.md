# WeChat (personal) via Tencent iLink Bot API

Adapter: `gateway/platforms/weixin.py`. Connects a **personal** WeChat account
(not a scriptable bot) through Tencent's iLink endpoint
`https://ilinkai.weixin.qq.com`. Login is **QR-scan only** — no API key. The
login identity is an `...@im.bot` address; ordinary WeChat groups usually can't
invite it, so DM is the only reliably-working channel.

## Prereqs (check in the Hermes venv, not system python)
```
<install>/venv/bin/python -c "import aiohttp, cryptography, qrcode"
```
`aiohttp` + `cryptography` are required (`check_weixin_requirements()`);
`qrcode` is only needed to render terminal/PNG QR art.

## Login flow (`qr_login` coroutine)
`gateway/platforms.weixin.qr_login(hermes_home, bot_type="3", timeout_seconds=480)`
- GETs `ilink/bot/get_bot_qrcode?bot_type=3` → returns `qrcode` (hex token) +
  `qrcode_img_content` (the full scannable liteapp URL — scan THIS, not the hex).
- Prints the URL + ASCII QR, then polls `ilink/bot/get_qrcode_status`
  (statuses: `wait` → `scaned` → `scaned_but_redirect` → `confirmed` / `expired`).
- On `confirmed` it auto-saves the account JSON to
  `~/.hermes/weixin/accounts/<account_id>.json` (token, base_url, user_id) and
  returns `{account_id, token, base_url, user_id}`.

Run it via `scripts/qr_login_driver.py` from the Hermes venv in the background,
then surface the QR URL. If terminal art is unusable for the user, render a PNG:
```python
import qrcode
qrcode.make("<the liteapp URL>").save("/root/.hermes/weixin_qr.png")
```
QR is valid ~8 min and auto-refreshes up to 3× on expiry.

## Credentials → `.env` (the step the wizard does after login)
The driver only writes the account JSON. You must also append to `~/.hermes/.env`
(protected file — use a terminal `cat >>`, not `patch`):
```
WEIXIN_ACCOUNT_ID=<account_id, e.g. 11e1e6896a8a@im.bot>
WEIXIN_TOKEN=<token from the account JSON, "<account_id>:<hex>">
WEIXIN_BASE_URL=https://ilinkai.weixin.qq.com
WEIXIN_CDN_BASE_URL=https://novac2c.cdn.weixin.qq.com/c2c
WEIXIN_DM_POLICY=allowlist          # pairing | open | allowlist | disabled
WEIXIN_ALLOW_ALL_USERS=false
WEIXIN_ALLOWED_USERS=<owner user_id, e.g. o9cq...@im.wechat>
WEIXIN_GROUP_POLICY=disabled        # iLink rarely delivers group events
WEIXIN_GROUP_ALLOWED_USERS=
```
The gateway's connected-check requires BOTH `WEIXIN_ACCOUNT_ID` and a token.

## Access policy
- `pairing` (default): unknown senders denied; approve with `hermes pairing approve`.
- `allowlist` + `WEIXIN_ALLOWED_USERS=<ids>`: best for a single known owner.
- The owner's user_id shows up in the gateway log on their first message as
  `Unauthorized user: <id> on weixin` — copy it into the allowlist.

## Start / restart / verify
```
hermes gateway install   # systemd user service + linger (survives SSH logout)
hermes gateway start
hermes gateway status
```
Restart to reload `.env`: user must run `hermes gateway restart` from a separate
terminal (blocked from within the session). Verify by reading
`~/.hermes/state.db` `messages` for the weixin DM session.

## Reasoning-leak gotcha (qwen/reasoning models)
A reasoning model's English chain-of-thought can be streamed to WeChat before the
Chinese answer, even with global `show_reasoning: false`. Confirm by reading the
session's `reasoning_content` column in `state.db`. Fix: set the platform/session
reasoning to `none`/low, or pin a non-reasoning model for the gateway.
