from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.application.artifacts.document_part_edits import DocumentEditRefused, PartEdit
from src.application.artifacts.document_schema import get_document_schema, get_document_subdirectory
from src.application.artifacts.query import ArtifactRepository
from src.application.document_links import id_links_expanded, relocated_links
from src.application.identifier_allocator import get_default_allocator
from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.config.repo_paths import DOCS
from src.domain.repository.groups import UNCATEGORIZED
from src.infrastructure.atomic_file import write_atomic

from ._artifact_deduplication import extract_friendly_slug, get_repository, validate_document_unique
from ._document_group_move import _doc_dir, _resolve_document_group_path, commit_document_move
from ._document_part_edit import (
    DocumentPartWriteResult,
    artifact_paths,
    edit_part,
    read_as_stored,
    with_frontmatter,
)
from ._document_placeholder import _build_placeholder_body, _declared_tables, _validate_section_templates
from ._document_text import (
    _MANAGED_DOC_FM_KEYS,
    REFERENCES_HEADING,
    DocumentNotFoundError,
    _document_frontmatter_yaml,
    _dump_yaml_text,
    _format_document_markdown,
    _resolve_document_path,
    _split_document_frontmatter,
    _verification_to_document_dict,
    render_references,
)
from .boundary import assert_engagement_write_root, modification_stamp
from .coerce import as_optional_str_list
from .enterprise_edit_arguments import Interception, document_change
from .types import WriteResult
from .verify import document_write_allowed, verify_content_in_temp_path


def _generate_document_id(abbreviation: str, title: str) -> str:
    return get_default_allocator().allocate(prefix=abbreviation, name_hint=title)


def create_document(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    doc_type: str,
    title: str,
    body: str | None,
    keywords: list[str] | None,
    extra_frontmatter: dict[str, object] | None,
    artifact_id: str | None,
    version: str,
    status: str,
    last_updated: str | None,
    dry_run: bool,
    group: str = UNCATEGORIZED,
    references: list[Path] | None = None,
) -> WriteResult:
    """*references* are model files this document points at, rendered as a `References` section.

    Data rather than a mode: an empty list and `None` mean the same thing, and the section is simply
    absent. It is the writer's job because the hrefs are relative to the document's own path, which
    only this function knows before the file exists.
    """
    assert_engagement_write_root(repo_root)

    schema = get_document_schema(repo_root, doc_type)
    if schema is None:
        raise ValueError(f"Unknown doc-type: {doc_type!r}. No schema found at .arch-repo/documents/{doc_type}.json")

    abbreviation: str = schema.get("abbreviation") or doc_type.upper()
    doc_subdirectory = get_document_subdirectory(schema, doc_type)
    required_sections: list[str] = schema.get("required_sections") or []
    sections_raw = schema.get("sections")
    sections: list[object] = list(sections_raw) if isinstance(sections_raw, list) else list(required_sections)

    section_templates_raw = schema.get("section_templates")
    section_templates: dict[str, str] | None = None
    if section_templates_raw is not None:
        _validate_section_templates(section_templates_raw, required_sections, doc_type)
        section_templates = section_templates_raw  # type: ignore[assignment]

    last = last_updated or modification_stamp()
    doc_id = artifact_id or _generate_document_id(abbreviation, title)
    doc_dir = _doc_dir(repo_root, doc_subdirectory, group)
    path = doc_dir / f"{doc_id}.md"

    friendly_slug = extract_friendly_slug(doc_id)
    repo = get_repository(repo_root)
    try:
        validate_document_unique(repo, doc_type, friendly_slug)
    except ValueError as e:
        # Report validation error in preview/dry_run
        error_msg = str(e)
        return WriteResult(
            wrote=False,
            path=path,
            artifact_id=doc_id,
            content=None,
            warnings=[],
            verification={
                "valid": False,
                "issues": [
                    {
                        "severity": "error",
                        "code": "duplicate_artifact",
                        "message": error_msg,
                        "location": None,
                    }
                ],
            },
        )

    actual_body = (
        id_links_expanded(body, written_to=doc_dir, path_of=artifact_paths(repo_root, verifier.registry))
        if body
        else _build_placeholder_body(sections, section_templates, _declared_tables(repo_root, doc_type))
    )
    actual_body = actual_body.rstrip() + render_references(path, references or [])
    content = _format_document_markdown(
        artifact_id=doc_id,
        doc_type=doc_type,
        title=title,
        status=status,
        version=version,
        last_updated=last,
        keywords=keywords,
        extra_frontmatter=extra_frontmatter,
        body=actual_body,
    )

    preview_res = verify_content_in_temp_path(
        verifier=verifier,
        file_type="document",
        desired_name=path.relative_to(repo_root / DOCS).as_posix(),
        content=content,
        support_repo_root=repo_root,
    )
    verification = _verification_to_document_dict(path, preview_res)

    if dry_run or not document_write_allowed(preview_res):
        return WriteResult(
            wrote=False,
            path=path,
            artifact_id=doc_id,
            content=content,
            warnings=[],
            verification=verification,
        )

    if not dry_run:
        write_atomic(path, content)
        clear_repo_caches(path)

    return WriteResult(
        wrote=True,
        path=path,
        artifact_id=doc_id,
        content=None,
        warnings=[],
        verification=verification,
    )


def _assert_a_part_can_be_edited(
    docs_root: Path, artifact_id: str, *, body: str | None, registry: ArtifactRegistry | None
) -> None:
    """A part edit is made on a file this repository stores, and beside no replacement of the whole."""
    if body is not None:
        raise DocumentEditRefused(
            "The edit states a whole body and a part of it. Send the body to replace it whole, or the "
            "section, text or rows to change it in part."
        )
    held_elsewhere = registry is not None and registry.find_file_by_id(artifact_id) is not None
    if _resolve_document_path(docs_root, artifact_id) is None and held_elsewhere:
        raise DocumentEditRefused(
            f"'{artifact_id}' is not a document this repository stores, so there is no file to edit in part. "
            "A change to enterprise-owned content is recorded from the document's whole body."
        )


def edit_document(
    *,
    assert_write_root: Callable[[Path], None],
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    title: str | None,
    body: str | None,
    keywords: list[str] | None,
    extra_frontmatter: dict[str, object] | None,
    status: str | None,
    version: str | None,
    last_updated: str | None,
    group: str | None = None,
    registry: ArtifactRegistry | None = None,
    repo: ArtifactRepository | None = None,
    part: PartEdit | None = None,
    dry_run: bool,
) -> WriteResult:
    """Edit a document, or — where it is a reference to a promoted one — record a change to it.

    *part* edits one section, one text or rows of one table of the body and leaves the rest of the
    stored file byte for byte; *body* replaces the body whole. A call states one or neither.
    """
    assert_write_root(repo_root)
    docs_root = repo_root / DOCS
    if part is not None:
        _assert_a_part_can_be_edited(docs_root, artifact_id, body=body, registry=registry)

    if part is None and (recorded := document_change(
        into=Interception(registry, verifier, clear_repo_caches, repo, repo_root, artifact_id, dry_run),
        title=title, body=body, keywords=keywords, extra_frontmatter=extra_frontmatter, status=status,
        version=version, last_updated=last_updated, group=group,
    )) is not None:
        return recorded

    path = _resolve_document_path(docs_root, artifact_id)
    if path is None:
        raise DocumentNotFoundError(f"Document '{artifact_id}' not found under {docs_root}")

    fm, existing_body = _split_document_frontmatter(path.read_text(encoding="utf-8"), path)
    states_a_field = any(given is not None for given in (title, status, version, keywords)) or bool(extra_frontmatter)
    path_of = artifact_paths(repo_root, registry)
    edited = (
        edit_part(read_as_stored(path), part, repo_root=repo_root, doc_type=str(fm.get("doc-type", "")),
                  doc_path=path, path_of=path_of)
        if part is not None
        else None
    )
    fm.update({k: v for k, v in {"title": title, "status": status, "version": version, "keywords": keywords}.items()
               if v is not None})
    fm["last-updated"] = last_updated if last_updated is not None else modification_stamp()
    if extra_frontmatter:
        fm.update(extra_frontmatter)

    target_path = _resolve_document_group_path(
        repo_root=repo_root, current_path=path, doc_type=str(fm.get("doc-type", "")), group=group
    )
    moved = target_path != path

    frontmatter: dict[str, Any] = {
        "artifact_id": str(fm.get("artifact-id", artifact_id)),
        "doc_type": str(fm.get("doc-type", "")),
        "title": str(fm.get("title", "")),
        "status": str(fm.get("status", "draft")),
        "version": str(fm.get("version", "")),
        "last_updated": str(fm.get("last-updated", modification_stamp())),
        "keywords": as_optional_str_list(fm.get("keywords")),
        "extra_frontmatter": {k: v for k, v in fm.items() if k not in _MANAGED_DOC_FM_KEYS},
    }

    def _relocated(text: str) -> str:
        # A body is read where the document is and written where it is going. A collection sits
        # one directory deeper than the doc-type's own, so carried across unchanged every relative
        # link in it resolved one level short. A body sent with the move is read the same way: it
        # is an edit of the document as it stands, which is what the GUI's save sends.
        return relocated_links(text, read_from=path.parent, written_to=target_path.parent, moves={path: target_path})

    content = (
        with_frontmatter(
            edited.content,
            stamp_line=_dump_yaml_text({"last-updated": frontmatter["last_updated"]}),
            whole_block=_document_frontmatter_yaml(**frontmatter) if states_a_field else None,
            relocated=_relocated,
        )
        if edited is not None
        else _format_document_markdown(
            **frontmatter,
            body=_relocated(
                id_links_expanded(body, written_to=path.parent, path_of=path_of) if body is not None else existing_body
            ),
        )
    )

    relative_path = target_path.relative_to(repo_root / DOCS).as_posix()
    preview_res = verify_content_in_temp_path(
        verifier=verifier,
        file_type="document",
        desired_name=relative_path,
        content=content,
        support_repo_root=repo_root,
    )
    verification = _verification_to_document_dict(target_path, preview_res)
    warnings = [f"Will move document to group '{group}': {target_path}"] if moved and dry_run else []

    added_row_ids = list(edited.added_row_ids) if edited is not None else []
    if dry_run or not document_write_allowed(preview_res):
        return DocumentPartWriteResult(
            wrote=False, path=target_path, artifact_id=artifact_id, content=content,
            warnings=warnings, verification=verification, added_row_ids=added_row_ids,
        )

    if moved:
        warnings.extend(commit_document_move(
            repo_root=repo_root, old_path=path, new_path=target_path, content=content,
            group=group, clear_repo_caches=clear_repo_caches,
        ))
    else:
        write_atomic(target_path, content)
    clear_repo_caches(target_path)
    return DocumentPartWriteResult(
        wrote=True, path=target_path, artifact_id=artifact_id, content=None,
        warnings=warnings, verification=verification, added_row_ids=added_row_ids,
    )


def delete_document(
    *,
    repo_root: Path,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    dry_run: bool,
    verifier: ArtifactVerifier | None = None,
) -> WriteResult:
    assert_engagement_write_root(repo_root)

    docs_root = repo_root / DOCS
    path = None
    if verifier is not None and verifier.registry is not None:
        path = verifier.registry.find_file_by_id(artifact_id)
    if path is None:
        path = _resolve_document_path(docs_root, artifact_id)
    if path is None:
        raise DocumentNotFoundError(f"Document '{artifact_id}' not found under {docs_root}")

    if not dry_run:
        path.unlink()
        clear_repo_caches(path)

    return WriteResult(
        wrote=not dry_run,
        path=path,
        artifact_id=artifact_id,
        content=None,
        warnings=[],
        verification={"valid": True, "issues": []},
    )


__all__ = [
    "REFERENCES_HEADING",
    "DocumentNotFoundError",
    "_build_placeholder_body",
    "_doc_dir",
    "_dump_yaml_text",
    "_format_document_markdown",
    "_resolve_document_group_path",
    "_validate_section_templates",
    "create_document",
    "delete_document",
    "edit_document",
    "render_references",
]
