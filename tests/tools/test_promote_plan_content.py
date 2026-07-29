"""Tests for _promote_plan_content.py: docs and diagrams sub-plan helpers.

Covers: plan_docs and plan_diagrams with all branch paths including
not-found warnings, already-promoted, conflict detection, and new additions.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.infrastructure.write.artifact_write._promote_plan_content import (
    plan_diagrams,
    plan_docs,
)

# ---------------------------------------------------------------------------
# Lightweight fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeDocRecord:
    artifact_id: str
    doc_type: str
    title: str


@dataclass
class FakeDiagramRecord:
    artifact_id: str
    diagram_type: str
    name: str


class FakeRepo:
    def __init__(
        self,
        documents: list[FakeDocRecord] | None = None,
        diagrams: list[FakeDiagramRecord] | None = None,
    ) -> None:
        self._docs = {d.artifact_id: d for d in (documents or [])}
        self._diags = {d.artifact_id: d for d in (diagrams or [])}

    def list_documents(self) -> list[FakeDocRecord]:
        return list(self._docs.values())

    def get_document(self, did: str) -> FakeDocRecord | None:
        return self._docs.get(did)

    def list_diagrams(self) -> list[FakeDiagramRecord]:
        return list(self._diags.values())

    def get_diagram(self, did: str) -> FakeDiagramRecord | None:
        return self._diags.get(did)


class FakeRegistry:
    def __init__(self, ent_doc_ids: set[str] | None = None, ent_diag_ids: set[str] | None = None) -> None:
        self._doc_ids = ent_doc_ids or set()
        self._diag_ids = ent_diag_ids or set()

    def enterprise_document_ids(self) -> set[str]:
        return self._doc_ids

    def enterprise_diagram_ids(self) -> set[str]:
        return self._diag_ids


# ---------------------------------------------------------------------------
# plan_docs
# ---------------------------------------------------------------------------


class TestPlanDocs:
    def test_adds_new_document(self) -> None:
        doc = FakeDocRecord("DOC@1.new", "adr", "New Decision")
        repo = FakeRepo(documents=[doc])
        registry = FakeRegistry()
        already: list[str] = []
        warnings: list[str] = []
        to_add, conflicts = plan_docs(["DOC@1.new"], repo, registry, already, warnings)
        assert "DOC@1.new" in to_add
        assert conflicts == []
        assert warnings == []
        assert already == []

    def test_already_in_enterprise_skips(self) -> None:
        doc = FakeDocRecord("DOC@2.ex", "adr", "Existing")
        repo = FakeRepo(documents=[doc])
        registry = FakeRegistry(ent_doc_ids={"DOC@2.ex"})
        already: list[str] = []
        warnings: list[str] = []
        to_add, conflicts = plan_docs(["DOC@2.ex"], repo, registry, already, warnings)
        assert to_add == []
        assert "DOC@2.ex" in already
        assert conflicts == []

    def test_conflict_detected(self) -> None:
        eng_doc = FakeDocRecord("DOC@3.eng", "adr", "Same Title")
        ent_doc = FakeDocRecord("DOC@4.ent", "adr", "Same Title")
        repo = FakeRepo(documents=[eng_doc, ent_doc])
        registry = FakeRegistry(ent_doc_ids={"DOC@4.ent"})
        already: list[str] = []
        warnings: list[str] = []
        to_add, conflicts = plan_docs(["DOC@3.eng"], repo, registry, already, warnings)
        assert to_add == []
        assert len(conflicts) == 1
        assert conflicts[0].engagement_id == "DOC@3.eng"
        assert conflicts[0].enterprise_id == "DOC@4.ent"

    def test_document_not_found_adds_warning(self) -> None:
        repo = FakeRepo()
        registry = FakeRegistry()
        warnings: list[str] = []
        to_add, conflicts = plan_docs(["DOC@99.ghost"], repo, registry, [], warnings)
        assert to_add == []
        assert any("not found" in w.lower() or "DOC@99" in w for w in warnings)

    def test_none_document_ids_returns_empty(self) -> None:
        repo = FakeRepo()
        registry = FakeRegistry()
        to_add, conflicts = plan_docs(None, repo, registry, [], [])
        assert to_add == []
        assert conflicts == []


# ---------------------------------------------------------------------------
# plan_diagrams
# ---------------------------------------------------------------------------


class TestPlanDiagrams:
    def test_adds_new_diagram(self) -> None:
        diag = FakeDiagramRecord("DIA@1.new", "archimate", "New Diagram")
        repo = FakeRepo(diagrams=[diag])
        registry = FakeRegistry()
        already: list[str] = []
        warnings: list[str] = []
        to_add, conflicts = plan_diagrams(["DIA@1.new"], repo, registry, already, warnings)
        assert "DIA@1.new" in to_add
        assert conflicts == []
        assert warnings == []

    def test_already_in_enterprise_skips(self) -> None:
        diag = FakeDiagramRecord("DIA@2.ex", "archimate", "Existing")
        repo = FakeRepo(diagrams=[diag])
        registry = FakeRegistry(ent_diag_ids={"DIA@2.ex"})
        already: list[str] = []
        warnings: list[str] = []
        to_add, conflicts = plan_diagrams(["DIA@2.ex"], repo, registry, already, warnings)
        assert to_add == []
        assert "DIA@2.ex" in already

    def test_conflict_detected(self) -> None:
        eng_diag = FakeDiagramRecord("DIA@3.eng", "archimate", "Same Name")
        ent_diag = FakeDiagramRecord("DIA@4.ent", "archimate", "Same Name")
        repo = FakeRepo(diagrams=[eng_diag, ent_diag])
        registry = FakeRegistry(ent_diag_ids={"DIA@4.ent"})
        already: list[str] = []
        warnings: list[str] = []
        to_add, conflicts = plan_diagrams(["DIA@3.eng"], repo, registry, already, warnings)
        assert to_add == []
        assert len(conflicts) == 1
        assert conflicts[0].engagement_id == "DIA@3.eng"

    def test_diagram_not_found_adds_warning(self) -> None:
        repo = FakeRepo()
        registry = FakeRegistry()
        warnings: list[str] = []
        to_add, conflicts = plan_diagrams(["DIA@99.ghost"], repo, registry, [], warnings)
        assert to_add == []
        assert any("DIA@99" in w or "not found" in w.lower() for w in warnings)

    def test_none_diagram_ids_returns_empty(self) -> None:
        repo = FakeRepo()
        registry = FakeRegistry()
        to_add, conflicts = plan_diagrams(None, repo, registry, [], [])
        assert to_add == []
        assert conflicts == []
