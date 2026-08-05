"""MCP delete tools: removing an entity or a diagram.

Their own module, not because ``edit_tools`` ran out of room but because deleting is not editing:
these two are the only mutations annotated ``DESTRUCTIVE_LOCAL_WRITE``, and a reader asking what this
server can destroy should not have to read past six ways of changing something in place.
"""

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.infrastructure.mcp.artifact_mcp import edit_tool_descriptions as descriptions
from src.infrastructure.mcp.artifact_mcp.context import (
    authoritative_callbacks_for,
    repo_cached,
    resolve_repo_roots,
    roots_key,
    verifier_for,
)
from src.infrastructure.mcp.artifact_mcp.edit_tools import (
    _finalize_authoritative_write,
    _require_registry,
    _resolve,
)
from src.infrastructure.mcp.artifact_mcp.tool_annotations import DESTRUCTIVE_LOCAL_WRITE
from src.infrastructure.write import artifact_write_ops


def artifact_delete_entity(
    *,
    artifact_id: str,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, object]:
    root, registry, _verifier = _resolve(repo_root, need_registry=True)
    registry = _require_registry(registry)
    mutation_context, clear_repo_caches = authoritative_callbacks_for(root)
    result = artifact_write_ops.delete_entity(
        repo_root=root,
        registry=registry,
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        dry_run=dry_run,
    )
    return _finalize_authoritative_write(dry_run, result, mutation_context)


def artifact_delete_diagram(
    *,
    artifact_id: str,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, object]:
    roots = resolve_repo_roots(repo_scope="engagement", repo_root=repo_root, repo_preset=None, enterprise_root=None)
    key = roots_key(roots)
    root = roots[0]
    from src.application.candidate_repository import committed_repository  # noqa: PLC0415
    verifier = verifier_for(key, include_registry=False)
    committed_repo = committed_repository(repo_cached(key))
    mutation_context, clear_repo_caches = authoritative_callbacks_for(roots)
    result = artifact_write_ops.delete_diagram(
        repo_root=root,
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        dry_run=dry_run,
        verifier=verifier,
        committed_repo=committed_repo,
    )
    return _finalize_authoritative_write(dry_run, result, mutation_context)


def register_delete_tools(mcp: FastMCP) -> None:
    from src.infrastructure.mcp.artifact_mcp.mutation_registration import register_mutation_tool  # noqa: PLC0415

    register_mutation_tool(
        mcp,
        artifact_delete_entity,
        name="artifact_delete_entity",
        title="Artifact Write: Delete Entity",
        description=descriptions.DELETE_ENTITY_DESCRIPTION,
        annotations=DESTRUCTIVE_LOCAL_WRITE,
        structured_output=True,
    )

    register_mutation_tool(
        mcp,
        artifact_delete_diagram,
        name="artifact_delete_diagram",
        title="Artifact Write: Delete Diagram",
        description=descriptions.DELETE_DIAGRAM_DESCRIPTION,
        annotations=DESTRUCTIVE_LOCAL_WRITE,
        structured_output=True,
    )
