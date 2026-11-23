"""Arrange a diagram from MCP: the layout patch or the layout intents the REST layout routes take, written
the same way — over the stored layout or the diagram's first layout, each entry checked, through the
write queue as one named operation."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer  # type: ignore[import-not-found]

from src.application.repo_path_helpers import resolve_diagram_source_path
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.mcp.artifact_mcp.context import (
    authoritative_callbacks_for,
    resolve_repo_roots,
    roots_key,
    verifier_for,
)
from src.infrastructure.mcp.artifact_mcp.mutation_registration import register_mutation_tool
from src.infrastructure.mcp.tool_annotations import DESTRUCTIVE_LOCAL_WRITE
from src.infrastructure.rendering.layout.diagram_geometry import intents_patch
from src.infrastructure.rendering.layout.diagram_picture import first_layout_of
from src.infrastructure.write.artifact_write.boundary import assert_engagement_write_root
from src.infrastructure.write.artifact_write.diagram_layout_patch import patch_diagram_layout
from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file

ARRANGE_DIAGRAM_DESCRIPTION = """Change a diagram's layout: exactly one of `patch` or `intents`.

`patch`: entries by section (`elements`, `boxes`, `relations`, `z`) and layout key; each entry is null to
remove it, or {value, based_on?} — what it becomes and what you read it as (null for absent). A based_on
that no longer holds is a conflict and nothing is written.

`intents`, applied in order: {intent: "align", keys: [≥2 element keys], edge: left|right|top|bottom|
centre_x|centre_y}, {intent: "distribute", keys: [≥3], axis: x|y}, {intent: "straighten", relations:
[relation keys]}, {intent: "return_to_automatic", keys?: [...]} (no keys: the whole layout). Each compiles
to the patch that states it, checked against the stored layout; the answer includes that patch.

Layout keys are those `GET /api/diagrams/{id}/layout/geometry` names. dry_run defaults to true."""


def artifact_arrange_diagram(
    *,
    artifact_id: str,
    patch: dict[str, dict[str, Any]] | None = None,
    intents: list[dict[str, Any]] | None = None,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, object]:
    if (patch is None) == (intents is None):
        raise ValueError("State exactly one of patch or intents.")
    roots = resolve_repo_roots(repo_scope="engagement", repo_root=repo_root, repo_preset=None, enterprise_root=None)
    root, key = roots[0], roots_key(roots)
    verifier = verifier_for(key, include_registry=True)
    _, clear_repo_caches = authoritative_callbacks_for(roots)
    ontology = process_runtime_catalogs().ontology
    stated: Any = patch
    if intents is not None:
        find = verifier.registry.find_file_by_id if verifier.registry is not None else None
        path = resolve_diagram_source_path(root, artifact_id, find)
        if path is None:
            raise ValueError(f"Diagram '{artifact_id}' not found")
        stated = intents_patch(intents, parse_diagram_file(path), artifact_id, root, ontology)
    result = patch_diagram_layout(
        repo_root=root, verifier=verifier, clear_repo_caches=clear_repo_caches,
        assert_write_root=assert_engagement_write_root, artifact_id=artifact_id, patch=stated,
        first_layout=lambda body, frontmatter: first_layout_of(body, frontmatter, root, ontology),
        dry_run=dry_run,
    )
    write = result.write
    return {
        "artifact_id": write.artifact_id, "wrote": write.wrote, "warnings": list(write.warnings),
        "errors": write.error_messages, "layout": result.layout, "patch": dict(result.patch),
    }


def register_layout_tools(mcp: MCPServer) -> None:
    register_mutation_tool(
        mcp,
        artifact_arrange_diagram,
        name="artifact_arrange_diagram",
        title="Artifact Write: Arrange Diagram",
        description=ARRANGE_DIAGRAM_DESCRIPTION,
        annotations=DESTRUCTIVE_LOCAL_WRITE,
        structured_output=True,
    )
