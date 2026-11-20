"""MCP write tools: document create, edit, delete."""

from mcp.server.mcpserver import MCPServer  # type: ignore[import-not-found]
from pydantic import TypeAdapter  # type: ignore[import-not-found]

from src.infrastructure.document_part_wire import (
    RowEditBody,
    SectionEditBody,
    TextReplacementBody,
    stated_part,
    table_row_edits,
)
from src.infrastructure.mcp.artifact_mcp.write._common import (
    _out,
    artifact_write_ops,
    authoritative_callbacks_for,
    registry_cached,
    repo_cached,
    resolve_repo_roots,
    roots_key,
    verifier_for,
)
from src.infrastructure.mcp.tool_annotations import DESTRUCTIVE_LOCAL_WRITE, LOCAL_WRITE
from src.infrastructure.write.artifact_write.boundary import assert_engagement_write_root


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


_ROW_EDITS: TypeAdapter[list[RowEditBody]] = TypeAdapter(list[RowEditBody])


def _shaped[Body: (SectionEditBody, TextReplacementBody)](model: type[Body], sent: object) -> Body | None:
    """The typed body, whether the caller handed over a model or the JSON object behind one.

    The annotation is what publishes the body's fields in the tool's schema. These functions are
    also called directly — by the write queue and by tests — where the object arrives as sent.
    """
    return None if sent is None else model.model_validate(sent)


def artifact_edit_document(
    *,
    artifact_id: str,
    title: str | None = None,
    body: str | None = None,
    section: SectionEditBody | None = None,
    replace: TextReplacementBody | None = None,
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
        assert_write_root=assert_engagement_write_root,
        repo_root=roots[0],
        verifier=verifier_for(roots_key(roots), include_registry=False),
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        # A reference to a promoted document lives in the model tree, not under `docs/`, so this
        # edit needs the registry to recognise one and the repository to record the change in.
        registry=registry_cached(roots_key(roots)),
        repo=repo_cached(roots_key(roots)),
        title=title,
        body=body,
        part=stated_part(_shaped(SectionEditBody, section), _shaped(TextReplacementBody, replace)),
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


def artifact_edit_document_table(
    *,
    artifact_id: str,
    table: str,
    rows: list[RowEditBody],
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
    # The same write as `artifact_edit_document`, stating a part and no field: a row edit is a
    # document edit, verified and gated as one.
    result = artifact_write_ops.edit_document(
        assert_write_root=assert_engagement_write_root,
        repo_root=roots[0],
        verifier=verifier_for(roots_key(roots), include_registry=False),
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        registry=registry_cached(roots_key(roots)),
        repo=repo_cached(roots_key(roots)),
        part=table_row_edits(table, _ROW_EDITS.validate_python(rows)),
        title=None,
        body=None,
        keywords=None,
        extra_frontmatter=None,
        status=None,
        version=None,
        last_updated=None,
        group=None,
        dry_run=dry_run,
    )
    if result.wrote and not dry_run:
        mutation_context.finalize()
    return _out(result, dry_run=dry_run) | {"added_row_ids": list(getattr(result, "added_row_ids", []))}


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


def register(mcp: MCPServer) -> None:
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
            "To change part of the body send section or replace instead of body; the rest of the "
            "stored file is then left byte for byte. "
            "section {heading_path, text}: replace what stands under one heading. heading_path is the "
            "titles from the ## section down to it — ['Decision'], or ['Decision', 'Rationale'] for a "
            "### beneath it; text is what goes under the heading, without the heading line. "
            "replace {find, replacement, expected_matches=1}: replace an exact text of the body, "
            "refused unless it occurs exactly expected_matches times. "
            "A link may be written with an artifact id where its path would go — [label](ADR@…), or "
            "[](ADR@…) to take the artifact's name as the label — and is stored as the relative path; "
            "an id that names no artifact is refused. "
            "For rows of a typed table use artifact_edit_document_table. "
            "group (str|None): re-home to a different document-collection slug, moving the file. "
            "Set dry_run=false to write the file. "
            "artifact_id: full (PREFIX@epoch.random.slug) or short (PREFIX@epoch.random) form."
        ),
        annotations=DESTRUCTIVE_LOCAL_WRITE,
        structured_output=True,
    )

    register_mutation_tool(
        mcp,
        artifact_edit_document_table,
        name="artifact_edit_document_table",
        title="Artifact Write: Edit Document Table",
        description=(
            "Add, change and remove rows of one typed table a document's type declares, leaving "
            "every other line of the document as it is. Read the rows first with "
            "artifact_query_document_tables: a row is addressed by its row_id, and a change or a "
            "removal states the row's values as read in based_on. "
            "rows: a list of {op: 'add', cells}, {op: 'change', row_id, based_on, cells} and "
            "{op: 'remove', row_id, based_on}. cells and based_on map column names to values: the "
            "column's typed value (text, number, true/false, a list), an artifact id or markdown "
            "link for a reference column, a row id for a row column, a list of them where the "
            "column takes several, null to empty a cell. A change names only the cells it changes. "
            "A row that has changed since it was read is refused, naming the row and both values, "
            "and nothing is written — read it again and repeat the edit; changes to other rows are "
            "not affected. An added row takes the table's next id, answered in added_row_ids. "
            "The write is verified as every document write is: a row still being filled in is "
            "written with warnings, a cell that cannot be read as its column's type is refused. "
            "Set dry_run=false to write the file. "
            "artifact_id: full (PREFIX@epoch.random.slug) or short (PREFIX@epoch.random) form."
        ),
        annotations=DESTRUCTIVE_LOCAL_WRITE,
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
