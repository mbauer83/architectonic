"""Whether this backend may listen on an address other hosts can reach.

The backend has no authentication of its own: whoever reaches its port can read and write the
repositories it serves, and unlock the confidential store. On the loopback interface only this machine
can reach it. Anywhere else, the deployment must supply the access boundary itself — a VPN, a firewall,
an authenticating reverse proxy — and it has to say so. A non-loopback bind is refused unless the
operator opts in, by the flag or by the setting, and the refusal names both.

A container is the ordinary case for opting in: it must listen on all of its own interfaces for a
published port to reach it, and what is exposed is then decided by where the port is published.
"""

from __future__ import annotations

import ipaddress

#: The command-line opt-in.
REMOTE_OPT_IN_FLAG = "--allow-remote-without-auth"
#: The same opt-in in `config/settings.yaml`.
REMOTE_OPT_IN_SETTING = "backend.allow_remote_without_auth"

_LOOPBACK_NAMES = frozenset({"localhost"})


def is_loopback(host: str) -> bool:
    """True when `host` names only this machine: `localhost`, or a loopback address in either family."""
    candidate = host.strip().lower()
    if candidate in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(candidate.strip("[]")).is_loopback
    except ValueError:
        return False


def bind_refusal(host: str, *, opted_in: bool) -> str | None:
    """Why the backend must not listen on `host`, or None when it may."""
    if opted_in or is_loopback(host):
        return None
    return (
        f"refusing to listen on {host!r}: the backend has no authentication, so any host that reaches "
        "this address could read and change the repositories it serves. Listen on 127.0.0.1, or put "
        f"an access boundary in front of it (VPN, firewall, authenticating proxy) and opt in with "
        f"{REMOTE_OPT_IN_FLAG} or `{REMOTE_OPT_IN_SETTING}: true` in config/settings.yaml."
    )
