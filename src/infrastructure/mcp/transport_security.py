"""The MCP mounts' DNS-rebinding settings, derived from the application's one host list.

The allowed `Host` values are not configured here: they are `src.config.allowed_hosts`, which the
whole application checks before a request reaches any mount. The SDK's own check is kept, fed the
same list, so a mount served without that guard in front of it still refuses what the application
would. `*` in that list turns both off together.

Origins are MCP's alone (browsers do not call the MCP mounts): ``ARCH_MCP_ALLOWED_ORIGINS`` is a
comma-separated list of Origin values added to the loopback ones (e.g. ``https://arch.internal:*``).
"""

from __future__ import annotations

import os

from mcp.server.transport_security import TransportSecuritySettings

from src.config.allowed_hosts import allowed_hosts

_LOCALHOST_ORIGINS = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def build_transport_security() -> TransportSecuritySettings:
    """The SDK's settings for the configured host list and origins."""
    hosts = allowed_hosts()
    if not hosts.checked:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts.as_exact_and_wildcard(),
        allowed_origins=_LOCALHOST_ORIGINS + _split(os.getenv("ARCH_MCP_ALLOWED_ORIGINS", "")),
    )
