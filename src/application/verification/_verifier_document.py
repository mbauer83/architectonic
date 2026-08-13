"""Verification logic for document (docs/) files."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.verification._verifier_snapshot import RepositorySnapshot

import re
from dataclasses import dataclass
from pathlib import Path

from src.application.document_links import references_from, strip_anchor
from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.verification.artifact_verifier_parsing import parse_frontmatter, read_file
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.artifact_verifier_rules import check_enum, check_internal_links
from src.application.verification.artifact_verifier_types import (
    VALID_STATUSES,
    Issue,
    Severity,
    VerificationResult,
)
from src.domain.repository.frontmatter import body_after_frontmatter
from src.domain.repository.repo_layout import ARCH_REPO, DOCS, MODEL

_SECTION_HEADING_RE = re.compile(r"^##\s+(.+)$", re.MULTILINE)


def _infer_repo_root_for_document(path: Path) -> Path | None:
    for parent in path.parents:
        if (parent / DOCS).exists() and (parent / ARCH_REPO).exists():
            return parent
        if (parent / DOCS).exists() and (parent / MODEL).exists():
            return parent
    return None


def _doc_repo_root(path: Path, registry: ArtifactRegistry | None) -> Path | None:
    if registry is not None:
        resolved = path.resolve()
        for root in registry.repo_roots:
            try:
                resolved.relative_to(root)
                return root
            except ValueError:
                continue
    return _infer_repo_root_for_document(path)


def document_body(content: str) -> str:
    """Document content with the YAML frontmatter block removed."""
    return body_after_frontmatter(content)


def document_section_spans(body: str) -> dict[str, str]:
    matches = list(_SECTION_HEADING_RE.finditer(body))
    spans: dict[str, list[str]] = {}
    for index, match in enumerate(matches):
        name = match.group(1).strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        spans.setdefault(name, []).append(body[match.start() : end])
    return {name: "\n".join(parts) for name, parts in spans.items()}


@dataclass(frozen=True)
class ResolvedEntityLink:
    """One markdown link in a document that resolves to an entity file."""

    href: str
    artifact_id: str
    artifact_type: str
    name: str


def resolve_entity_links(doc_path: Path, content: str) -> list[ResolvedEntityLink]:
    """Resolve every relative markdown link in *content* to the entity it targets.

    This is the single reading of "which entities does this document link" — the
    required-entity-type-connection rules (E155/E156) and the promotion closure
    gate both consume it, so they cannot drift apart. What a link *is* comes from
    `references_from`, which is the single reading one level down; this one says which of
    those references turn out to be entities.
    """
    links: list[ResolvedEntityLink] = []
    for reference in references_from(content, directory=doc_path.parent):
        if not strip_anchor(reference.href).endswith(".md") or not reference.target.is_file():
            continue
        try:
            target_content = reference.target.read_text(encoding="utf-8")
        except OSError:
            continue
        fm = parse_frontmatter(
            target_content,
            VerificationResult(path=reference.target, file_type="entity"),
            str(reference.target),
        )
        if fm and fm.get("artifact-type"):
            links.append(
                ResolvedEntityLink(
                    href=reference.href,
                    artifact_id=str(fm.get("artifact-id", "")),
                    artifact_type=str(fm["artifact-type"]),
                    name=str(fm.get("name", fm.get("artifact-id", ""))),
                )
            )
    return links


def _linked_entity_types(doc_path: Path, content: str) -> set[str]:
    return {link.artifact_type for link in resolve_entity_links(doc_path, content)}


def _verify_required_entity_type_connections(
    *,
    result: VerificationResult,
    loc: str,
    catalogs: RuntimeCatalogs,
    linked_types: set[str],
    required_entity_types: list[str],
) -> None:
    _oc = catalogs.ontology
    for etype in required_entity_types:
        label = _oc.format_entity_type_term(etype)
        if not _oc.expand_entity_type_term(etype):
            result.issues.append(
                Issue(
                    Severity.ERROR,
                    "E155",
                    f"Unknown required entity-type connection term: {label} ({etype})",
                    loc,
                )
            )
        elif not _oc.entity_type_term_matches(etype, linked_types):
            result.issues.append(
                Issue(
                    Severity.ERROR,
                    "E155",
                    f"Required entity-type connection missing: link at least one {label}",
                    loc,
                )
            )


def _verify_section_entity_type_connections(
    *,
    result: VerificationResult,
    loc: str,
    doc_path: Path,
    catalogs: RuntimeCatalogs,
    section_spans: dict[str, str],
    sections: list[dict],
) -> None:
    _oc = catalogs.ontology
    for section in sections:
        name = str(section.get("name") or "").strip()
        if not name:
            continue
        required_entity_types: list[str] = section.get("required_entity_type_connections") or []
        if not required_entity_types or name not in section_spans:
            continue
        linked_types = _linked_entity_types(doc_path, section_spans[name])
        for etype in required_entity_types:
            label = _oc.format_entity_type_term(etype)
            if not _oc.expand_entity_type_term(etype):
                result.issues.append(
                    Issue(
                        Severity.WARNING,
                        "W157",
                        f"Unknown required entity-type connection term in section '{name}': {label} ({etype})",
                        loc,
                    )
                )
            elif not _oc.entity_type_term_matches(etype, linked_types):
                result.issues.append(
                    Issue(
                        Severity.ERROR,
                        "E156",
                        f"Required entity-type connection missing in section '{name}': link at least one {label}",
                        loc,
                    )
                )


def verify_document(  # noqa: C901
    path: Path,
    *,
    registry: ArtifactRegistry | None,
    catalogs: RuntimeCatalogs,
    snapshot: "RepositorySnapshot | None" = None,
) -> VerificationResult:
    """Verify a document file under docs/."""
    result = VerificationResult(path=path, file_type="document")
    loc = str(path)
    content = read_file(path, result, loc, snapshot=snapshot)
    if content is None:
        return result
    fm = parse_frontmatter(content, result, loc)
    if fm is None:
        return result

    doc_type = str(fm.get("doc-type", "")).strip()
    doc_type_status_enum: frozenset[str] | None = None
    if not doc_type:
        result.issues.append(Issue(Severity.ERROR, "E153", "Missing required frontmatter field 'doc-type'", loc))
    else:
        repo_root = _doc_repo_root(path, registry)
        if repo_root is not None:
            from src.application.artifacts.document_schema import get_document_schema  # noqa: PLC0415

            schema = get_document_schema(repo_root, doc_type)
            if schema is None:
                result.issues.append(
                    Issue(
                        Severity.ERROR,
                        "E153",
                        f"Unknown doc-type '{doc_type}': no schema at .arch-repo/documents/{doc_type}.json",
                        loc,
                    )
                )
            else:
                fm_schema = schema.get("frontmatter_schema")
                if fm_schema:
                    from src.application.artifacts.schema import validate_against_schema  # noqa: PLC0415

                    errors = validate_against_schema(fm, fm_schema)
                    for err in errors:
                        result.issues.append(
                            Issue(Severity.ERROR, "E153", f"Document frontmatter schema violation: {err}", loc)
                        )
                    status_enum = fm_schema.get("properties", {}).get("status", {}).get("enum")
                    if status_enum:
                        doc_type_status_enum = frozenset(str(v) for v in status_enum)
                required_sections: list[str] = schema.get("required_sections") or []
                body = document_body(content)
                section_spans = document_section_spans(body)
                if required_sections:
                    present = set(section_spans)
                    for section in required_sections:
                        if section not in present:
                            result.issues.append(
                                Issue(
                                    Severity.ERROR,
                                    "E154",
                                    f"Required section '## {section}' missing from document",
                                    loc,
                                )
                            )
                required_entity_types: list[str] = schema.get("required_entity_type_connections") or []
                if required_entity_types:
                    linked_types = _linked_entity_types(path, content)
                    _verify_required_entity_type_connections(
                        result=result,
                        loc=loc,
                        catalogs=catalogs,
                        linked_types=linked_types,
                        required_entity_types=required_entity_types,
                    )
                _verify_section_entity_type_connections(
                    result=result,
                    loc=loc,
                    doc_path=path,
                    catalogs=catalogs,
                    section_spans=section_spans,
                    sections=schema.get("sections") or [],
                )

    check_internal_links(content, path, result, loc)

    check_enum(fm, "status", doc_type_status_enum or VALID_STATUSES, result, loc)
    return result
