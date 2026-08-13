from collections.abc import Callable
from pathlib import Path

from src.application.identifier_allocator import get_default_allocator
from src.application.modeling.artifact_write import format_matrix_markdown, prefix_for_diagram_type
from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.config.repo_paths import DIAGRAM_CATALOG, DIAGRAMS

from ._diagram_group_move import commit_diagram_write
from ._matrix_content import compose_matrix_body
from .boundary import assert_engagement_write_root, modification_stamp
from .coerce import as_optional_str_list
from .parse_existing import parse_matrix_file
from .types import WriteResult


def create_matrix(
    *,
    repo_root: Path,
    registry: ArtifactRegistry,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    name: str,
    matrix_markdown: str,
    artifact_id: str | None,
    keywords: list[str] | None = None,
    version: str = "0.1.0",
    status: str = "draft",
    last_updated: str | None = None,
    infer_entity_ids: bool = True,
    auto_link_entity_ids: bool = True,
    entity_ids: list[str] | None = None,
    from_entity_ids: list[str] | None = None,
    to_entity_ids: list[str] | None = None,
    conn_type_configs: list[dict[str, object]] | None = None,
    combined: bool | None = None,
    tlp: str | None = None,
    group: str | None = None,
    dry_run: bool = True,
) -> WriteResult:
    """Create a new matrix diagram, or upsert an existing one when ``artifact_id`` is given.

    When ``artifact_id`` names an already-existing matrix diagram, its real
    on-disk location is resolved via the registry — honouring any diagram-
    collection group it already lives in — instead of assuming the flat,
    ungrouped path. ``group`` re-homes the file to a different diagram-
    collection slug (moving it there on a successful write).
    """
    assert_engagement_write_root(repo_root)
    existing_path = registry.find_file_by_id(artifact_id) if artifact_id else None
    if existing_path is not None:
        stored = parse_matrix_file(existing_path).frontmatter
        # artifact_id may be the short/stale-slug form that resolved to existing_path above;
        # canonicalize to the file's own recorded id so it isn't written back out truncated.
        effective_id = str(stored.get("artifact-id") or artifact_id)
        # On an upsert, a declaration the caller does not state is preserved rather than dropped.
        # It used to be dropped: the axes are frontmatter the *author* declares and the MCP tool
        # does not even expose, so any agent handing back an edited body — repairing a link, say —
        # silently erased which entities the matrix relates. Restating everything is not something
        # a caller can do through a surface that will not carry it.
        entity_ids = entity_ids if entity_ids is not None else as_optional_str_list(stored.get("entity-ids-used"))
        from_entity_ids = (
            from_entity_ids if from_entity_ids is not None
            else as_optional_str_list(stored.get("from-entity-ids"))
        )
        to_entity_ids = (
            to_entity_ids if to_entity_ids is not None else as_optional_str_list(stored.get("to-entity-ids"))
        )
        keywords = keywords if keywords is not None else as_optional_str_list(stored.get("keywords"))
        stored_conn_types = stored.get("conn-type-configs")
        if conn_type_configs is None and isinstance(stored_conn_types, list):
            conn_type_configs = [row for row in stored_conn_types if isinstance(row, dict)]
        if combined is None and stored.get("combined") is not None:
            combined = bool(stored.get("combined"))
    else:
        effective_id = artifact_id or get_default_allocator().allocate(
            prefix=prefix_for_diagram_type("matrix"), name_hint=name
        )
    current_path = existing_path or (repo_root / DIAGRAM_CATALOG / DIAGRAMS / f"{effective_id}.md")

    last = last_updated or modification_stamp()
    warnings: list[str] = []

    body_markdown = compose_matrix_body(
        repo_root=repo_root,
        registry=registry,
        matrix_markdown=matrix_markdown,
        infer_entity_ids=infer_entity_ids,
        auto_link_entity_ids=auto_link_entity_ids,
    )

    content = format_matrix_markdown(
        artifact_id=effective_id,
        name=name,
        version=version,
        status=status,
        last_updated=last,
        keywords=keywords,
        matrix_markdown=body_markdown,
        entity_ids=entity_ids,
        from_entity_ids=from_entity_ids,
        to_entity_ids=to_entity_ids,
        conn_type_configs=conn_type_configs,
        combined=combined,
    )

    return commit_diagram_write(
        repo_root=repo_root,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        artifact_id=effective_id,
        diagram_path=current_path,
        diagram_type="matrix",
        tlp=tlp,
        group=group,
        content=content,
        warnings=warnings,
        dry_run=dry_run,
        verify_fn=verifier.verify_matrix_diagram_file,
        render=False,
    )


def edit_matrix_metadata(
    *,
    repo_root: Path,
    registry: ArtifactRegistry,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    diagram_path: Path,
    artifact_id: str,
    name: str | None,
    keywords: list[str] | None,
    version: str | None,
    status: str | None,
    tlp: str | None,
    group: str | None,
    dry_run: bool,
) -> WriteResult:
    """Metadata/group-only edit for an existing matrix diagram.

    Preserves the existing table body and structural fields (entity-ids,
    conn-type-configs, combined) verbatim — only frontmatter fields and the
    file's group/location change through this path. To change table content
    itself, call ``create_matrix`` with ``artifact_id`` set (an upsert), or
    edit it via the GUI. ``None`` for ``keywords`` means "leave unchanged";
    there is no way to explicitly clear keywords through this metadata-only path.
    """
    parsed = parse_matrix_file(diagram_path)
    fm = parsed.frontmatter
    raw_conn_type_configs = fm.get("conn-type-configs")
    conn_type_configs = raw_conn_type_configs if isinstance(raw_conn_type_configs, list) else None
    raw_combined = fm.get("combined")
    combined = raw_combined if isinstance(raw_combined, bool) else None
    return create_matrix(
        repo_root=repo_root,
        registry=registry,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        name=name if name is not None else str(fm.get("name", "")),
        matrix_markdown=parsed.matrix_markdown,
        artifact_id=artifact_id,
        keywords=keywords if keywords is not None else as_optional_str_list(fm.get("keywords")),
        version=version if version is not None else str(fm.get("version", "0.1.0")),
        status=status if status is not None else str(fm.get("status", "draft")),
        entity_ids=as_optional_str_list(fm.get("entity-ids")),
        from_entity_ids=as_optional_str_list(fm.get("from-entity-ids")),
        to_entity_ids=as_optional_str_list(fm.get("to-entity-ids")),
        conn_type_configs=conn_type_configs,
        combined=combined,
        infer_entity_ids=False,
        auto_link_entity_ids=False,
        tlp=tlp,
        group=group,
        dry_run=dry_run,
    )
