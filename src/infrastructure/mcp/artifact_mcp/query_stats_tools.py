from typing import Literal

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.infrastructure.mcp.artifact_mcp.context import RepoScope, repo_cached, resolve_repo_roots, roots_key
from src.infrastructure.mcp.artifact_mcp.tool_annotations import READ_ONLY


def _include_flags(
    include_record_types: list[Literal["entities", "connections", "diagrams", "documents"]] | None,
) -> tuple[bool, bool, bool]:
    selected = set(include_record_types or ["entities", "connections", "diagrams", "documents"])
    return (
        "connections" in selected,
        "diagrams" in selected,
        "documents" in selected,
    )


def register_query_stats_tools(mcp: FastMCP) -> None:
    @mcp.tool(
        name="artifact_query_stats",
        title="Artifact Query: Stats",
        description=(
            "Return model statistics: total entity/connection/diagram counts and breakdowns "
            "by domain, connection type, and group. Use this first to confirm the server is "
            "pointed at the expected repo. "
            "Pass group_by='artifact_type'|'diagram_type'|'domain'|'group' to get a filtered "
            "count breakdown instead of the default summary. "
            "group_by='group' returns per-group counts for each artifact family."
            "\n\nRepo selection: repo_scope defaults to both (engagement + enterprise)."
        ),
        annotations=READ_ONLY,
        structured_output=True,
    )
    def artifact_query_stats(
        *,
        group_by: Literal["artifact_type", "diagram_type", "domain", "group"] | None = None,
        artifact_type: str | list[str] | None = None,
        domain: str | list[str] | None = None,
        status: str | list[str] | None = None,
        include_record_types: list[Literal["entities", "connections", "diagrams", "documents"]] | None = None,
        repo_root: str | None = None,
        repo_scope: RepoScope = "both",
    ) -> dict[str, object]:
        roots = resolve_repo_roots(
            repo_scope=repo_scope,
            repo_root=repo_root,
            repo_preset=None,
            enterprise_root=None,
        )
        key = roots_key(roots)
        repo = repo_cached(key)
        if group_by is not None:
            include_connections, include_diagrams, include_documents = _include_flags(include_record_types)
            counts = repo.count_artifacts_by(
                group_by,
                artifact_type=artifact_type,
                domain=domain,
                status=status,
                include_connections=include_connections,
                include_diagrams=include_diagrams,
            )
            if not include_documents and group_by == "artifact_type":
                counts.pop("document", None)
            return {
                "repo_roots": [str(p) for p in roots],
                "repo_scope": repo_scope,
                "group_by": group_by,
                "counts": counts,
            }
        stats = repo.stats()
        stats["repo_roots"] = [str(p) for p in roots]
        stats["repo_scope"] = repo_scope
        return stats
