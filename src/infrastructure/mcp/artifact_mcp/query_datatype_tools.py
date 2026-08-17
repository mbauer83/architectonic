"""MCP read tool: datatype attribute-type discovery."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.infrastructure.mcp.artifact_mcp.context import (
    RepoScope,
    repo_cached,
    resolve_repo_roots,
    roots_key,
)
from src.infrastructure.mcp.tool_annotations import READ_ONLY


def register_query_datatype_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="artifact_query_datatype_types",
        title="Datatype: Type Catalog",
        description=(
            "List available attribute types for datatype diagrams. "
            "`primitives` is the whole scalar vocabulary — the built-in names, then the label of "
            "every classifier this repository declares `classifier_kind: primitive`. Each entry in "
            "`classifiers` carries its declared `kind` ('class', 'datatype', 'enumeration' or "
            "'primitive'). "
            "Use type_id from the classifiers list when setting "
            "{kind: 'classifier', id: '<type_id>'} attribute types via artifact_edit_diagram; a "
            "custom primitive may also be named as {kind: 'primitive', name: '<label>'}. "
            "Filters: query (name substring), scope ('engagement'|'enterprise'), "
            "kind (the declared classifier kind), "
            "diagram_id (classifiers owned by a specific diagram). "
            "Pagination: pass next_cursor from the previous response as cursor."
        ),
        annotations=READ_ONLY,
        structured_output=True,
    )
    def artifact_query_datatype_types(
        *,
        query: str | None = None,
        scope: str | None = None,
        kind: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
        diagram_id: str | None = None,
        repo_root: str | None = None,
        repo_scope: RepoScope = "both",
    ) -> dict[str, object]:
        from src.diagram_types.datatype import _config as _dt_config  # noqa: PLC0415
        from src.diagram_types.datatype._type_catalog import query_datatype_types  # noqa: PLC0415
        from src.domain.diagrams.diagram_type_config import primitive_types_from_mapping  # noqa: PLC0415

        primitive_names = list(primitive_types_from_mapping(_dt_config))
        roots = resolve_repo_roots(
            repo_scope=repo_scope,
            repo_root=repo_root,
            repo_preset=None,
            enterprise_root=None,
        )
        repo = repo_cached(roots_key(roots))
        result = query_datatype_types(
            repo, primitive_names,
            query=query, scope=scope, kind=kind, limit=limit, cursor=cursor, diagram_id=diagram_id,
        )
        return {
            "generation": result.generation,
            "primitives": result.primitives,
            "classifiers": [
                {
                    "type_id": c.type_id,
                    "label": c.label,
                    "kind": c.kind,
                    "scope": c.scope,
                    "host_diagram_id": c.host_diagram_id,
                }
                for c in result.classifiers
            ],
            "next_cursor": result.next_cursor,
        }
