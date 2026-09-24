"""MCP write tool: add an icon to the repository's library."""

from __future__ import annotations

import base64
import binascii
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
from src.infrastructure.mcp.tool_annotations import LOCAL_WRITE


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
    try:
        content = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError):
        return {"ok": False, "error": "content_base64 is not base64"}
    roots = resolve_repo_roots(repo_scope="engagement", repo_root=repo_root, repo_preset=None, enterprise_root=None)
    mutation_context, clear_repo_caches = authoritative_callbacks_for(roots)
    result = artifact_write_ops.create_icon(
        repo_root=roots[0],
        verifier=verifier_for(roots_key(roots), include_registry=False),
        clear_repo_caches=clear_repo_caches,
        upload=artifact_write_ops.IconUpload(
            content=content, source_format=source_format, name=name, attribution=attribution,
            applies_to=tuple(applies_to or ()), default_style=default_style, tags=tuple(tags or ()),
        ),
        dry_run=dry_run,
    )
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
            "PNG of at most 128 px and 32 KB; an SVG is rebuilt without scripts or references to files "
            "or URLs, and what was removed is listed in warnings. attribution is required: whose mark "
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
