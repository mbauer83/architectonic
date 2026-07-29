"""write_tools.py — re-exports all MCP write tool functions and registers them.

Logic lives in src/infrastructure/mcp/artifact_mcp/write/*.
"""

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.infrastructure.mcp.artifact_mcp.admin_tools import artifact_admin_reindex
from src.infrastructure.mcp.artifact_mcp.bulk_tools import artifact_bulk_delete
from src.infrastructure.mcp.artifact_mcp.write._common import DiagramConnectionInferenceMode, WriteRepoScope
from src.infrastructure.mcp.artifact_mcp.write.connection import artifact_add_connection
from src.infrastructure.mcp.artifact_mcp.write.diagram import artifact_create_diagram, artifact_create_matrix
from src.infrastructure.mcp.artifact_mcp.write.document import (
    artifact_create_document,
    artifact_edit_document,
)
from src.infrastructure.mcp.artifact_mcp.write.entity import (
    artifact_authoring_guidance,
    artifact_create_entity,
    artifact_help,
)
from src.infrastructure.mcp.artifact_mcp.write.group import artifact_group
from src.infrastructure.mcp.artifact_mcp.write.promote import artifact_promote_to_enterprise
from src.infrastructure.mcp.artifact_mcp.write.viewpoint import artifact_viewpoint

__all__ = [
    "DiagramConnectionInferenceMode",
    "WriteRepoScope",
    "artifact_add_connection",
    "artifact_admin_reindex",
    "artifact_authoring_guidance",
    "artifact_bulk_delete",
    "artifact_create_diagram",
    "artifact_create_document",
    "artifact_create_entity",
    "artifact_create_matrix",
    "artifact_edit_document",
    "artifact_group",
    "artifact_help",
    "artifact_promote_to_enterprise",
    "artifact_viewpoint",
]


def register_write_tools(mcp: FastMCP) -> None:
    from src.infrastructure.mcp.artifact_mcp import admin_tools, bulk_tools
    from src.infrastructure.mcp.artifact_mcp.write import (
        connection,
        diagram,
        document,
        entity,
        group,
        promote,
        viewpoint,
    )

    entity.register(mcp)
    connection.register(mcp)
    diagram.register(mcp)
    document.register(mcp)
    promote.register(mcp)
    group.register(mcp)
    viewpoint.register(mcp)
    bulk_tools.register(mcp)
    admin_tools.register_admin_tools(mcp)
