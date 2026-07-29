"""The execution-scoped TraceGraphIndex: direct adjacency over referenced connection types
only, entity maps, the realizer closure (direct ∪ derived), and the active-status policy."""

from __future__ import annotations

import pytest

from src.application.viewpoints.trace_index import build_trace_graph_index
from src.domain.relationships.relationship_reachability import DerivationBounds
from src.infrastructure.app_bootstrap import get_module_registry
from tests.application.viewpoints._fixtures import Store, connection, entity

_REFERENCED = frozenset({"archimate-realization", "archimate-influence", "archimate-association"})
_BOUNDS = DerivationBounds(max_hops=4, max_relationships=10_000, time_budget_seconds=2.0)


def _store() -> Store:
    entities = {
        "REQ@1": entity(artifact_id="REQ@1", artifact_type="requirement", domain="motivation"),
        "OUT@1": entity(artifact_id="OUT@1", artifact_type="outcome", domain="motivation"),
        "GOL@1": entity(artifact_id="GOL@1", artifact_type="goal", domain="motivation", status="deprecated"),
        "APP@1": entity(artifact_id="APP@1", artifact_type="application-component", domain="application"),
    }
    connections = [
        connection(artifact_id="C1", source="APP@1", target="REQ@1", conn_type="archimate-realization"),
        connection(artifact_id="C2", source="OUT@1", target="GOL@1", conn_type="archimate-realization"),
        connection(artifact_id="C3", source="APP@1", target="OUT@1", conn_type="archimate-serving"),
    ]
    return Store(entities=entities, connections=connections)


def _index():
    return build_trace_graph_index(
        _store(), get_module_registry(),
        referenced_connection_types=_REFERENCED, requirement_type="requirement", bounds=_BOUNDS,
    )


class TestAdjacency:
    def test_reverse_and_forward_adjacency_for_referenced_types(self) -> None:
        index = _index()
        assert index.sources("REQ@1", "archimate-realization") == ("APP@1",)
        assert index.targets("APP@1", "archimate-realization") == ("REQ@1",)

    def test_unreferenced_connection_types_are_excluded(self) -> None:
        index = _index()
        assert index.sources("OUT@1", "archimate-serving") == ()
        assert ("APP@1", "archimate-serving") not in index.outgoing

    def test_absent_edge_returns_empty(self) -> None:
        assert _index().sources("REQ@1", "archimate-influence") == ()


class TestEntityMaps:
    def test_type_domain_status_maps(self) -> None:
        index = _index()
        assert index.type_of["APP@1"] == "application-component"
        assert index.domain_of["REQ@1"] == "motivation"
        assert index.status_of["GOL@1"] == "deprecated"

    def test_classes_by_type_populated_from_registry(self) -> None:
        index = _index()
        assert "requirement" in index.classes_by_type
        assert isinstance(index.classes_by_type["requirement"], frozenset)

    def test_active_status_policy(self) -> None:
        index = _index()
        assert index.is_active("APP@1")
        assert not index.is_active("GOL@1")  # deprecated excluded


class TestRealizerClosure:
    def test_direct_realizer_present(self) -> None:
        assert _index().realizers_of("REQ@1") == frozenset({"APP@1"})

    def test_requirement_without_realizers_is_empty(self) -> None:
        # No element realizes OUT@1's requirements here; realizers_of is empty, not an error.
        assert _index().realizers_of("REQ@2") == frozenset()


class TestBudgetSemanticsPropagate:
    """The trace path inherits the derivation budget object and its two failure semantics
    unchanged (I-G10): the hard-ceiling typed error is a request-wide all-or-none abort that the
    index never swallows; the time-budget partial surfaces as ``derived_truncated`` (a lower
    bound) rather than being converted into a false pass/gap."""

    def test_hard_ceiling_error_is_not_swallowed(self) -> None:
        from unittest.mock import patch

        from src.domain.relationships.relationship_reachability import DerivationLimitError

        with patch(
            "src.application.viewpoints.trace_index.derive_relationships",
            side_effect=DerivationLimitError(2000),
        ):
            with pytest.raises(DerivationLimitError):
                _index()

    def test_time_budget_partial_surfaces_as_derived_truncated(self) -> None:
        from unittest.mock import patch

        from src.domain.relationships.relationship_reachability import DerivedRelationshipSet

        with patch(
            "src.application.viewpoints.trace_index.derive_relationships",
            return_value=DerivedRelationshipSet((), truncated=True),
        ):
            assert _index().derived_truncated is True
