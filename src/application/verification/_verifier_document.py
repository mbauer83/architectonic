"""Verification logic for document (docs/) files."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.verification._verifier_snapshot import RepositorySnapshot

import re
from pathlib import Path

from src.application.artifacts.document_schema import SectionSpec
from src.application.artifacts.reference_terms import (
    LinkedArtifactTypes,
    ReferenceTermVocabulary,
    TermStatus,
    parse_reference_term,
)
from src.application.document_links import resolve_artifact_links
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


def linked_types_in(doc_path: Path, content: str) -> LinkedArtifactTypes:
    """What *content* links, partitioned by vocabulary — the input every required-term rule takes."""
    return LinkedArtifactTypes.from_links(resolve_artifact_links(doc_path, content))


def _verify_required_connections(
    *,
    result: VerificationResult,
    loc: str,
    vocabulary: ReferenceTermVocabulary,
    linked: LinkedArtifactTypes,
    terms: list[str],
    section: str | None = None,
) -> None:
    """One rule for a document's declared terms and for a section's.

    The two differ only in severity and in whether the message names a section: an unknown term is an
    error about the document (E155) and a warning about a section (W157), because a typo in a schema
    should not make somebody's document unwritable, while an unmet requirement is an error either way
    (E155 / E156). A term naming a diagram type no module registers here is neither — it is a
    template asking for something this deployment cannot create, which W159 reports and nothing
    refuses.
    """
    where = f" in section '{section}'" if section else ""
    for term in terms:
        noun = vocabulary.kind_noun(term)
        label = vocabulary.label(term)
        match vocabulary.status(term):
            case TermStatus.UNKNOWN:
                result.issues.append(
                    Issue(
                        Severity.WARNING if section else Severity.ERROR,
                        "W157" if section else "E155",
                        f"Unknown required {noun} connection term{where}: {label} ({term})",
                        loc,
                    )
                )
            case TermStatus.UNREGISTERED if not vocabulary.matches(term, linked):
                result.issues.append(
                    Issue(
                        Severity.WARNING,
                        "W159",
                        f"Required {noun} connection unverifiable{where}: diagram type "
                        f"'{parse_reference_term(term).body}' is not registered in this deployment, "
                        "and nothing links one",
                        loc,
                    )
                )
            case TermStatus.KNOWN if not vocabulary.matches(term, linked):
                result.issues.append(
                    Issue(
                        Severity.ERROR,
                        "E156" if section else "E155",
                        f"Required {noun} connection missing{where}: link at least one {label}",
                        loc,
                    )
                )
            case _:
                continue


def _verify_section_connections(
    *,
    result: VerificationResult,
    loc: str,
    doc_path: Path,
    vocabulary: ReferenceTermVocabulary,
    section_spans: dict[str, str],
    sections: tuple[SectionSpec, ...],
) -> None:
    for section in sections:
        if not section.required_connections or section.name not in section_spans:
            continue
        _verify_required_connections(
            result=result,
            loc=loc,
            vocabulary=vocabulary,
            linked=linked_types_in(doc_path, section_spans[section.name]),
            terms=list(section.required_connections),
            section=section.name,
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
            from src.application.artifacts.document_schema import get_document_schema_object  # noqa: PLC0415

            schema = get_document_schema_object(repo_root, doc_type)
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
                fm_schema = schema.data.get("frontmatter_schema")
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
                body = document_body(content)
                section_spans = document_section_spans(body)
                present = set(section_spans)
                for section_name in schema.required_sections:
                    if section_name not in present:
                        result.issues.append(
                            Issue(
                                Severity.ERROR,
                                "E154",
                                f"Required section '## {section_name}' missing from document",
                                loc,
                            )
                        )
                vocabulary = ReferenceTermVocabulary.for_repository(catalogs=catalogs, repo_root=repo_root)
                if schema.required_connections:
                    _verify_required_connections(
                        result=result,
                        loc=loc,
                        vocabulary=vocabulary,
                        linked=linked_types_in(path, content),
                        terms=list(schema.required_connections),
                    )
                _verify_section_connections(
                    result=result,
                    loc=loc,
                    doc_path=path,
                    vocabulary=vocabulary,
                    section_spans=section_spans,
                    sections=schema.sections,
                )

    check_internal_links(content, path, result, loc)

    check_enum(fm, "status", doc_type_status_enum or VALID_STATUSES, result, loc)
    return result
