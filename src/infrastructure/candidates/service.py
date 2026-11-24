"""Candidate and analysis operations shared by the HTTP and MCP transports."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, TypeAlias

from src.application.artifacts.document_table_rows import tables_of_stored_document
from src.application.change_sets.base import record_revision
from src.application.change_sets.candidate_apply import application_of
from src.application.change_sets.candidate_reads import (
    comparison,
    read_view,
    reading_beneath,
    rebase,
    standing_report,
    wire_standing,
)
from src.application.change_sets.candidate_recorded_form import from_mapping, to_mapping
from src.application.change_sets.candidate_work import conflicts_between
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.recorded_form import operation_to_mapping
from src.application.change_sets.recorded_form import to_mapping as set_to_mapping
from src.application.change_sets.recording import recorded
from src.application.change_sets.stacking import stack_of
from src.application.modeling.artifact_write import generate_entity_id
from src.application.modeling.diagram_layout_statement import DeclaresElementKinds
from src.application.stress_analysis.workspace import analyse
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.viewpoints.placed_occurrences import resolve_placed_entities
from src.domain.repository.repo_default_stress_analysis import NAIVE_CANDIDATE, STRESS_ANALYSIS
from src.infrastructure.artifact_index import notify_paths_changed, shared_artifact_index
from src.infrastructure.candidates.apply import write_operations
from src.infrastructure.candidates.repository import KIND, CandidateArchitectureStore, CandidateConflict
from src.infrastructure.rendering.layout.diagram_geometry import stored_geometry
from src.infrastructure.write.artifact_write.document import create_document
from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file
from src.infrastructure.write.artifact_write.types import WriteResult

#: The analysis document's writer, bound by the transport to its verifier: title, frontmatter, dry run.
DocumentWriter: TypeAlias = Callable[[str, dict[str, object], bool], WriteResult]


class CandidateService:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.store = CandidateArchitectureStore(root)
        self.index = shared_artifact_index(root)
        self.registry = ArtifactRegistry(self.index)

    def list(self) -> list[dict[str, Any]]:
        return [{"id": c.id, "name": c.name, "state": c.state, "parent": c.parent_id,
                 "scope": list(c.scope), "operations": len(c.changes.operations)}
                for c in self.store.list()]

    def read(self, ref: str) -> dict[str, Any]:
        record = to_mapping(self.store.require(ref))
        return {"record": record, "version": record_revision(record)}

    def save(self, record: Mapping[str, Any], based_on: str | None, *, ref: str | None = None) -> dict[str, Any]:
        body = dict(record)
        if ref and body.get("id", ref) != ref:
            raise ValueError("The addressed candidate and record id must agree.")
        body["id"] = ref or body.get("id") or generate_entity_id(str(KIND.id_prefix), str(body.get("name") or ""))
        candidate = from_mapping(body)
        version = self.store.save(candidate, based_on)
        notify_paths_changed([self.store.path(candidate.id)])
        return {"record": to_mapping(candidate), "version": version}

    def create(self, record: Mapping[str, Any], diagram: str | None = None) -> dict[str, Any]:
        body = dict(record)
        body.setdefault("state", "draft")
        body.setdefault("changes", set_to_mapping(ChangeSet((), self.index.read_model_version().etag)))
        if diagram:
            if "scope" in body:
                raise ValueError("Select either diagram scope or explicit scope.")
            drawing = self.index.get_diagram(diagram)
            if drawing is None:
                raise FileNotFoundError(diagram)
            # A diagram may draw one entity more than once; the scope is the entities, each once.
            placed = resolve_placed_entities(dict(drawing.extra), self.registry)
            body["scope"] = list(dict.fromkeys(e.artifact_id for e in placed))
        return self.save(body, None)

    def start(
        self, title: str, naive: Mapping[str, Any], write_document: DocumentWriter,
        *, question: str | None = None, scope_diagram: str | None = None,
    ) -> dict[str, Any]:
        """Start an analysis: its naive architecture and the document naming it, both or neither.

        The document is planned before anything is written, so the refusals a plan can see leave
        nothing behind; a refusal only the write sees takes the naive architecture back with it. The
        naive states its own scope, or takes the scope diagram's entities when it states none.
        """
        record = dict(naive)
        record.setdefault("id", generate_entity_id(str(KIND.id_prefix), str(record.get("name") or "")))
        ref = str(record["id"])
        frontmatter: dict[str, object] = {NAIVE_CANDIDATE: ref}
        if question:
            frontmatter["question"] = question
        if scope_diagram:
            frontmatter["scope-diagram"] = scope_diagram
        _refuse_unwritten(write_document(title, frontmatter, True), wrote=False)
        if self.store.find(ref) is not None:
            raise CandidateConflict(f"{ref} already exists; a naive architecture starts as a new candidate.")
        created = self.create(record, None if "scope" in record else scope_diagram)
        try:
            written = write_document(title, frontmatter, False)
            _refuse_unwritten(written, wrote=True)
        except BaseException:
            self._remove(ref)
            raise
        return {"document": written.artifact_id, "naive_candidate": created}

    def delete(self, ref: str) -> None:
        """Delete a candidate nothing depends on: none stacks on it, and no analysis starts from it."""
        self.store.require(ref)
        stacked = sorted(c.id for c in self.store.list() if c.parent_id == ref)
        if stacked:
            verb = "stacks" if len(stacked) == 1 else "stack"
            raise CandidateConflict(
                f"{ref} cannot be deleted: {', '.join(stacked)} {verb} on it. Delete what stacks on it first."
            )
        naming = sorted(
            doc.artifact_id for doc in self.index.list_documents(doc_type=STRESS_ANALYSIS)
            if doc.extra.get(NAIVE_CANDIDATE) == ref
        )
        if naming:
            raise CandidateConflict(
                f"{ref} cannot be deleted: it is the naive architecture of {', '.join(naming)}. "
                "Delete the analysis first."
            )
        self._remove(ref)

    def _remove(self, ref: str) -> None:
        self.store.delete(ref)
        notify_paths_changed([self.store.path(ref)])

    def rebase(self, ref: str, based_on: str) -> dict[str, Any]:
        """Write each drifted operation again against the model as it stands now. Nothing drifted, nothing changes."""
        candidate = self.store.require(ref)
        moved = rebase(candidate, self.store, self.registry, self.index.read_model_version().etag)
        return self.save(to_mapping(moved), based_on, ref=ref)

    def apply(self, ref: str, *, dry_run: bool) -> dict[str, Any]:
        """Write the candidate's operations onto the model in one transaction, then mark it integrated.

        A dry run answers what would be written and the refusal, if any. A real apply that is refused
        raises it, and leaves both the model and the candidate as they were.
        """
        candidate = self.store.require(ref)
        version = record_revision(to_mapping(candidate))
        application = application_of(candidate, self.store, self.registry)
        written = None if application.refusal else write_operations(application, self.root, dry_run=dry_run)
        refusal = application.refusal or (written.refusal if written else None)
        if refusal and not dry_run:
            raise CandidateConflict(refusal)
        integrated = bool(written and written.committed)
        if integrated:
            self.save(to_mapping(application.integrated), version, ref=ref)
        return {
            "candidate": ref, "dry_run": dry_run, "integrated": integrated, "refusal": refusal,
            "operation_id": written.operation_id if written else None,
            "standing": wire_standing(application.standing),
        }

    def edit(self, ref: str, based_on: str, patch: Mapping[str, Any]) -> dict[str, Any]:
        current = self.read(ref)
        return self.save(current["record"] | dict(patch), based_on, ref=ref)

    def record(self, ref: str, based_on: str, intent: Mapping[str, Any]) -> dict[str, Any]:
        """Record an edit among the candidate's operations, its base read from the stack beneath it."""
        candidate = self.store.require(ref)
        named = [str(intent[part]) for part in ("artifact_id", "source_entity", "target_entity") if part in intent]
        beneath = reading_beneath(candidate, self.store, self.registry, named)
        return self.save(to_mapping(recorded(candidate, intent, beneath)), based_on, ref=ref)

    def compare(
        self, ref: str, base: str, naive: str | None, diagram: str | None, ontology: DeclaresElementKinds,
    ) -> dict[str, Any]:
        result = comparison(self.store.require(ref), self.store, self.registry, base=base, naive=naive)
        if diagram:
            record = self.index.get_diagram(diagram)
            if record is None:
                raise FileNotFoundError(diagram)
            parsed = parse_diagram_file(record.path)
            result["drawing"] = stored_geometry(parsed, record.artifact_id, self.root, ontology)
        return result

    def analysis(self, ref: str, kinds: Sequence[str] = ()) -> dict[str, Any]:
        doc = self.index.get_document(ref)
        if doc is None:
            raise FileNotFoundError(ref)
        if doc.doc_type != STRESS_ANALYSIS:
            raise ValueError("Select a stress-analysis document.")
        naive = str(doc.extra.get(NAIVE_CANDIDATE) or "")
        if not naive:
            raise ValueError("Set naive-candidate on the stress-analysis document.")
        view = read_view(self.store.require(naive), self.store, self.registry)
        tables = tables_of_stored_document(doc.path, doc.doc_type, [self.root])
        return {"document": doc.artifact_id, "naive_candidate": naive, **analyse(tables, view, kinds=tuple(kinds))}

    def check(self, ids: Sequence[str]) -> dict[str, Any]:
        if not ids or len(set(ids)) != len(ids):
            raise ValueError("Select one or more distinct candidates.")
        selected = [self.store.require(ref) for ref in ids]
        layers = {}
        for candidate in selected:
            if candidate.state != "candidate":
                raise ValueError(f"Offer {candidate.id} as a candidate before checking integration.")
            layers.update((c.id, c) for c in stack_of(candidate, self.store.find))
        return {"candidates": list(ids), "overlaps": [
            {"kind": overlap.kind, "subject": overlap.subject, "parties": [
                {"set_id": p.set_id, "operation": operation_to_mapping(p.operation)} for p in overlap.parties
            ]} for overlap in conflicts_between(tuple(layers.values()))
        ]}

    def standing(self, ref: str) -> dict[str, Any]:
        return {"candidate": ref, "standing": standing_report(self.store.require(ref), self.store, self.registry)}

    def progress(self, ref: str, kinds: Sequence[str] = ()) -> dict[str, Any]:
        report = self.analysis(ref, kinds)
        return {key: report[key] for key in ("document", "naive_candidate", "progress", "coverage")}

    def incidence(self, ref: str) -> dict[str, Any]:
        report = self.analysis(ref)
        return {key: value for key, value in report.items() if key not in {"progress", "coverage"}}


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
