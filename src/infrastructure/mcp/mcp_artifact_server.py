"""MCP servers exposing artifact tools.

Two separate servers share the same unified backend:
- mcp_read  → /mcp/read  (query + verify tools; safe for read-only agents)
- mcp_write → /mcp/write (create, edit, delete, promote tools)

Tool logic lives in:
- src/infrastructure/mcp/artifact_mcp/ (MCP tool wrappers)
- src/domain/, src/application/ (domain and application logic)
- src/infrastructure/write/artifact_write/ (writer I/O operations)
"""

import os

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.infrastructure.mcp.artifact_mcp import (
    register_edit_tools,
    register_query_tools,
    register_verify_tools,
    register_write_tools,
)
from src.infrastructure.mcp.artifact_mcp.edit_tools import (  # noqa: F401
    artifact_delete_diagram,
    artifact_delete_entity,
    artifact_edit_connection,
    artifact_edit_connection_associations,
    artifact_edit_diagram,
    artifact_edit_entity,
)
from src.infrastructure.mcp.artifact_mcp.name_normalization import install_call_tool_normalizer
from src.infrastructure.mcp.artifact_mcp.verify_tools import (  # noqa: F401
    artifact_verify,
    artifact_verify_all,
    artifact_verify_file,
)
from src.infrastructure.mcp.artifact_mcp.write import sync_ops as _sync_ops

# Re-export tool functions for direct calling in tests.
from src.infrastructure.mcp.artifact_mcp.write_tools import (  # noqa: F401
    artifact_add_connection,
    artifact_authoring_guidance,
    artifact_bulk_delete,
    artifact_create_diagram,
    artifact_create_document,
    artifact_create_entity,
    artifact_create_matrix,
    artifact_edit_document,
    artifact_help,
    artifact_promote_to_enterprise,
    artifact_viewpoint,
)
from src.infrastructure.mcp.transport_security import build_transport_security

_HOST = os.getenv("ARCH_MCP_HOST", "127.0.0.1")
_PORT = int(os.getenv("ARCH_MCP_PORT", "8000"))
_LOG_LEVEL = os.getenv("ARCH_MCP_LOG_LEVEL", "INFO")
_READ_SERVER_NAME = os.getenv("ARCH_MCP_READ_SERVER_NAME", "arch_artifacts_read")
_WRITE_SERVER_NAME = os.getenv("ARCH_MCP_WRITE_SERVER_NAME", "arch_artifacts_write")
_JSON_RESPONSE = os.getenv("ARCH_MCP_JSON_RESPONSE", "0") in {"1", "true", "TRUE", "yes", "YES"}
_STATELESS_HTTP = os.getenv("ARCH_MCP_STATELESS_HTTP", "1") in {"1", "true", "TRUE", "yes", "YES"}

_READ_INSTRUCTIONS = (
    "Architecture repository read-only tools (explore, query + verify). "
    "Safe for read-only contexts and agents without write permissions."
)
_WRITE_INSTRUCTIONS = (
    "Architecture repository write tools (create, edit, delete, promote). "
    "Requires write access to the engagement repository."
)

mcp_read = FastMCP(
    name=_READ_SERVER_NAME,
    instructions=_READ_INSTRUCTIONS,
    host=_HOST,
    port=_PORT,
    streamable_http_path="/mcp/read",
    json_response=_JSON_RESPONSE,
    stateless_http=_STATELESS_HTTP,
    log_level=_LOG_LEVEL,  # type: ignore[arg-type]
    transport_security=build_transport_security(),
)

register_query_tools(mcp_read)
register_verify_tools(mcp_read)
install_call_tool_normalizer(mcp_read)


mcp_write = FastMCP(
    name=_WRITE_SERVER_NAME,
    instructions=_WRITE_INSTRUCTIONS,
    host=_HOST,
    port=_PORT,
    streamable_http_path="/mcp/write",
    json_response=_JSON_RESPONSE,
    stateless_http=_STATELESS_HTTP,
    log_level=_LOG_LEVEL,  # type: ignore[arg-type]
    transport_security=build_transport_security(),
)

register_write_tools(mcp_write)
register_edit_tools(mcp_write)

_sync_ops.register(mcp_write)
# Same dispatch treatment as the read server: incoming tool-name normalization,
# compact YAML responses, and — critically — rejection of unknown parameters
# (otherwise a mistyped arg is silently dropped and the tool runs with defaults).
install_call_tool_normalizer(mcp_write)
