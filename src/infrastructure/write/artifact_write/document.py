from collections.abc import Callable
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from src.application.artifacts.document_schema import get_document_schema, get_document_subdirectory
from src.application.identifier_allocator import get_default_allocator
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.config.repo_paths import DOCS
from src.domain.artifact_id import stable_id
from src.domain.repository.groups import UNCATEGORIZED
from src.infrastructure.atomic_file import write_atomic

from ._artifact_deduplication import extract_friendly_slug, get_repository, validate_document_unique
from ._document_group_move import _doc_dir, _resolve_document_group_path
from ._document_placeholder import _build_placeholder_body, _validate_section_templates
from .boundary import assert_engagement_write_root, modification_stamp
from .coerce import as_optional_str_list
from .file_transaction import FileChange, commit_file_changes
from .types import WriteResult
from .verify import verify_content_in_temp_path


def _dump_yaml_text(data: object) -> str:
    dumped = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    if not isinstance(dumped, str):
        raise TypeError("yaml.dump returned non-string output")
    return dumped.rstrip()


def _generate_document_id(abbreviation: str, title: str) -> str:
    return get_default_allocator().allocate(prefix=abbreviation, name_hint=title)


def _format_document_markdown(
    *,
    artifact_id: str,
    doc_type: str,
    title: str,
    status: str,
    version: str,
    last_updated: str,
    keywords: list[str] | None,
    extra_frontmatter: dict[str, object] | None,
    body: str,
) -> str:
    fm: dict[str, object] = {
        "artifact-id": artifact_id,
        "artifact-type": "document",
        "doc-type": doc_type,
        "title": title,
        "status": status,
        "version": version,
        "last-updated": last_updated,
    }
    if keywords:
        fm["keywords"] = keywords
    if extra_frontmatter:
        fm.update({k: v for k, v in extra_frontmatter.items() if k not in fm})
    frontmatter = _dump_yaml_text(fm)
    return f"---\n{frontmatter}\n---\n\n{body.strip()}\n"


def _verification_to_document_dict(path: Path, res) -> dict[str, object]:
    return {
        "path": str(path),
        "file_type": "document",
        "valid": res.valid,
        "issues": [
            {"severity": i.severity, "code": i.code, "message": i.message, "location": i.location} for i in res.issues
        ],
    }


def _document_write_allowed(res) -> bool:
    return res.valid and not res.issues


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
) -> WriteResult:
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

    actual_body = body or _build_placeholder_body(sections, section_templates)
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

    if dry_run or not _document_write_allowed(preview_res):
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


_MANAGED_DOC_FM_KEYS = frozenset(
    {"artifact-id", "artifact-type", "doc-type", "title", "status", "version", "last-updated", "keywords"}
)


def _split_document_frontmatter(raw: str, path: Path) -> tuple[dict[str, object], str]:
    """Split a document's raw text into its parsed frontmatter mapping and body."""
    if not raw.startswith("---"):
        raise ValueError(f"Document at {path} has no YAML frontmatter")
    end = raw.find("\n---", 3)
    if end == -1:
        raise ValueError(f"Document at {path} has malformed YAML frontmatter")
    fm: dict[str, object] = yaml.safe_load(raw[3:end].strip()) or {}
    return fm, raw[end + 4 :].lstrip("\n")


def _resolve_document_path(docs_root: Path, artifact_id: str) -> Path | None:
    """Locate a document by filename stem (the artifact id), group subdirectory included.

    Documents have no registry-backed lookup, so this mirrors
    ``diagram_delete._find_diagram_file``'s own disk-scan short-id tolerance: an exact
    filename match wins; otherwise a short (rename-stable) id is accepted if exactly one
    file matches it (ambiguous short ids report not-found, same fail-safe convention as
    ``_MemStore.canonical_id``).
    """
    if not docs_root.exists():
        return None
    short = stable_id(artifact_id)
    short_matches: list[Path] = []
    for path in docs_root.rglob("*.md"):
        if path.stem == artifact_id:
            return path
        if stable_id(path.stem) == short:
            short_matches.append(path)
    return short_matches[0] if len(short_matches) == 1 else None


def edit_document(
    *,
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
    dry_run: bool,
) -> WriteResult:
    assert_engagement_write_root(repo_root)

    docs_root = repo_root / DOCS
    path = _resolve_document_path(docs_root, artifact_id)
    if path is None:
        raise ValueError(f"Document '{artifact_id}' not found under {docs_root}")

    fm, existing_body = _split_document_frontmatter(path.read_text(encoding="utf-8"), path)
    fm.update({k: v for k, v in {"title": title, "status": status, "version": version, "keywords": keywords}.items()
               if v is not None})
    fm["last-updated"] = last_updated if last_updated is not None else modification_stamp()
    if extra_frontmatter:
        fm.update(extra_frontmatter)

    content = _format_document_markdown(
        artifact_id=str(fm.get("artifact-id", artifact_id)),
        doc_type=str(fm.get("doc-type", "")),
        title=str(fm.get("title", "")),
        status=str(fm.get("status", "draft")),
        version=str(fm.get("version", "")),
        last_updated=str(fm.get("last-updated", modification_stamp())),
        keywords=as_optional_str_list(fm.get("keywords")),
        extra_frontmatter={k: v for k, v in fm.items() if k not in _MANAGED_DOC_FM_KEYS},
        body=body if body is not None else existing_body,
    )

    target_path = _resolve_document_group_path(
        repo_root=repo_root, current_path=path, doc_type=str(fm.get("doc-type", "")), group=group
    )
    moved = target_path != path

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

    if dry_run or not _document_write_allowed(preview_res):
        return WriteResult(
            wrote=False, path=target_path, artifact_id=artifact_id, content=content,
            warnings=warnings, verification=verification,
        )

    if moved:
        # Writing the new file and unlinking the old are one change: a crash between them
        # leaves the document present in both groups, which parses and resolves cleanly and
        # so is reported by nothing.
        commit_file_changes(
            repo_root=repo_root,
            changes=[
                FileChange(path=target_path, content=content),
                FileChange(path=path, content=None),
            ],
            rebuild_index=lambda: None,
            label="document-move",
        )
        clear_repo_caches(path)
        warnings.append(f"Moved document to group '{group}': {target_path}")
    else:
        write_atomic(target_path, content)
    clear_repo_caches(target_path)
    return WriteResult(
        wrote=True, path=target_path, artifact_id=artifact_id, content=None,
        warnings=warnings, verification=verification,
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
        raise ValueError(f"Document '{artifact_id}' not found under {docs_root}")

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
