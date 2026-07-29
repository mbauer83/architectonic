from __future__ import annotations

from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.domain.artifact_id import parse_entity_id
from src.infrastructure.artifact_index import shared_artifact_index
from src.infrastructure.mcp.artifact_mcp.context import resolve_repo_root, sync_refresh_for_roots
from src.infrastructure.mcp.artifact_mcp.tool_annotations import LOCAL_WRITE

ReindexScope = Literal["full", "entity"]


def artifact_admin_reindex(
    *,
    scope: ReindexScope = "full",
    short_id: str | None = None,
    repo_root: str | None = None,
) -> dict[str, object]:
    """Rebuild the disk-backed index, globally or for one stable entity ID.

    Registered through the mutation manifest (maintenance intent): the executor
    serializes the rebuild and holds the workspace write gate around it.
    """
    root = resolve_repo_root(repo_root=repo_root, repo_preset=None).resolve()
    return _reindex_locked(scope=scope, short_id=short_id, root=root)


def _reindex_locked(
    *,
    scope: ReindexScope,
    short_id: str | None,
    root: Path,
) -> dict[str, object]:
    if scope == "full":
        if short_id is not None:
            raise ValueError("short_id is only valid when scope='entity'")
        sync_refresh_for_roots(root)
        return {"status": "reindexed", "scope": scope, "repo_root": str(root)}
    if scope != "entity":
        raise ValueError("scope must be 'full' or 'entity'")
    if short_id is None:
        raise ValueError("short_id is required when scope='entity'")

    canonical_short = parse_entity_id(short_id).short
    index = shared_artifact_index(root)
    index.reconcile_short_id(canonical_short)
    candidates = index.find_all_by_stable_id(canonical_short)
    return {
        "status": "reindexed",
        "scope": scope,
        "short_id": canonical_short,
        "repo_root": str(root),
        "candidates": [
            {
                "artifact_id": candidate.artifact_id,
                "path": str(candidate.path),
                "scope": candidate.scope,
            }
            for candidate in candidates
        ],
    }


def register_admin_tools(mcp: FastMCP) -> None:
    from src.infrastructure.mcp.artifact_mcp.mutation_registration import register_mutation_tool  # noqa: PLC0415

    register_mutation_tool(
        mcp,
        artifact_admin_reindex,
        name="artifact_admin_reindex",
        title="Reindex Architecture Repository",
        description=(
            "Rebuild the artifact index from disk. scope='full' refreshes the repository; "
            "scope='entity' reconciles one stable short ID after an out-of-band rename."
        ),
        annotations=LOCAL_WRITE,
        structured_output=True,
    )
