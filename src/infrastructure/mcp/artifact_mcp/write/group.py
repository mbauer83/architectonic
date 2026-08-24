"""MCP write tool: artifact_group — group lifecycle management."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.infrastructure.mcp.artifact_mcp.write._common import resolve_repo_roots
from src.infrastructure.mcp.tool_annotations import DESTRUCTIVE_LOCAL_WRITE


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
                   For model-project, the impact report lists what the cascade would remove.

    confirm — echo the target slug back for destructive/non-empty ops (archive/delete).
    dry_run — applies to every action. True (the default) validates the operation and reports what
              it would do without changing anything; False carries it out. The result always names
              both `dry_run` and `wrote`, so a caller never has to infer which happened.
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
    # Refresh on what was written, not on which action was asked for: a preview changes nothing,
    # and a rename that moved a slug moves every file under it.
    wrote = bool(result.get("wrote"))
    if wrote and (action == "delete" or (action == "rename" and new_slug is not None)):
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
            "dry_run: True (the default) reports what the action would do and changes nothing; "
            "False carries it out. Honoured by every action; the result names dry_run and wrote."
        ),
        annotations=DESTRUCTIVE_LOCAL_WRITE,
        structured_output=True,
    )
