"""Candidate and analysis operations shared by the HTTP and MCP transports."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from src.application.artifacts.document_table_rows import tables_of_stored_document
from src.application.change_sets.base import record_revision
from src.application.change_sets.candidate_recorded_form import from_mapping, to_mapping
from src.application.change_sets.candidate_work import conflicts_between
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.recorded_form import operation_to_mapping
from src.application.change_sets.recorded_form import to_mapping as set_to_mapping
from src.application.change_sets.stacking import stack_of
from src.application.modeling.artifact_write import generate_entity_id
from src.application.stress_analysis.workspace import analyse
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.viewpoints.placed_occurrences import resolve_placed_entities
from src.infrastructure.artifact_index import notify_paths_changed, shared_artifact_index
from src.infrastructure.candidates.reads import comparison, read_view
from src.infrastructure.candidates.repository import KIND, CandidateRepository


class CandidateService:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.store = CandidateRepository(root)
        self.index = shared_artifact_index(root)
        self.registry = ArtifactRegistry(self.index)

    def list(self) -> list[dict[str, Any]]:
        return [{"id": c.id, "name": c.name, "state": c.state, "parent": c.parent_id}
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
            body["scope"] = [e.artifact_id for e in resolve_placed_entities(dict(drawing.extra), self.registry)]
        return self.save(body, None)

    def edit(self, ref: str, based_on: str, patch: Mapping[str, Any]) -> dict[str, Any]:
        current = self.read(ref)
        return self.save(current["record"] | dict(patch), based_on, ref=ref)

    def compare(self, ref: str, base: str, naive: str | None, diagram: str | None) -> dict[str, Any]:
        result = comparison(self.store.require(ref), self.store, self.registry, base=base, naive=naive)
        if diagram:
            from src.infrastructure.app_bootstrap import process_runtime_catalogs  # noqa: PLC0415
            from src.infrastructure.rest.routers.diagrams._layout_geometry import stored_geometry  # noqa: PLC0415
            from src.infrastructure.write.artifact_write.parse_existing import parse_diagram_file  # noqa: PLC0415

            record = self.index.get_diagram(diagram)
            if record is None:
                raise FileNotFoundError(diagram)
            result["drawing"] = stored_geometry(parse_diagram_file(record.path), record.artifact_id, self.root,
                                                process_runtime_catalogs().ontology)
        return result

    def analysis(self, ref: str, kinds: Sequence[str] = ()) -> dict[str, Any]:
        doc = self.index.get_document(ref)
        if doc is None:
            raise FileNotFoundError(ref)
        if doc.doc_type != "stress-analysis":
            raise ValueError("Select a stress-analysis document.")
        naive = str(doc.extra.get("naive-candidate") or "")
        if not naive:
            raise ValueError("Set naive-candidate on the stress-analysis document.")
        view = read_view(self.store.require(naive), self.store, self.registry)
        tables = tables_of_stored_document(doc.path, doc.doc_type, [self.root])
        return {"document": doc.artifact_id, "naive_candidate": naive, **analyse(tables, view, kinds=tuple(kinds))}

    def check(self, ids: Sequence[str]) -> dict[str, Any]:
        selected = [self.store.require(ref) for ref in ids]
        for candidate in selected:
            if candidate.state != "candidate":
                raise ValueError(f"Offer {candidate.id} as a candidate before checking integration.")
            stack_of(candidate, self.store.find)
        return {"candidates": list(ids), "overlaps": [
            {"kind": overlap.kind, "subject": overlap.subject, "parties": [
                {"set_id": p.set_id, "operation": operation_to_mapping(p.operation)} for p in overlap.parties
            ]} for overlap in conflicts_between(selected)
        ]}

    def standing(self, ref: str) -> dict[str, Any]:
        report = self.compare(ref, "model", None, None)
        return {"candidate": ref, "standing": report["standing"]}

    def progress(self, ref: str, kinds: Sequence[str] = ()) -> dict[str, Any]:
        report = self.analysis(ref, kinds)
        return {key: report[key] for key in ("document", "naive_candidate", "progress", "coverage")}

    def incidence(self, ref: str) -> dict[str, Any]:
        report = self.analysis(ref)
        return {key: value for key, value in report.items() if key not in {"progress", "coverage"}}
