"""MCP write tools: the repository's icon library — add, edit, replace and delete an icon."""

from __future__ import annotations

from typing import Literal

from mcp.server.mcpserver import MCPServer  # type: ignore[import-not-found]

from src.infrastructure.mcp.artifact_mcp.write._common import (
    _out,
    artifact_write_ops,
    authoritative_callbacks_for,
    resolve_repo_roots,
    roots_key,
    verifier_for,
)
from src.infrastructure.mcp.tool_annotations import DESTRUCTIVE_LOCAL_WRITE, LOCAL_WRITE


def artifact_create_icon(
    *,
    name: str,
    attribution: str,
    content_base64: str,
    source_format: Literal["svg", "png", "jpeg", "webp"],
    applies_to: list[str] | None = None,
    default_style: Literal["badge", "figure"] = "badge",
    tags: list[str] | None = None,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, object]:
    upload = artifact_write_ops.upload_from_base64(
        content_base64, source_format=source_format, name=name, attribution=attribution,
        applies_to=applies_to or (), default_style=default_style, tags=tags or (),
    )
    if isinstance(upload, artifact_write_ops.IconRefused):
        return {"ok": False, "error": upload.reason}
    roots = resolve_repo_roots(repo_scope="engagement", repo_root=repo_root, repo_preset=None, enterprise_root=None)
    mutation_context, clear_repo_caches = authoritative_callbacks_for(roots)
    result = artifact_write_ops.create_icon(
        repo_root=roots[0],
        verifier=verifier_for(roots_key(roots), include_registry=False),
        clear_repo_caches=clear_repo_caches,
        upload=upload,
        dry_run=dry_run,
    )
    if result.wrote and not dry_run:
        mutation_context.finalize()
    return _out(result, dry_run=dry_run)


def artifact_delete_icon(*, artifact_id: str, dry_run: bool = True, repo_root: str | None = None) -> dict[str, object]:
    roots = resolve_repo_roots(repo_scope="engagement", repo_root=repo_root, repo_preset=None, enterprise_root=None)
    mutation_context, clear_repo_caches = authoritative_callbacks_for(roots)
    try:
        result = artifact_write_ops.delete_icon(
            repo_root=roots[0], verifier=verifier_for(roots_key(roots), include_registry=False),
            clear_repo_caches=clear_repo_caches, artifact_id=artifact_id, dry_run=dry_run,
        )
    except (FileNotFoundError, artifact_write_ops.IconInUseError) as exc:
        return {"ok": False, "error": str(exc)}
    if result.wrote and not dry_run:
        mutation_context.finalize()
    return _out(result, dry_run=dry_run)


def artifact_edit_icon(
    *,
    artifact_id: str,
    name: str | None = None,
    attribution: str | None = None,
    applies_to: list[str] | None = None,
    default_style: Literal["badge", "figure"] | None = None,
    tags: list[str] | None = None,
    status: Literal["active", "retired"] | None = None,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, object]:
    roots = resolve_repo_roots(repo_scope="engagement", repo_root=repo_root, repo_preset=None, enterprise_root=None)
    mutation_context, clear_repo_caches = authoritative_callbacks_for(roots)
    try:
        # A changed applies-to is checked against every element showing the icon, through the registry.
        result = artifact_write_ops.edit_icon(
            repo_root=roots[0], verifier=verifier_for(roots_key(roots), include_registry=True),
            clear_repo_caches=clear_repo_caches, artifact_id=artifact_id, name=name, attribution=attribution,
            applies_to=applies_to, default_style=default_style, tags=tags, status=status, dry_run=dry_run,
        )
    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc)}
    if result.wrote and not dry_run:
        mutation_context.finalize()
    return _out(result, dry_run=dry_run)


def artifact_replace_icon(
    *, artifact_id: str, replacement_id: str, dry_run: bool = True, repo_root: str | None = None
) -> dict[str, object]:
    roots = resolve_repo_roots(repo_scope="engagement", repo_root=repo_root, repo_preset=None, enterprise_root=None)
    mutation_context, clear_repo_caches = authoritative_callbacks_for(roots)
    try:
        # It edits diagrams, and a diagram's body is restated through the registry.
        result = artifact_write_ops.replace_icon(
            repo_root=roots[0], verifier=verifier_for(roots_key(roots), include_registry=True),
            clear_repo_caches=clear_repo_caches, artifact_id=artifact_id, replacement_id=replacement_id,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as exc:
        return {"ok": False, "error": str(exc)}
    if result.wrote and not dry_run:
        mutation_context.finalize()
    return _out(result, dry_run=dry_run)


def artifact_share_icon(
    *,
    diagram_id: str,
    icon_key: str,
    attribution: str,
    tags: list[str] | None = None,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, object]:
    roots = resolve_repo_roots(repo_scope="engagement", repo_root=repo_root, repo_preset=None, enterprise_root=None)
    mutation_context, clear_repo_caches = authoritative_callbacks_for(roots)
    try:
        # It edits the diagram, and a diagram's body is restated through the registry.
        result = artifact_write_ops.share_icon(
            repo_root=roots[0], verifier=verifier_for(roots_key(roots), include_registry=True),
            clear_repo_caches=clear_repo_caches, diagram_id=diagram_id, icon_key=icon_key,
            attribution=attribution, tags=tags or (), dry_run=dry_run,
        )
    except FileNotFoundError as exc:
        return {"ok": False, "error": str(exc)}
    if result.wrote and not dry_run:
        mutation_context.finalize()
    return _out(result, dry_run=dry_run)


def register(mcp: MCPServer) -> None:
    from src.infrastructure.mcp.artifact_mcp.mutation_registration import register_mutation_tool  # noqa: PLC0415

    register_mutation_tool(
        mcp,
        artifact_create_icon,
        name="artifact_create_icon",
        title="Artifact Write: Create Icon",
        description=(
            "Add an icon to the repository's shared library, for diagrams to show on their elements. "
            "content_base64 is the file (SVG, PNG, JPEG or WebP, at most 1 MB and 4096 px on an edge) "
            "base64-encoded — about 1.4 tokens per byte, so prefer small files. It is normalised to one "
            "PNG at most 128 px high, 384 px wide and 32 KB; an SVG is rebuilt without scripts or "
            "references to files or URLs, and what was removed is listed in warnings. attribution is "
            "required: whose mark "
            "it is and on what terms it is used. applies_to lists the entity types or specializations "
            "the icon may be shown on (empty: any element); a name the product does not know is "
            "refused. A picture the library already holds is refused with the existing icon's id. "
            "default_style is how it shows when a diagram does not say: badge (where the type glyph "
            "sits) or figure (as the element, name beneath). Assign it on a diagram through "
            "diagram_entities.display_icons (per instance) or type_icons (per type or specialization "
            "name). Set dry_run=false to write the file."
        ),
        annotations=LOCAL_WRITE,
        structured_output=True,
    )
    register_mutation_tool(
        mcp,
        artifact_delete_icon,
        name="artifact_delete_icon",
        title="Artifact Write: Delete Icon",
        description=(
            "Delete an icon from this repository's library. Refused while any diagram shows it or any "
            "specialization defaults to it; the refusal names them, so they can be re-pointed or cleared "
            "first. An icon still shown that should no longer be offered is retired instead. Set "
            "dry_run=false to delete the file."
        ),
        annotations=DESTRUCTIVE_LOCAL_WRITE,
        structured_output=True,
    )
    register_mutation_tool(
        mcp,
        artifact_edit_icon,
        name="artifact_edit_icon",
        title="Artifact Write: Edit Icon",
        description=(
            "Change what a library icon says about itself: its name, attribution, the types and "
            "specializations it applies to, its default style, its tags, or its status. An argument left "
            "out keeps its value. status='retired' stops the picker offering the icon while every diagram "
            "showing it still does; 'active' reinstates it. The picture cannot be edited: upload the new "
            "one with artifact_create_icon and move the users to it with artifact_replace_icon. Set "
            "dry_run=false to write."
        ),
        annotations=LOCAL_WRITE,
        structured_output=True,
    )
    register_mutation_tool(
        mcp,
        artifact_replace_icon,
        name="artifact_replace_icon",
        title="Artifact Write: Replace Icon",
        description=(
            "Re-point every diagram showing a library icon at another icon, then delete the first, in one "
            "transaction. The replacement must already be in this library or the enterprise's — upload a "
            "new version with artifact_create_icon first. Each diagram is re-verified; if any would not "
            "verify, nothing changes. Refused while a specialization defaults to the icon. The dry run "
            "lists the diagrams it would re-point. Set dry_run=false to write."
        ),
        annotations=DESTRUCTIVE_LOCAL_WRITE,
        structured_output=True,
    )
    register_mutation_tool(
        mcp,
        artifact_share_icon,
        name="artifact_share_icon",
        title="Artifact Write: Share Icon",
        description=(
            "Move an icon a diagram holds for itself (diagram_entities.icons, named local:<icon_key>) into "
            "this repository's library, and have the diagram name the library icon instead. attribution "
            "says whose mark it is and on what terms it is used. A picture the library already holds is "
            "not added again: the diagram is pointed at that icon. Set dry_run=false to write."
        ),
        annotations=LOCAL_WRITE,
        structured_output=True,
    )
