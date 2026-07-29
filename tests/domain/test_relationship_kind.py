"""Tests for the relationship_kind field on ConnectionTypeInfo.

Covers: RELATIONSHIP_KINDS constant; the four tagged ArchiMate types;
untagged ArchiMate types remain None; diagram loader round-trip.
"""

from __future__ import annotations

from pathlib import Path

from src.domain.diagrams.diagram_ontology_loader import load_diagram_ontology
from src.domain.ontology_representation.ontology_types import RELATIONSHIP_KINDS
from src.ontologies.archimate_4 import module as archimate_module


def _archimate_conn(name: str):
    return archimate_module.connection_types[name]


class TestRelationshipKindsConstant:
    def test_constant_contains_expected_kinds(self) -> None:
        assert "association" in RELATIONSHIP_KINDS
        assert "containment" in RELATIONSHIP_KINDS
        assert "generalization" in RELATIONSHIP_KINDS
        assert "dependency" in RELATIONSHIP_KINDS

    def test_constant_is_frozenset(self) -> None:
        assert isinstance(RELATIONSHIP_KINDS, frozenset)


class TestArchiMateRelationshipKinds:
    def test_association_is_association(self) -> None:
        assert _archimate_conn("archimate-association").relationship_kind == "association"

    def test_aggregation_is_containment(self) -> None:
        assert _archimate_conn("archimate-aggregation").relationship_kind == "containment"

    def test_composition_is_containment(self) -> None:
        assert _archimate_conn("archimate-composition").relationship_kind == "containment"

    def test_specialization_is_generalization(self) -> None:
        assert _archimate_conn("archimate-specialization").relationship_kind == "generalization"

    def test_untagged_types_are_none(self) -> None:
        for name in ("archimate-realization", "archimate-serving", "archimate-flow", "archimate-influence"):
            assert _archimate_conn(name).relationship_kind is None, f"{name} should have no relationship_kind"


class TestDiagramLoaderRelationshipKind:
    def test_relationship_kind_round_trips(self, tmp_path: Path) -> None:
        yaml_text = (
            "connection_types:\n"
            "  dt-association:\n"
            "    embedding: none\n"
            "    relationship_kind: association\n"
            "    symmetric: true\n"
            "  dt-generalization:\n"
            "    embedding: none\n"
            "    relationship_kind: generalization\n"
            "    symmetric: false\n"
        )
        f = tmp_path / "ontology.yaml"
        f.write_text(yaml_text, encoding="utf-8")
        ont = load_diagram_ontology(f)
        assert ont.connection_types["dt-association"].relationship_kind == "association"
        assert ont.connection_types["dt-generalization"].relationship_kind == "generalization"

    def test_missing_relationship_kind_is_none(self, tmp_path: Path) -> None:
        yaml_text = "connection_types:\n  dt-dep:\n    embedding: none\n"
        f = tmp_path / "ontology.yaml"
        f.write_text(yaml_text, encoding="utf-8")
        ont = load_diagram_ontology(f)
        assert ont.connection_types["dt-dep"].relationship_kind is None
