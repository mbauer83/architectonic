"""MCP write tool: artifact_group — group lifecycle management."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.infrastructure.mcp.artifact_mcp.tool_annotations import LOCAL_WRITE
from src.infrastructure.mcp.artifact_mcp.write._common import resolve_repo_roots


def artifact_group(
    *,
    kind: Literal["model-project", "diagram-collection", "document-collection"],
    action: Literal["create", "rename", "archive", "unarchive", "delete"],
    target: str | None = None,
    name: str | None = None,
    new_slug: str | None = None,
    description: str = "",
    order: int = 0,
    confirm: str | None = None,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, object]:
    """Manage group containers (create / rename / archive / unarchive / delete).

    kind — the grouping axis:
      model-project       : groups of entities + connections (cascade delete supported)
      diagram-collection  : groups of diagrams
      document-collection : groups of documents

    action — the lifecycle operation:
      create     : register a new group (target = new slug)
      rename     : change display name (name=) and/or slug (new_slug=); target = existing slug
      archive    : hide from default pickers; typed confirm required when non-empty
      unarchive  : restore archived group to default pickers
      delete     : remove folder + contents; typed confirm required
                   For model-project: two-stage cascade delete via dry_run flag.
                   dry_run=True (default): returns impact report without mutating.
                   dry_run=False: applies deletion after you have reviewed the report.

    confirm — echo the target slug back for destructive/non-empty ops (archive/delete).
    dry_run — for model-project delete only: True returns impact report, False applies.
    """
    from src.infrastructure.write.artifact_write.group_ops import GroupOpError, group_op  # noqa: PLC0415

    roots = resolve_repo_roots(
        repo_scope="engagement",
        repo_root=repo_root,
        repo_preset=None,
        enterprise_root=None,
    )
    repo = roots[0]
    try:
        result = group_op(
            repo,
            axis=kind,
            action=action,
            target=target,
            name=name,
            new_slug=new_slug,
            description=description,
            order=order,
            confirm=confirm,
            dry_run=dry_run,
        )
    except GroupOpError as exc:
        return {"error": str(exc), "action": action, "axis": kind, "target": target}
    live_delete = action == "delete" and not dry_run
    if live_delete or (action == "rename" and new_slug is not None):
        from src.infrastructure.mcp.artifact_mcp.context import enqueue_background_refresh  # noqa: PLC0415
        enqueue_background_refresh([repo], full_refresh=True)
    return result


def register(mcp: FastMCP) -> None:
    from src.infrastructure.mcp.artifact_mcp.mutation_registration import register_mutation_tool  # noqa: PLC0415

    register_mutation_tool(
        mcp,
        artifact_group,
        name="artifact_group",
        title="Artifact Write: Group Lifecycle",
        description=(
            "Manage artifact group containers across all three grouping axes. "
            "kind: 'model-project' | 'diagram-collection' | 'document-collection'. "
            "action: create | rename | archive | unarchive | delete. "
            "target: the group slug (directory name) to act on. "
            "name: display name (for create/rename). "
            "new_slug: new directory name (rename only). "
            "confirm: echo the target slug back for destructive/non-empty ops. "
            "dry_run: for model-project delete — True (default) returns impact report, False applies."
        ),
        annotations=LOCAL_WRITE,
        structured_output=True,
    )
