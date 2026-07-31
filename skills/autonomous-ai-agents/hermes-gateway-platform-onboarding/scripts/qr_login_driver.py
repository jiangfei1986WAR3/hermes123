#!/usr/bin/env python3
"""
Generic QR/OAuth login driver for Hermes gateway platform adapters.

Runs an adapter's login coroutine from the Hermes venv (so the adapter + its
deps import correctly) and prints the returned credentials to stdout. Run it in
the BACKGROUND from a tool-call terminal, then poll for the QR URL / result.

Usage:
    <install>/venv/bin/python qr_login_driver.py weixin
    <install>/venv/bin/python qr_login_driver.py <platform> [extra_arg ...]

Adapt PLATFORM_LOGIN for other adapters: map platform name -> (module, func).
Most adapters expose an async `qr_login(hermes_home, ...)` returning a dict of
credentials (token, account_id, base_url, user_id) or None on timeout/failure.

NOTE: this only runs the login helper. It saves the adapter's account JSON but
does NOT write ~/.hermes/.env or set access policy — do that afterward (see
SKILL.md step 3-4).
"""
import asyncio
import importlib
import sys

# Point at the Hermes install so `gateway.*` / `hermes_constants` import.
# Adjust if your install lives elsewhere (e.g. ~/.hermes/hermes-agent).
HERMES_INSTALL = "/usr/local/lib/hermes-agent"
sys.path.insert(0, HERMES_INSTALL)

# platform -> (module under gateway.platforms, login coroutine name)
PLATFORM_LOGIN = {
    "weixin": ("gateway.platforms.weixin", "qr_login"),
    # add more, e.g.:
    # "whatsapp": ("plugins.platforms.whatsapp.adapter", "qr_login"),
}


async def main(platform: str, extra: list) -> None:
    if platform not in PLATFORM_LOGIN:
        print(f">>> UNKNOWN_PLATFORM {platform}; known: {list(PLATFORM_LOGIN)}")
        return
    mod_name, fn_name = PLATFORM_LOGIN[platform]
    print(f">>> importing {mod_name}.{fn_name} ...", flush=True)
    mod = importlib.import_module(mod_name)
    login = getattr(mod, fn_name)

    from hermes_constants import get_hermes_home

    print(">>> requesting login / QR ...", flush=True)
    creds = await login(str(get_hermes_home()))
    if creds:
        print("\n>>> LOGIN_SUCCESS", flush=True)
        for k, v in creds.items():
            # mask long secrets in logs; the account JSON still holds the full value
            shown = v if len(str(v)) <= 24 else f"{v[:12]}…({len(str(v))} chars)"
            print(f">>> {k}={shown}", flush=True)
    else:
        print("\n>>> LOGIN_FAILED_OR_TIMEOUT", flush=True)


if __name__ == "__main__":
    argv = sys.argv[1:]
    if not argv:
        print("usage: qr_login_driver.py <platform> [args...]")
        sys.exit(2)
    try:
        asyncio.run(main(argv[0], argv[1:]))
    except KeyboardInterrupt:
        print("\n>>> CANCELLED", flush=True)
