"""Which `Host` header values this backend answers to — one list for REST, the GUI and MCP alike.

A browser enforces the same-origin policy by name, not by address. A page on an attacker's domain
whose name is re-pointed at 127.0.0.1 (DNS rebinding) is same-origin with itself and can read and
write a loopback backend, unless the backend refuses requests addressed to a name it does not serve.
The MCP SDK refused them on the MCP mounts only; this list is what the whole application checks, and
the MCP transport settings are derived from it rather than configured beside it.

Configuration is the environment variable `ARCH_ALLOWED_HOSTS`: comma-separated entries added to the
loopback names, which are always allowed. An entry is `name`, `name:port`, or `name:*` for any port
(`10.20.20.34:*`, `arch.internal`). The single entry `*` turns the check off, which is only for a
network where nothing untrusted can resolve a name to this backend. `ARCH_MCP_ALLOWED_HOSTS`, the
variable's name while only the MCP mounts read it, is still honoured when the new one is unset.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

ENV_ALLOWED_HOSTS = "ARCH_ALLOWED_HOSTS"
#: The name the same list had while only the MCP mounts read it.
ENV_ALLOWED_HOSTS_FORMER = "ARCH_MCP_ALLOWED_HOSTS"

_ANY_PORT = ":*"
#: Always allowed: a request addressed to this machine by a loopback name.
LOOPBACK_HOSTS: tuple[str, ...] = ("127.0.0.1:*", "localhost:*", "[::1]:*")


def _entry_permits(entry: str, host: str) -> bool:
    if entry.endswith(_ANY_PORT):
        name = entry[: -len(_ANY_PORT)]
        return host == name or host.startswith(f"{name}:")
    return host == entry


@dataclass(frozen=True, slots=True)
class AllowedHosts:
    """The configured list. `entries` is None when the operator turned the check off with `*`."""

    entries: tuple[str, ...] | None

    @property
    def checked(self) -> bool:
        return self.entries is not None

    def permits(self, host: str | None) -> bool:
        """Whether a request whose `Host` header is `host` is addressed to this backend."""
        if self.entries is None:
            return True
        if not host:
            return False
        candidate = host.strip().lower()
        return any(_entry_permits(entry, candidate) for entry in self.entries)

    def as_exact_and_wildcard(self) -> list[str]:
        """The entries in the MCP SDK's spelling, which matches `name:*` only when a port is present."""
        return [
            spelled
            for entry in self.entries or ()
            for spelled in ((entry[: -len(_ANY_PORT)], entry) if entry.endswith(_ANY_PORT) else (entry,))
        ]


def _configured_value() -> str:
    return (os.getenv(ENV_ALLOWED_HOSTS) or os.getenv(ENV_ALLOWED_HOSTS_FORMER) or "").strip()


def allowed_hosts() -> AllowedHosts:
    """The list as configured now: the loopback names, plus whatever the environment adds."""
    value = _configured_value()
    if value == "*":
        return AllowedHosts(entries=None)
    added = tuple(item.strip().lower() for item in value.split(",") if item.strip())
    return AllowedHosts(entries=LOOPBACK_HOSTS + added)
