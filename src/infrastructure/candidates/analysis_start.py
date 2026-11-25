"""Starting a stress analysis: its naive candidate and the document naming it, in one write made whole or not
at all. Shared by the HTTP and MCP transports, each binding the document writer to its own verifier.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, TypeAlias

from src.application.modeling.artifact_write import generate_entity_id
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.domain.repository.repo_default_stress_analysis import ANALYSIS_CONTEXT, NAIVE_CANDIDATE, STRESS_ANALYSIS
from src.infrastructure.candidates.repository import KIND, CandidateConflict
from src.infrastructure.candidates.service import CandidateService
from src.infrastructure.write.artifact_write.document import create_document
from src.infrastructure.write.artifact_write.types import WriteResult

#: The analysis document's writer, bound by the transport to its verifier: title, frontmatter, dry run.
DocumentWriter: TypeAlias = Callable[[str, dict[str, object], bool], WriteResult]


def start_analysis(
    service: CandidateService, title: str, naive: Mapping[str, Any], write_document: DocumentWriter, *,
    context: str | None = None,
) -> dict[str, Any]:
    """Start an analysis: its naive architecture and the document naming it, both or neither.

    The document is planned before anything is written, so the refusals a plan can see leave
    nothing behind; a refusal only the write sees takes the naive architecture back with it. The
    naive owns the scope and the diagram it is drawn on; the document names the naive and, where
    given, the *context* the evaluation is made in.
    """
    record = dict(naive)
    record.setdefault("id", generate_entity_id(str(KIND.id_prefix), str(record.get("name") or "")))
    ref = str(record["id"])
    frontmatter: dict[str, object] = {NAIVE_CANDIDATE: ref, **({ANALYSIS_CONTEXT: context} if context else {})}
    _refuse_unwritten(write_document(title, frontmatter, True), wrote=False)
    if service.store.find(ref) is not None:
        raise CandidateConflict(f"{ref} already exists; a naive architecture starts as a new candidate.")
    created = service.create(record)
    try:
        written = write_document(title, frontmatter, False)
        _refuse_unwritten(written, wrote=True)
    except BaseException:
        service.discard(ref)
        raise
    return {"document": written.artifact_id, "naive_candidate": created}


def document_writer(
    repo_root: Path, verifier: ArtifactVerifier, clear_repo_caches: Callable[[Path], None],
) -> DocumentWriter:
    """The analysis document written as every document is created, by the transport's verifier."""

    def write(title: str, frontmatter: dict[str, object], dry_run: bool) -> WriteResult:
        return create_document(
            repo_root=repo_root, verifier=verifier, clear_repo_caches=clear_repo_caches, doc_type=STRESS_ANALYSIS,
            title=title, body=None, keywords=None, extra_frontmatter=frontmatter, artifact_id=None,
            version="0.1.0", status="draft", last_updated=None, dry_run=dry_run,
        )

    return write


def _refuse_unwritten(result: WriteResult, *, wrote: bool) -> None:
    """Refuse what verification refused, or a write that wrote nothing, in the verifier's own words."""
    if result.error_messages or result.wrote != wrote:
        said = " ".join(result.error_messages) or "it was refused"
        raise ValueError(f"The analysis document cannot be {'written' if wrote else 'planned'}: {said}")
