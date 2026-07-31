---
name: hermes-gateway-platform-onboarding
description: "Connect Hermes to messaging platforms (WeChat/iLink, etc.) — drive QR/OAuth login headlessly, wire credentials into .env, set DM policy, start the gateway, and verify delivery via state.db."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, gateway, messaging, wechat, weixin, onboarding, login, troubleshooting]
    homepage: https://hermes-agent.nousresearch.com/docs/user-guide/messaging/
    related_skills: [hermes-agent]
---

# Hermes Gateway Platform Onboarding

Connecting a messaging platform (WeChat, WhatsApp, Signal, Telegram, …) to
Hermes normally means running the interactive `hermes gateway setup` wizard.
When you're operating headlessly over a tool-call terminal, that wizard often
can't be driven (interactive prompts, QR codes the agent can't scan). This skill
covers the **programmatic path**: call the adapter's login helper directly,
write the credentials the wizard *would* have written, set access policy, start
the gateway, and verify end-to-end delivery by reading the session store.

The bundled `hermes-agent` skill has the gateway command reference; this skill
adds the operational procedure + pitfalls for actually wiring a platform up.

## When to use
- User asks to connect WeChat / WhatsApp / Signal / Telegram / any gateway platform to Hermes.
- The interactive wizard is impractical (SSH session, no interactive PTY, agent-driven).
- A platform connected but messages are being rejected or replies look wrong.

## General procedure

1. **Confirm adapter + deps exist.** Adapters live under
   `<install>/gateway/platforms/<name>.py`. Each usually exports a
   `check_<name>_requirements()` and a login helper. Verify the Hermes venv
   (`<install>/venv/bin/python`) has the runtime deps — the *system* python
   missing them is irrelevant.
2. **Drive login programmatically.** Import the adapter's login coroutine
   (e.g. `qr_login`) from the Hermes venv python, run it, and capture the
   returned credentials. For QR flows, surface the URL (and render a PNG with
   `qrcode` if the terminal art is unusable) and poll the background process.
   See `references/wechat-ilink.md` for the WeChat example.
3. **Write credentials into `~/.hermes/.env`.** The driver only saves the
   account JSON under `~/.hermes/<platform>/accounts/`. The wizard's *second*
   job — exporting `*_ACCOUNT_ID` / `*_TOKEN` / `*_BASE_URL` + access-policy
   vars to `.env` — must be done by you. `.env` is a protected file: `patch`
   is denied; use a `cat >>` / `sed -i` terminal command (needs user approval).
4. **Set DM / group access policy.** Default is `pairing` (unknown senders
   denied until `hermes pairing approve`). For a single known owner, set
   `<PLAT>_DM_POLICY=allowlist` + `<PLAT>_ALLOWED_USERS=<their user_id>` so
   they aren't blocked. The user_id comes from the first inbound message in the
   gateway log ("Unauthorized user: <id>").
5. **Start the gateway.** `hermes gateway install` (sets up systemd + linger)
   then `hermes gateway start`. On a server, linger is what keeps it alive
   after SSH logout.
6. **Restart to reload config.** Config/`.env` changes need a gateway restart
   — **but you cannot restart from inside a running gateway session** (see
   Pitfalls). The user must run `hermes gateway restart` from a *separate*
   terminal.
7. **Verify delivery via state.db, not just logs.** Logs rarely show message
   bodies. Read `~/.hermes/state.db` `messages` table for the platform session
   to see the actual inbound text and the stored assistant `content`. Find the
   session id from `~/.hermes/sessions/sessions.json` (key
   `agent:main:<platform>:dm:<user_id>`).

## Pitfalls

- **Cannot restart/stop the gateway from within a session.** Both
  `hermes gateway restart` and `systemctl --user restart hermes-gateway` are
  blocked from inside the gateway process (SIGTERM would kill the handler).
  Backgrounding the command does NOT help — the guard catches it too. The user
  must run the restart from a separate shell. Don't loop retrying; tell them.
- **`.env` is a protected credential file.** `write_file`/`patch` are denied.
  Edit via terminal (`cat >>`, `sed -i`) — these prompt for user approval.
- **Login driver ≠ full setup.** The login helper saves the account JSON only.
  You must still write the `.env` vars + access policy, or the platform won't
  be "connected" per the gateway's checker (which needs both token AND
  account_id, plus an allowlisted/paired sender).
- **First message from the owner gets "Unauthorized user: <id>".** This is the
  pairing policy working, not a failure — it tells you the exact user_id to
  add to `<PLAT>_ALLOWED_USERS`.
- **Reasoning models leak English "thinking" into replies.** On adapters that
  stream interim output, a reasoning model's English chain-of-thought can be
  delivered before the localized answer, even with `show_reasoning: false`
  globally. Diagnose by reading `reasoning_content` in `state.db` for that
  session — if it's English and the user saw English up front, that's the
  source. Fix: lower/`none` the reasoning level for that platform/session
  (`/reasoning` in-chat or platform reasoning config), or pin a non-reasoning
  model for the gateway. Always confirm by asking the user for the exact text
  they saw before assuming.
- **Verify with real artifacts, not assumptions.** "Login succeeded" in the
  driver log is not proof the user got a reply. Read `state.db` messages to
  confirm both inbound and stored outbound content.

## References
- `references/wechat-ilink.md` — WeChat personal-account login via Tencent iLink
  Bot API: exact env vars, the `qr_login` driver, QR rendering, and the full
  worked flow.
- `scripts/qr_login_driver.py` — reusable driver that runs an adapter's QR
  login coroutine from the Hermes venv and prints the credentials.
