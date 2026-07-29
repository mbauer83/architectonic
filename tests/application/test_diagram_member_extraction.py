"""Unit tests for diagram member-entity extraction (feeds the diagram FTS index)."""

from __future__ import annotations

from pathlib import Path

from src.application._diagram_entity_extraction import diagram_bound_entity_ids, diagram_member_text
from src.domain.ontology_representation.artifact_types import DiagramRecord


def _diagram(extra: dict[str, object]) -> DiagramRecord:
    return DiagramRecord(
        artifact_id="DIAG@1.aa.sample",
        artifact_type="diagram",
        name="Sample",
        diagram_type="c4-context",
        version="0.1.0",
        status="draft",
        path=Path("/repo/diagram-catalog/diagrams/DIAG@1.aa.sample.md"),
        extra=extra,
    )


class TestDiagramBoundEntityIds:
    def test_matrix_axes(self) -> None:
        ids = diagram_bound_entity_ids({"from-entity-ids": ["REQ@1.aa.x"], "to-entity-ids": ["OUT@1.bb.y"]})
        assert ids == ["REQ@1.aa.x", "OUT@1.bb.y"]

    def test_c4_bindings_target_entity_id(self) -> None:
        extra = {"bindings": [{"id": "b1", "target": {"entity_id": "APP@1.cc.platform"}}]}
        assert diagram_bound_entity_ids(extra) == ["APP@1.cc.platform"]

    def test_ignores_malformed_entries(self) -> None:
        extra = {"from-entity-ids": ["", 42], "bindings": [{"target": {}}, "nope", {"target": {"entity_id": ""}}]}
        assert diagram_bound_entity_ids(extra) == []

    def test_empty_extra(self) -> None:
        assert diagram_bound_entity_ids({}) == []


class TestDiagramMemberText:
    def test_combines_local_and_bound_names_deduped_in_order(self) -> None:
        diag = _diagram({"from-entity-ids": ["APP@1.cc.platform", "REQ@1.dd.dup"]})
        names = {"APP@1.cc.platform": "Management Platform", "REQ@1.dd.dup": "Local Node"}
        text = diagram_member_text(diag, local_names=["Local Node"], name_of=names.get)
        assert text == "Local Node Management Platform"

    def test_unresolved_bound_ids_are_dropped(self) -> None:
        diag = _diagram({"from-entity-ids": ["MISSING@1.zz.gone"]})
        text = diagram_member_text(diag, local_names=["Kept"], name_of=lambda _id: None)
        assert text == "Kept"

    def test_no_members_yields_empty_string(self) -> None:
        assert diagram_member_text(_diagram({}), local_names=[], name_of=lambda _id: None) == ""
