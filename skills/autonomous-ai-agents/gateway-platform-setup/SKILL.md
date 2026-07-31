---
name: gateway-platform-setup
description: "Connect messaging platforms (WeChat, Telegram, Signal, etc.) to Hermes Agent via gateway adapters — QR login flows, credential wiring, env vars, and startup."
version: 1.0.0
author: agent
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [hermes, gateway, messaging, weixin, wechat, platform, setup]
    related_skills: [hermes-agent]
---

# Gateway Platform Setup

Connect messaging platforms to Hermes Agent through gateway adapters. Each
platform has its own auth flow (QR scan, bot token, OAuth), but the wiring
pattern is the same: obtain credentials → write env vars to `~/.hermes/.env`
→ configure access policies → start the gateway.

## When to Use

- User asks to connect a messaging platform (WeChat, Telegram, Discord,
  Signal, WhatsApp, etc.) to Hermes.
- Gateway is configured but not connecting — credential or policy issue.
- Re-authentication needed after credential expiry.
- User reports "no reply" or very slow replies on a messaging platform —
  could be allowlist rejection OR session compression stall (see below).

## General Procedure

1. **Check dependencies** — platform adapters live in
   `<hermes-install>/gateway/platforms/`. Verify runtime deps import
   cleanly in the Hermes venv (`<install>/venv/bin/python -c "import ..."`),
   NOT the system Python.
2. **Run the auth flow** — prefer the interactive wizard
   (`hermes gateway setup`) when the user can interact with their own
   terminal. For headless/assisted flows, drive the platform's login
   function programmatically (see platform references).
3. **Write env vars** — credentials must land in `~/.hermes/.env`.
   ⚠️ Some programmatic login functions save credentials to a JSON file
   but do NOT write `.env` — the setup wizard handles that step separately.
   Always verify `.env` after any login flow.
4. **Configure access policies** — DM policy (pairing / open / allowlist /
   disabled) and group policy. Pairing is the safe default.
5. **Start the gateway** — `hermes gateway install && hermes gateway start`
   for persistent service, or `hermes gateway run` for foreground debug.
6. **Verify** — read `~/.hermes/gateway_state.json` for per-platform
   connection state (see "Diagnosing connection status" below). Do NOT rely
   on `hermes gateway status` alone — it only reports the systemd *service*
   state, not whether each platform actually connected.

## Diagnosing connection status

When the user asks "is my platform working / connected", check in this order:

1. **Authoritative source — `~/.hermes/gateway_state.json`.** This is the
   real per-platform connection record. Structure:
   `platforms.<name>.state` (e.g. `"connected"`), `.error_code` (null when
   healthy), `.error_message`, `.updated_at`. A platform is healthy when
   `state == "connected"` and `error_code == null`. Read this file directly
   — it's small (~400 bytes).
2. **Service liveness — `hermes gateway status`.** Confirms the gateway
   *process* is running (systemd unit active, PID, uptime). It does NOT show
   per-platform connection, so a "running" service can still have a
   disconnected platform.
3. **Recent logs — `journalctl --user -u hermes-gateway.service --since
   "15 min ago"`** for errors, QR/expiry, or restart loops.

⚠️ **Media support ≠ connection.** A platform being `connected` only means
the message channel is up. Whether images/voice/video actually reach the
model depends on (a) the adapter parsing that media type — grep
`gateway/platforms/<name>.py` for `image|media|msg_type|MessageType.PHOTO`
— and (b) the active model having vision capability. A weak-vision model
receives the image but can't read its contents. Tell the user both halves
honestly rather than just "yes I can see images".

## Sudden disconnection — "was working, now rejected"

When a previously-connected user suddenly can't talk to the agent, the most
common cause is the allowlist going empty (e.g. after `.env` regeneration,
manual edit, or config migration). Diagnostic flow:

1. **Check gateway logs for rejection:**
   `journalctl --user -u hermes-gateway.service --since "10 min ago" --no-pager | grep -i "unauthorized"`
   ⚠️ `hermes gateway logs` is NOT a valid command — always use journalctl.
2. **Cross-validate the user ID.** The rejected ID in the log should match
   `<PLAT>_HOME_CHANNEL` in `.env`. If both agree, you have the right ID.
3. **Check the allowlist var:** `grep "<PLAT>_ALLOWED_USERS" ~/.hermes/.env`
   — if empty, that's the root cause.
4. **Fix:** backup `.env` first (`cp .env .env.bak.$(date +%s)`), then
   `sed -i 's|^<PLAT>_ALLOWED_USERS=$|<PLAT>_ALLOWED_USERS=<user_id>|' ~/.hermes/.env`
5. **Restart gateway:** `hermes gateway restart` (from a non-gateway session
   such as the TUI; from a gateway session, ask the user to restart).
6. **Verify:** ask the user to send a test message; re-check journalctl for
   absence of new "Unauthorized" lines.

## Messages received but no reply — compression stall

When the allowlist is fine (no "Unauthorized" in logs) but the user still
gets no reply, the most common cause is **session bloat triggering
auto-compression**. The gateway accumulates all messages in a platform
session; when the token estimate crosses the compression threshold, it
blocks ALL replies until compression finishes (ceiling: 600 s).

Diagnostic flow:

1. **Check `~/.hermes/logs/gateway.log`** (NOT journalctl — journalctl
   often misses per-message detail for the gateway process):
   ```bash
   tail -100 ~/.hermes/logs/gateway.log | grep -iE "hygiene|compress|still streaming|inbound|response ready"
   ```
2. **Look for these telltale lines:**
   - `Session hygiene: N messages, ~X tokens — auto-compressing` → bloat
     detected, compression started.
   - `still streaming after Ns … extending wait (ceiling 600s)` →
     compression is running and blocking replies.
   - `Demoting busy_input_mode 'interrupt' to 'queue' … because context
     compression is in flight` → new user messages are queued, not dropped.
   - `compressed N → M msgs, ~X → ~Y tokens` → compression finished;
     replies should resume shortly after.
   - `response ready: platform=... time=Ns` → reply generated and being
     sent. If this appears, delivery is happening.
3. **Leading indicator:** a startup warning like `Auxiliary compression
   model X has Y token context, below the main model's compression
   threshold of Z` means the compression model's context window is much
   smaller than the session it must compress — expect very slow
   compression or outright failure on large sessions.

Fix options (pick one):

- **Wait it out.** Compression ceiling is 600 s. If it's already at 300 s+,
  it will likely finish. Queued messages are processed afterward.
- **Delete the bloated session** for instant recovery:
  ```bash
  hermes sessions delete <session_id> --yes
  ```
  Find the session_id from the compression log lines. The next inbound
  message auto-creates a fresh session. Chat history in the user's
  messaging app is unaffected — only the agent's context is reset.
- **Prevent recurrence:** periodically prune old gateway sessions
  (`hermes sessions prune --source gateway --older-than 14d --yes`) or
  lower the compression threshold in config so sessions compress earlier
  while still small.

## Pitfalls

- **Credential writing is sensitive.** Writing tokens to `.env` involves
  secrets. Present the exact env vars to the user and get explicit consent
  before appending, or let them run `hermes gateway setup` themselves.
  Do NOT silently append credentials.
- **System Python ≠ Hermes venv.** Adapters import `aiohttp`,
  `cryptography`, etc. from the Hermes venv. A `ModuleNotFoundError` in
  system Python does NOT mean the adapter is broken.
- **QR codes expire.** iLink QR codes last ~8 minutes with auto-refresh
  (up to 3 times). If the user is slow, re-run the login flow.
- **Gateway must stay running.** On SSH servers, enable linger:
  `sudo loginctl enable-linger $USER`. On WSL2, ensure `systemd=true`
  in `/etc/wsl.conf`.
- **Check logs on failure:** `~/.hermes/logs/gateway.log`.

## Platform References

- **WeChat (Weixin):** `references/weixin-ilink.md` — iLink Bot API QR
  login, credential flow, env var list, driver script pattern.
