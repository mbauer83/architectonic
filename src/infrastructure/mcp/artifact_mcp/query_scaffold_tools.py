"""artifact_diagram_scaffold MCP tool."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.infrastructure.mcp.artifact_mcp._diagram_scaffold import build_diagram_scaffold
from src.infrastructure.mcp.artifact_mcp.context import RepoScope
from src.infrastructure.mcp.artifact_mcp.tool_annotations import READ_ONLY


def artifact_diagram_scaffold(
    *,
    entity_ids: list[str],
    diagram_name: str = "Architecture Diagram",
    direction: Literal["top_to_bottom", "left_to_right"] = "top_to_bottom",
    repo_root: str | None = None,
    repo_scope: RepoScope = "both",
) -> dict[str, object]:
    return build_diagram_scaffold(
        entity_ids=entity_ids,
        diagram_name=diagram_name,
        direction=direction,
        repo_root=repo_root,
        repo_scope=repo_scope,
    )


def register_query_scaffold_tools(mcp: FastMCP) -> None:
    mcp.tool(
        name="artifact_diagram_scaffold",
        title="Artifact Query: Diagram Scaffold",
        description=(
            "Generate a ready-to-edit @startuml…@enduml scaffold from a list of entity IDs. "
            "Returns entity declarations, all existing connections between them, "
            "visible domain groupings (for 90° routing), and hidden layout chains. "
            "Pass the returned puml directly to artifact_create_diagram after adjusting layout. "
            "Use direction='left_to_right' for process sequences; "
            "direction='top_to_bottom' (default) for layered cross-domain views."
        ),
        annotations=READ_ONLY,
        structured_output=True,
    )(artifact_diagram_scaffold)
