"""Assurance MCP servers (arch-assurance-read / arch-assurance-write).

Two separate FastMCP servers sharing the same assurance store:
  mcp_assurance_read  → /mcp/assurance-read  (query, verify, guidance)
  mcp_assurance_write → /mcp/assurance-write (create, edit, delete, seal)

Both servers are fail-closed: if the store is not configured or locked,
every tool returns a structured locked error rather than raising.
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.infrastructure.mcp.artifact_mcp.name_normalization import install_call_tool_normalizer
from src.infrastructure.mcp.assurance_mcp.context import get_assurance_context
from src.infrastructure.mcp.assurance_mcp.read_tools import register_read_tools
from src.infrastructure.mcp.assurance_mcp.write_tools import register_write_tools
from src.infrastructure.mcp.transport_security import build_transport_security

_HOST = os.getenv("ARCH_MCP_HOST", "127.0.0.1")
_PORT = int(os.getenv("ARCH_MCP_PORT", "8000"))
_LOG_LEVEL = os.getenv("ARCH_MCP_LOG_LEVEL", "INFO")
_JSON_RESPONSE = os.getenv("ARCH_MCP_JSON_RESPONSE", "0") in {"1", "true", "TRUE"}
_STATELESS = os.getenv("ARCH_MCP_STATELESS_HTTP", "1") in {"1", "true", "TRUE"}

_READ_INSTRUCTIONS = (
    "Assurance read-only tools (STPA/CAST/GRC query, verify, guidance). "
    "Gated: only active when the confidential assurance store is configured and unlocked. "
    "Safe for read-only analyst sessions."
)
_WRITE_INSTRUCTIONS = (
    "Assurance write tools (create, edit, delete, seal baselines). "
    "Requires the confidential assurance store to be unlocked. "
    "Write scope: assurance only — use arch-repo-write for architecture edits."
)

mcp_assurance_read = FastMCP(
    name="arch_assurance_read",
    instructions=_READ_INSTRUCTIONS,
    host=_HOST,
    port=_PORT,
    streamable_http_path="/mcp/assurance-read",
    json_response=_JSON_RESPONSE,
    stateless_http=_STATELESS,
    log_level=_LOG_LEVEL,  # type: ignore[arg-type]
    transport_security=build_transport_security(),
)

mcp_assurance_write = FastMCP(
    name="arch_assurance_write",
    instructions=_WRITE_INSTRUCTIONS,
    host=_HOST,
    port=_PORT,
    streamable_http_path="/mcp/assurance-write",
    json_response=_JSON_RESPONSE,
    stateless_http=_STATELESS,
    log_level=_LOG_LEVEL,  # type: ignore[arg-type]
    transport_security=build_transport_security(),
)

register_read_tools(mcp_assurance_read)
register_write_tools(mcp_assurance_write)

# Uniform dispatch treatment across every MCP server (see mcp_artifact_server):
# tool-name normalization, compact YAML responses for token efficiency, and
# rejection of unknown parameters instead of silently dropping them.
install_call_tool_normalizer(mcp_assurance_read)
install_call_tool_normalizer(mcp_assurance_write)

# Expose the context accessor for test/integration use.
__all__ = ["mcp_assurance_read", "mcp_assurance_write", "get_assurance_context"]
