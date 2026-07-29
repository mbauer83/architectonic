"""Env-driven MCP transport security (DNS-rebinding protection).

The MCP SDK auto-enables DNS-rebinding protection whenever a FastMCP server's
``host`` is localhost, seeding ``allowed_hosts`` with ``127.0.0.1``/``localhost``
only. A server reached over its LAN/VPN address (e.g. ``10.20.20.34:8000``) then
gets ``421 Invalid Host header`` for every MCP client — even though the GUI/REST
surface, which does not pass through this check, works.

This makes the allowlist configurable without weakening the local default:

- ``ARCH_MCP_ALLOWED_HOSTS``   — comma-separated Host values to permit, in
  addition to localhost. Entries may use the SDK's ``host:*`` wildcard-port form
  (e.g. ``10.20.20.34:*``). The literal value ``*`` turns protection OFF (only
  appropriate on a trusted network such as a VPN-only deployment).
- ``ARCH_MCP_ALLOWED_ORIGINS`` — comma-separated Origin values, same form
  (e.g. ``https://arch.internal:*``); only needed for browser-based clients.

When neither is set, returns ``None`` so the SDK keeps its secure localhost
default unchanged.
"""

from __future__ import annotations

import os

from mcp.server.transport_security import TransportSecuritySettings

# Retained so local clients keep working when an explicit allowlist is supplied.
_LOCALHOST_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
_LOCALHOST_ORIGINS = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]


def _split(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def build_transport_security() -> TransportSecuritySettings | None:
    """Construct transport security from env, or None to keep the SDK default."""
    hosts = os.getenv("ARCH_MCP_ALLOWED_HOSTS", "").strip()
    origins = os.getenv("ARCH_MCP_ALLOWED_ORIGINS", "").strip()
    if not hosts and not origins:
        return None
    if hosts == "*":
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_LOCALHOST_HOSTS + _split(hosts),
        allowed_origins=_LOCALHOST_ORIGINS + _split(origins),
    )
