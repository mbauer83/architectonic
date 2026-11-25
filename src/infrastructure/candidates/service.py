"""Candidate and analysis operations shared by the HTTP and MCP transports."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, TypeAlias

from src.application.artifacts.document_table_rows import DocumentTables, tables_of_stored_document
from src.application.artifacts.repository import ArtifactRepository
from src.application.change_sets.base import record_revision
from src.application.change_sets.candidate_apply import TERMINAL, application_of
from src.application.change_sets.candidate_architecture import CandidateArchitecture
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
from src.application.change_sets.stacking import drawn_on, stack_of
from src.application.identifier_allocator import get_default_allocator
from src.application.modeling.artifact_write import generate_entity_id
from src.application.modeling.diagram_layout_statement import DeclaresElementKinds
from src.application.stress_analysis.workspace import analyse
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.viewpoints.placed_occurrences import resolve_placed_entities
from src.domain.artifact_id import canonical_entity_key
from src.domain.modules.module_types import EntityTypeName
from src.domain.repository.repo_default_stress_analysis import ANALYSIS_CONTEXT, NAIVE_CANDIDATE, STRESS_ANALYSIS
from src.infrastructure.app_bootstrap import get_module_registry
from src.infrastructure.artifact_index import notify_paths_changed, shared_artifact_index
from src.infrastructure.candidates.apply import write_operations
from src.infrastructure.candidates.repository import (
    KIND,
    CandidateArchitectureStore,
    CandidateConflict,
    NotStored,
)
from src.infrastructure.candidates.scope_drawing import NoStoredDiagram, generated_drawing, stored_drawing
from src.infrastructure.write.artifact_write.document import create_document
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
                 "scope": list(c.scope), "diagram": c.diagram, "operations": len(c.changes.operations)}
                for c in self.store.list()]

    def resolved(self, ref: str) -> str:
        """The id the candidate is stored under, for *ref* in either spelling; refused as not found."""
        return self.store.require(ref).id

    def read(self, ref: str) -> dict[str, Any]:
        record = to_mapping(self.store.require(ref))
        return {"record": record, "version": record_revision(record)}

    def save(
        self, record: Mapping[str, Any], based_on: str | None, *, ref: str | None = None, applied: bool = False,
    ) -> dict[str, Any]:
        body = dict(record)
        if ref and canonical_entity_key(str(body.get("id", ref))) != canonical_entity_key(ref):
            raise ValueError("The addressed candidate and record id must agree.")
        body["id"] = ref or body.get("id") or generate_entity_id(str(KIND.id_prefix), str(body.get("name") or ""))
        if (parent := body.get("parent")) and (beneath := self.store.find(str(parent))) is not None:
            body["parent"] = beneath.id  # a parent is held under the id it is stored by, however it was named
        candidate = from_mapping(body)
        version = self.store.save(candidate, based_on, applied=applied)
        notify_paths_changed([self.store.path(candidate.id)])
        return {"record": to_mapping(candidate), "version": version}

    def create(self, record: Mapping[str, Any], edits: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
        """A new candidate from its header, with *edits* recorded, in one write.

        A header that names the diagram it is drawn on and states no scope is scoped by what the diagram draws.
        """
        body = {key: value for key, value in record.items() if value is not None}
        body.setdefault("state", "draft")
        body.setdefault("changes", set_to_mapping(ChangeSet((), self.index.read_model_version().etag)))
        if diagram := body.get("diagram"):
            drawing = self.index.get_diagram(str(diagram))
            if drawing is None:
                raise NotStored(f"No diagram {diagram} is stored.")
            body["diagram"] = drawing.artifact_id
            if "scope" not in body:
                # A diagram may draw one entity more than once; the scope is the entities, each once.
                placed = resolve_placed_entities(dict(drawing.extra), self.registry)
                body["scope"] = list(dict.fromkeys(canonical_entity_key(e.artifact_id) for e in placed))
        if edits:
            body["id"] = body.get("id") or generate_entity_id(str(KIND.id_prefix), str(body.get("name") or ""))
            body = to_mapping(self._recorded_all(from_mapping(body), edits))
        return self.save(body, None)

    def start(
        self, title: str, naive: Mapping[str, Any], write_document: DocumentWriter, *, context: str | None = None,
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
        if self.store.find(ref) is not None:
            raise CandidateConflict(f"{ref} already exists; a naive architecture starts as a new candidate.")
        created = self.create(record)
        try:
            written = write_document(title, frontmatter, False)
            _refuse_unwritten(written, wrote=True)
        except BaseException:
            self._remove(ref)
            raise
        return {"document": written.artifact_id, "naive_candidate": created}

    def delete(self, ref: str, *, based_on: str | None = None, dry_run: bool = False) -> dict[str, Any]:
        """Delete a candidate nothing refers to, or say what refers to it.

        Refused (409) while a candidate stacks on it, an analysis starts from it, an analysis's verdicts
        or adaptations name it, or it is integrated — an integrated candidate is the record of what was
        written to the model. *based_on*, when given, is the version the caller read: a candidate changed
        since is not deleted unseen. A dry run answers what a deletion would do and deletes nothing.
        """
        candidate = self.store.require(ref)
        ref = candidate.id
        version = record_revision(to_mapping(candidate))
        if based_on is not None and based_on != version:
            raise CandidateConflict(
                f"The candidate changed: its current version is {version}. Read it before deleting it."
            )
        if candidate.state == "integrated":
            raise CandidateConflict(
                f"{ref} is integrated, and is kept as the record of what was written to the model. "
                "An integrated candidate is not deleted."
            )
        refusal = self._held_by(ref)
        if refusal:
            raise CandidateConflict(f"{ref} cannot be deleted: {refusal}")
        if not dry_run:
            self._remove(ref, version)
        return {"candidate": ref, "dry_run": dry_run, "deleted": not dry_run, "version": version}

    def _held_by(self, ref: str) -> str | None:
        """What still refers to the candidate *ref*, in a sentence that says what to do, or None."""
        key = canonical_entity_key(ref)
        stacked = sorted(c.id for c in self.store.list() if c.parent_id and canonical_entity_key(c.parent_id) == key)
        if stacked:
            verb = "stacks" if len(stacked) == 1 else "stack"
            return f"{', '.join(stacked)} {verb} on it. Delete what stacks on it first."
        analyses = self.index.list_documents(doc_type=STRESS_ANALYSIS)
        naming = sorted(
            doc.artifact_id for doc in analyses
            if canonical_entity_key(str(doc.extra.get(NAIVE_CANDIDATE) or "")) == key
        )
        if naming:
            return f"it is the naive architecture of {', '.join(naming)}. Delete the analysis first."
        rows = [
            f"{doc.artifact_id} ({table} {row.row_id})"
            for doc in analyses
            for table, column in (("survival", "architecture"), ("adaptations", "candidate_architecture"))
            for row in _rows_of(tables_of_stored_document(doc.path, doc.doc_type, [self.root]), table)
            if canonical_entity_key(str(row.cells[column].value if column in row.cells else "")) == key
        ]
        if rows:
            return (
                f"an analysis names it in {', '.join(rows)}. Remove or re-point those rows first, so no "
                "verdict or adaptation names a candidate that is gone."
            )
        return None

    def _remove(self, ref: str, based_on: str | None = None) -> None:
        self.store.delete(ref, based_on)
        notify_paths_changed([self.store.path(ref)])

    def rebase(self, ref: str, based_on: str) -> dict[str, Any]:
        """Write each drifted operation again against the model as it stands now. Nothing drifted, nothing changes."""
        candidate = _a_draft(self.store.require(ref), "re-based")
        ref = candidate.id
        moved = rebase(candidate, self.store, self.registry, self.index.read_model_version().etag)
        return self.save(to_mapping(moved), based_on, ref=ref)

    def apply(self, ref: str, *, dry_run: bool) -> dict[str, Any]:
        """Write the candidate's operations onto the model in one transaction, then mark it integrated.

        A dry run answers what would be written and the refusal, if any. A real apply that is refused
        raises it, and leaves both the model and the candidate as they were.
        """
        candidate = self.store.require(ref)
        ref = candidate.id
        application = application_of(candidate, self.store, self.registry)
        written = None if application.refusal else write_operations(application, self.root, dry_run=dry_run)
        refusal = application.refusal or (written.refusal if written else None)
        if refusal and not dry_run:
            raise CandidateConflict(refusal)
        integrated = bool(written and written.committed) and self._mark_integrated(candidate)
        return {
            "candidate": ref, "dry_run": dry_run, "integrated": integrated, "refusal": refusal,
            "operation_id": written.operation_id if written else None,
            "standing": wire_standing(application.standing),
        }

    def _mark_integrated(self, applied: CandidateArchitecture) -> bool:
        """Record that *applied*'s operations are in the model, once they are.

        The write has committed by now, so a header edit made meanwhile (a rename, say) is no reason to
        answer as if nothing happened: the candidate is read again and marked over its current version.
        Only operations changed since the apply read them leave it unmarked, since the model then holds
        what the candidate no longer says; a retried apply finds them written and marks it.
        """
        for _attempt in range(3):
            current = self.store.require(applied.id)
            if current.state == "integrated":
                return True
            if current.changes != applied.changes:
                return False
            try:
                self.store.save(
                    replace(current, state="integrated"), record_revision(to_mapping(current)), applied=True,
                )
            except CandidateConflict:
                continue
            notify_paths_changed([self.store.path(applied.id)])
            return True
        return False

    def edit(self, ref: str, based_on: str, patch: Mapping[str, Any]) -> dict[str, Any]:
        current = self.read(ref)
        return self.save(current["record"] | dict(patch), based_on, ref=str(current["record"]["id"]))

    def record(self, ref: str, based_on: str, edits: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Record *edits* among the candidate's operations, in order, as one write over *based_on*.

        Each edit's base is read from the stack beneath it, with the edits before it in the list laid
        over: the list reads as the same edits recorded one call each, and all of it is written or none.
        A create that names no id is given one, minted from its type and name.
        """
        candidate = _a_draft(self.store.require(ref), "given new operations")
        return self.save(to_mapping(self._recorded_all(candidate, edits)), based_on, ref=candidate.id)

    def _recorded_all(
        self, candidate: CandidateArchitecture, edits: Sequence[Mapping[str, Any]],
    ) -> CandidateArchitecture:
        for edit in edits:
            intent = _with_minted_id(edit)
            named = [
                str(intent[part]) for part in ("artifact_id", "source_entity", "target_entity") if intent.get(part)
            ]
            beneath = reading_beneath(candidate, self.store, self.registry, named)
            candidate = recorded(candidate, intent, beneath)
        return candidate

    def compare(
        self, ref: str, base: str, naive: str | None, diagram: str | None, ontology: DeclaresElementKinds,
    ) -> dict[str, Any]:
        """*ref* against *base*, with the drawing it is read on: *diagram*, else what its stack is drawn on."""
        candidate = self.store.require(ref)
        result = comparison(candidate, self.store, self.registry, base=base, naive=naive)
        stack = stack_of(candidate, self.store.find)
        drawing = self.drawing(diagram or drawn_on(stack), [ref for layer in stack for ref in layer.scope],
                               candidate.name, ontology)
        return result | ({"drawing": drawing} if drawing else {})

    def drawing(
        self, diagram: str | None, scope: Sequence[str], name: str, ontology: DeclaresElementKinds,
    ) -> dict[str, Any] | None:
        """The stored *diagram*'s geometry, else a view generated from *scope*; None where there is neither."""
        repo = ArtifactRepository(self.index)
        try:
            return (stored_drawing(repo, diagram, self.root, ontology) if diagram
                    else generated_drawing(repo, scope, name, self.root, ontology))
        except NoStoredDiagram as missing:
            raise NotStored(str(missing)) from missing

    def analysis_tables(self, ref: str) -> tuple[str, str, DocumentTables]:
        """The analysis document's id, its naive candidate's id and its typed tables; refused for any other document."""
        doc = self.index.get_document(ref)
        if doc is None:
            raise NotStored(f"No document {ref} is stored.")
        if doc.doc_type != STRESS_ANALYSIS:
            raise ValueError("Select a stress-analysis document.")
        naive = str(doc.extra.get(NAIVE_CANDIDATE) or "")
        if not naive:
            raise ValueError("Set naive-candidate on the stress-analysis document.")
        stored = self.store.find(naive)
        tables = tables_of_stored_document(doc.path, doc.doc_type, [self.root])
        return doc.artifact_id, stored.id if stored else naive, tables

    def analysis(self, ref: str) -> dict[str, Any]:
        document, naive, tables = self.analysis_tables(ref)
        view = read_view(self.store.require(naive), self.store, self.registry)
        return {"document": document, "naive_candidate": naive, **analyse(tables, view)}

    def check(self, ids: Sequence[str]) -> dict[str, Any]:
        selected = [self.store.require(ref) for ref in ids]
        if not selected or len({candidate.id for candidate in selected}) != len(selected):
            raise ValueError("Select one or more distinct candidates.")
        layers = {}
        for candidate in selected:
            # A draft may be applied, so it may be checked: the check is how an applier sees what else
            # touches the same things. A terminal candidate has nothing left to integrate.
            if candidate.state in TERMINAL:
                raise ValueError(
                    f"{candidate.id} is {candidate.state}; only a draft or an offered candidate is checked."
                )
            layers.update((c.id, c) for c in stack_of(candidate, self.store.find))
        return {"candidates": [candidate.id for candidate in selected], "overlaps": [
            {"kind": overlap.kind, "subject": overlap.subject, "parties": [
                {"set_id": p.set_id, "operation": operation_to_mapping(p.operation)} for p in overlap.parties
            ]} for overlap in conflicts_between(tuple(layers.values()))
        ]}

    def standing(self, ref: str) -> dict[str, Any]:
        candidate = self.store.require(ref)
        return {"candidate": candidate.id, "standing": standing_report(candidate, self.store, self.registry)}

    def progress(self, ref: str) -> dict[str, Any]:
        report = self.analysis(ref)
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


def _a_draft(candidate: CandidateArchitecture, done: str) -> CandidateArchitecture:
    """*candidate*, refused (409, a state conflict) unless it is a draft, saying how to make it one."""
    if candidate.state == "draft":
        return candidate
    if candidate.state == "candidate":
        raise CandidateConflict(
            f"{candidate.id} is offered (state candidate); only a draft is {done}. Return it to draft first "
            "(change_set_edit, or PATCH, with state draft)."
        )
    raise CandidateConflict(f"{candidate.id} is {candidate.state}, which is final; only a draft is {done}.")


def _with_minted_id(edit: Mapping[str, Any]) -> Mapping[str, Any]:
    """*edit*, or for a create that names no id, the create with one minted as the write path mints one."""
    if edit.get("op") != "create_entity" or edit.get("artifact_id"):
        return edit
    fields: Mapping[str, Any] = edit.get("fields") or {}
    info = get_module_registry().find_entity_type(EntityTypeName(str(fields.get("artifact_type") or "")))
    if info is None:
        raise ValueError(
            f"A new entity names its artifact_type, and {fields.get('artifact_type')!r} is not one: see the "
            "entity types `artifact_help` lists."
        )
    minted = get_default_allocator().allocate(prefix=info.prefix, name_hint=str(fields.get("name") or ""))
    return {**edit, "artifact_id": minted}


def _refuse_unwritten(result: WriteResult, *, wrote: bool) -> None:
    """Refuse what verification refused, or a write that wrote nothing, in the verifier's own words."""
    if result.error_messages or result.wrote != wrote:
        said = " ".join(result.error_messages) or "it was refused"
        raise ValueError(f"The analysis document cannot be {'written' if wrote else 'planned'}: {said}")


def _rows_of(tables: DocumentTables, name: str) -> tuple[Any, ...]:
    table = tables.table(name)
    return tuple(table.rows) if table else ()
