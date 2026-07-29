"""Unit tests for the datatype correspondence predicate (§3.2).

Covers: corresponds() and admissible_backing_kinds() using real
ConnectionTypeInfo from the archimate_4 and datatype modules.
"""

from __future__ import annotations

import pytest

from src.application.verification.datatype_consistency import admissible_backing_kinds, corresponds
from src.diagram_types.datatype import module as datatype_module
from src.ontologies.archimate_4 import module as archimate_module


def _arch(name: str):
    return archimate_module.connection_types[name]


def _dt(name: str):
    return datatype_module.own_connection_types[name]


class TestCorrespondsKindMatch:
    def test_specialization_and_dt_generalization_same_dir(self) -> None:
        assert corresponds(_dt("dt-generalization"), _arch("archimate-specialization"), same_direction=True)

    def test_specialization_and_dt_generalization_reverse_dir(self) -> None:
        assert not corresponds(_dt("dt-generalization"), _arch("archimate-specialization"), same_direction=False)

    def test_aggregation_and_dt_aggregation(self) -> None:
        assert corresponds(_dt("dt-aggregation"), _arch("archimate-aggregation"), same_direction=True)

    def test_aggregation_and_dt_composition(self) -> None:
        # dt-composition is a containment refinement of an aggregation backing (both containment)
        assert corresponds(_dt("dt-composition"), _arch("archimate-aggregation"), same_direction=True)

    def test_aggregation_and_dt_aggregation_reverse_rejected(self) -> None:
        assert not corresponds(_dt("dt-aggregation"), _arch("archimate-aggregation"), same_direction=False)

    def test_association_and_dt_association_same_dir(self) -> None:
        assert corresponds(_dt("dt-association"), _arch("archimate-association"), same_direction=True)

    def test_association_and_dt_association_reverse_dir(self) -> None:
        # dt-association is symmetric — either direction satisfies
        assert corresponds(_dt("dt-association"), _arch("archimate-association"), same_direction=False)

    def test_specialization_and_dt_association_rejected(self) -> None:
        # generalization ≠ association
        assert not corresponds(_dt("dt-association"), _arch("archimate-specialization"), same_direction=True)

    def test_dt_association_and_specialization_rejected(self) -> None:
        assert not corresponds(_dt("dt-generalization"), _arch("archimate-association"), same_direction=True)


class TestCorrespondsNoneKinds:
    def test_dt_type_none_relationship_kind_returns_false(self) -> None:
        # dt-dependency has relationship_kind: dependency; use a type with no kind to simulate
        from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo

        no_kind = ConnectionTypeInfo(artifact_type="x", conn_lang="x", relationship_kind=None)
        assert not corresponds(no_kind, _arch("archimate-association"), same_direction=True)

    def test_backing_none_relationship_kind_returns_false(self) -> None:
        # archimate-influence has no relationship_kind
        assert not corresponds(_dt("dt-association"), _arch("archimate-influence"), same_direction=True)


class TestAdmissibleBackingKinds:
    @pytest.mark.parametrize(
        "dt_name, expected_kind",
        [
            ("dt-association", "association"),
            ("dt-aggregation", "containment"),
            ("dt-composition", "containment"),
            ("dt-generalization", "generalization"),
            ("dt-dependency", "dependency"),
        ],
    )
    def test_admissible_kinds(self, dt_name: str, expected_kind: str) -> None:
        kinds = admissible_backing_kinds(_dt(dt_name))
        assert kinds == frozenset({expected_kind})

    def test_none_relationship_kind_returns_empty(self) -> None:
        from src.domain.ontology_representation.ontology_types import ConnectionTypeInfo

        no_kind = ConnectionTypeInfo(artifact_type="x", conn_lang="x", relationship_kind=None)
        assert admissible_backing_kinds(no_kind) == frozenset()
