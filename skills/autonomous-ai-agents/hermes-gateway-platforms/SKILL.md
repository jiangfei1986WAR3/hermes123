---
name: hermes-gateway-platforms
description: "Connect messaging platforms (WeChat, Signal, Feishu, DingTalk, WhatsApp, etc.) to the Hermes Agent gateway."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, gateway, messaging, wechat, weixin, platforms, setup]
    homepage: https://github.com/NousResearch/hermes-agent
    related_skills: [hermes-agent]
---

# Hermes Gateway Platforms

How to connect a specific messaging platform to the Hermes Agent gateway so
the agent can receive and reply to messages on that platform. The bundled
`hermes-agent` skill documents the gateway *commands* at a high level; this
skill captures the **per-platform mechanics, auth flows, and pitfalls** that
you otherwise have to dig out of the adapter source.

Load the `hermes-agent` skill first for the general gateway CLI
(`hermes gateway setup/run/install/start/status`). This skill tells you what
each platform actually needs and what goes wrong.

## General methodology (any platform)

1. **Confirm the adapter ships in this install.** Adapters live under
   `<install>/gateway/platforms/`. Find the install dir with `which hermes`
   then read the launcher, or check `/usr/local/lib/hermes-agent/gateway/platforms/`.
   Look for `<platform>.py` (or a `<platform>/` package). Some platforms
   (WhatsApp, Email, SMS) moved to `plugins/platforms/<name>/adapter.py`.

2. **Check runtime deps with the HERMES venv python, NOT system python3.**
   The gateway runs inside Hermes's own venv. A `ModuleNotFoundError` from
   `python3 -c "import aiohttp"` is irrelevant if the venv has it. Check:
   ```bash
   /usr/local/lib/hermes-agent/venv/bin/python -c "import aiohttp, cryptography; print('ok')"
   ```
   (Adjust venv path to your install dir; some installs use `.venv/`.)

3. **Run the interactive setup wizard** — it drives the platform-specific
   auth (QR scan, API key, token, OAuth) and writes credentials for you:
   ```bash
   hermes gateway setup
   ```
   Pick the platform from the list. Do NOT hand-edit `.env` for platforms
   that have a QR/device flow — the wizard saves the full credential bundle.

4. **Start the gateway and verify:**
   ```bash
   hermes gateway install && hermes gateway start   # durable background service
   hermes gateway status                            # confirm the platform is connected
   ```

5. **Keep it alive.** On an SSH server enable linger so logout doesn't kill it:
   ```bash
   sudo loginctl enable-linger $USER
   ```
   Logs: `~/.hermes/logs/gateway.log`. In a gateway session, `/platforms`
   shows per-platform connection status.

## Auth flow varies by platform

- **QR / device login (no API key):** Weixin (personal WeChat), WhatsApp
  (Baileys bridge). The wizard shows a QR; scan with the phone app. Credentials
  expire — re-run setup to re-auth if messages stop flowing.
- **API key / token in `.env`:** Telegram, Discord, Slack, Signal, Matrix, etc.
- **OAuth / app registration:** Feishu, DingTalk, WeCom, Teams (need app id/secret
  from the vendor console).

See `references/` for per-platform detail. Currently documented:

- `references/weixin-personal.md` — personal WeChat via Tencent iLink Bot API
  (QR login, env vars, account storage, WeChat risk-control pitfalls).

When you set up a new platform and learn its quirks, add
`references/<platform>.md` and a one-line pointer here so the next session
doesn't re-read the adapter source.

## Pitfalls

- **Checking deps in the wrong interpreter** — see step 2. The system
  `python3` and the Hermes venv are different environments.
- **Promising delivery in the TUI** — cron/gateway output is NOT delivered
  into a TUI session; it goes to the connected messaging platform.
- **Credential expiry on QR-authed platforms** — long idle periods can drop
  the session; re-run `hermes gateway setup` to re-scan.
- **Cannot restart/stop the gateway from inside a gateway session.** When the
  agent runs *through* the gateway (a messaging session), `hermes gateway
  restart`/`stop` — and even `systemctl --user restart hermes-gateway` — are
  deliberately blocked: SIGTERM propagates to the child process and would kill
  the very session handling the message. After any `.env`/config change that
  needs a reload, ask the USER to run `hermes gateway restart` from a separate
  terminal, then verify via `journalctl --user -u hermes-gateway -n 30`.
- **`.env` writes need consent + the right tool.** `patch`/`write_file` refuse
  `~/.hermes/.env` as a protected credential file; use a terminal command
  (`sed -i` / append) and get explicit user consent before touching secrets.
- **"Connected" ≠ authorized.** `gateway status` showing a platform connected
  only means the adapter is wired; inbound senders are still gated by the DM
  policy. With the default `pairing` policy the first message is blocked
  (`Unauthorized user ... on <platform>`) until the user_id is allowlisted or
  the pairing request is approved. See `references/weixin-personal.md`.
- **Vendor risk control** — personal-account bridges (WeChat, WhatsApp) can
  be restricted by the vendor for non-official clients; use a stable,
  established account and avoid frequent reconnects.
