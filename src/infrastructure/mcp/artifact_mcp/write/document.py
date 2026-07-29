"""MCP write tools: document create, edit, delete."""

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

from src.infrastructure.mcp.artifact_mcp.tool_annotations import DESTRUCTIVE_LOCAL_WRITE, LOCAL_WRITE
from src.infrastructure.mcp.artifact_mcp.write._common import (
    _out,
    artifact_write_ops,
    authoritative_callbacks_for,
    resolve_repo_roots,
    roots_key,
    verifier_for,
)


def artifact_create_document(
    *,
    doc_type: str,
    title: str,
    body: str | None = None,
    keywords: list[str] | None = None,
    extra_frontmatter: dict[str, object] | None = None,
    artifact_id: str | None = None,
    version: str = "0.1.0",
    status: str = "draft",
    group: str | None = None,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, object]:
    from src.domain.repository.groups import UNCATEGORIZED  # noqa: PLC0415

    roots = resolve_repo_roots(
        repo_scope="engagement",
        repo_root=repo_root,
        repo_preset=None,
        enterprise_root=None,
    )
    mutation_context, clear_repo_caches = authoritative_callbacks_for(roots)
    result = artifact_write_ops.create_document(
        repo_root=roots[0],
        verifier=verifier_for(roots_key(roots), include_registry=False),
        clear_repo_caches=clear_repo_caches,
        doc_type=doc_type,
        title=title,
        body=body,
        keywords=keywords,
        extra_frontmatter=extra_frontmatter,
        artifact_id=artifact_id,
        version=version,
        status=status,
        last_updated=None,
        dry_run=dry_run,
        group=group or UNCATEGORIZED,
    )
    if result.wrote and not dry_run:
        mutation_context.finalize()
    return _out(result, dry_run=dry_run)


def artifact_edit_document(
    *,
    artifact_id: str,
    title: str | None = None,
    body: str | None = None,
    keywords: list[str] | None = None,
    extra_frontmatter: dict[str, object] | None = None,
    status: str | None = None,
    version: str | None = None,
    group: str | None = None,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, object]:
    roots = resolve_repo_roots(
        repo_scope="engagement",
        repo_root=repo_root,
        repo_preset=None,
        enterprise_root=None,
    )
    mutation_context, clear_repo_caches = authoritative_callbacks_for(roots)
    result = artifact_write_ops.edit_document(
        repo_root=roots[0],
        verifier=verifier_for(roots_key(roots), include_registry=False),
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        title=title,
        body=body,
        keywords=keywords,
        extra_frontmatter=extra_frontmatter,
        status=status,
        version=version,
        last_updated=None,
        group=group,
        dry_run=dry_run,
    )
    if result.wrote and not dry_run:
        mutation_context.finalize()
    return _out(result, dry_run=dry_run)


def artifact_delete_document(
    *,
    artifact_id: str,
    dry_run: bool = True,
    repo_root: str | None = None,
) -> dict[str, object]:
    roots = resolve_repo_roots(
        repo_scope="engagement",
        repo_root=repo_root,
        repo_preset=None,
        enterprise_root=None,
    )
    mutation_context, clear_repo_caches = authoritative_callbacks_for(roots)
    result = artifact_write_ops.delete_document(
        repo_root=roots[0],
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        dry_run=dry_run,
    )
    if result.wrote and not dry_run:
        mutation_context.finalize()
    return _out(result, dry_run=dry_run)


def register(mcp: FastMCP) -> None:
    from src.infrastructure.mcp.artifact_mcp.mutation_registration import register_mutation_tool  # noqa: PLC0415

    register_mutation_tool(
        mcp,
        artifact_create_document,
        name="artifact_create_document",
        title="Artifact Write: Create Document",
        description=(
            "Create a new architecture document (e.g. ADR, RFC). "
            "doc_type must match a schema in .arch-repo/documents/. "
            "body is the full markdown body after the frontmatter; if omitted, "
            "placeholder ## sections are generated from the schema's sections, using each "
            "section template when defined and adding an HTML comment hint for required/suggested "
            "entity links. Place entity links in the section whose schema names the expectation. "
            "Set dry_run=false to write the file."
        ),
        annotations=LOCAL_WRITE,
        structured_output=True,
    )

    register_mutation_tool(
        mcp,
        artifact_edit_document,
        name="artifact_edit_document",
        title="Artifact Write: Edit Document",
        description=(
            "Edit an existing architecture document's frontmatter or body. "
            "All fields are optional — supply only those that should change. "
            "body replaces the entire body when supplied; preserve required ## section headings "
            "and place required entity links in the section named by the document schema. "
            "group (str|None): re-home to a different document-collection slug, moving the file. "
            "Set dry_run=false to write the file. "
            "artifact_id: full (PREFIX@epoch.random.slug) or short (PREFIX@epoch.random) form."
        ),
        annotations=LOCAL_WRITE,
        structured_output=True,
    )

    register_mutation_tool(
        mcp,
        artifact_delete_document,
        name="artifact_delete_document",
        title="Artifact Write: Delete Document",
        description=(
            "Delete a single architecture document. No dependency check — documents aren't "
            "referenced by other verifier rules the way entities/diagrams are, so this deletes "
            "immediately once resolved. For a batch, use artifact_bulk_delete instead; this tool "
            "is the lighter-weight single-item path (no full-repo staging copy). "
            "artifact_id: full (PREFIX@epoch.random.slug) or short (PREFIX@epoch.random) form."
        ),
        annotations=DESTRUCTIVE_LOCAL_WRITE,
        structured_output=True,
    )
