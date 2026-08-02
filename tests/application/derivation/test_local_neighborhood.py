"""Tests for local-neighborhood/v1 derivation strategy.

Coverage:
  - BFS up to max_hops from root_entity_ids
  - Direction filtering: outbound, inbound, any
  - connection_types pre_filter
  - entity_types pre_filter
  - Unknown root entities are excluded from BFS
  - max_hops=0 returns only roots
  - SPEC registered with correct filters
"""

from __future__ import annotations

import pytest

from src.application.derivation.local_neighborhood import SPEC, derive
from src.domain.viewpoints.view_derivations import SourceModelSnapshot
from tests.application.derivation._fixtures import FakeQuery, _connection, _entity

_SNAPSHOT = SourceModelSnapshot(repo_scope="both")


class TestLocalNeighborhoodSpec:
    def test_name_and_version(self) -> None:
        assert SPEC.name == "local-neighborhood"
        assert SPEC.version == 1

    def test_supported_filters(self) -> None:
        assert "direction" in SPEC.supported_filters
        assert "connection_types" in SPEC.supported_filters
        assert "entity_types" in SPEC.supported_filters

    def test_spec_name(self) -> None:
        assert SPEC.name == "local-neighborhood"


def _linear_query() -> FakeQuery:
    """A → B → C (serving connections)."""
    return FakeQuery(
        entities=[_entity("A@1"), _entity("B@2"), _entity("C@3")],
        connections=[
            _connection("A@1---B@2@@serving", "A@1", "B@2", "serving"),
            _connection("B@2---C@3@@serving", "B@2", "C@3", "serving"),
        ],
    )


class TestLocalNeighborhoodBFS:
    def test_max_hops_1_from_root(self) -> None:
        result = derive(
            params={"root_entity_ids": ["A@1"], "max_hops": 1},
            snapshot=_SNAPSHOT,
            query=_linear_query(),
        )
        assert "A@1" in result.entity_ids
        assert "B@2" in result.entity_ids
        assert "C@3" not in result.entity_ids
        assert "A@1---B@2@@serving" in result.connection_ids

    @pytest.mark.verifies("REQ@1712870400.eBAa26")
    def test_max_hops_2_reaches_c(self) -> None:
        result = derive(
            params={"root_entity_ids": ["A@1"], "max_hops": 2},
            snapshot=_SNAPSHOT,
            query=_linear_query(),
        )
        assert "C@3" in result.entity_ids
        assert "B@2---C@3@@serving" in result.connection_ids

    def test_max_hops_0_returns_root_only(self) -> None:
        result = derive(
            params={"root_entity_ids": ["A@1"], "max_hops": 0},
            snapshot=_SNAPSHOT,
            query=_linear_query(),
        )
        assert result.entity_ids == frozenset({"A@1"})
        assert result.connection_ids == frozenset()

    def test_single_root_entity_id_param(self) -> None:
        result = derive(
            params={"root_entity_id": "A@1", "max_hops": 1},
            snapshot=_SNAPSHOT,
            query=_linear_query(),
        )
        assert "B@2" in result.entity_ids

    def test_unknown_root_excluded(self) -> None:
        result = derive(
            params={"root_entity_ids": ["UNKNOWN@99"], "max_hops": 2},
            snapshot=_SNAPSHOT,
            query=_linear_query(),
        )
        assert result.entity_ids == frozenset()

    def test_empty_root_returns_empty(self) -> None:
        result = derive(
            params={"root_entity_ids": [], "max_hops": 2},
            snapshot=_SNAPSHOT,
            query=_linear_query(),
        )
        assert result.entity_ids == frozenset()


class TestLocalNeighborhoodDirection:
    def _directed_query(self) -> FakeQuery:
        """A → B, C → B (A outbound, C inbound from B's perspective)."""
        return FakeQuery(
            entities=[_entity("A@1"), _entity("B@2"), _entity("C@3")],
            connections=[
                _connection("A@1---B@2@@serving", "A@1", "B@2", "serving"),
                _connection("C@3---B@2@@serving", "C@3", "B@2", "serving"),
            ],
        )

    def test_outbound_from_a_reaches_b_not_c(self) -> None:
        result = derive(
            params={
                "root_entity_ids": ["A@1"],
                "max_hops": 2,
                "pre_filters": {"direction": "outbound"},
            },
            snapshot=_SNAPSHOT,
            query=self._directed_query(),
        )
        assert "B@2" in result.entity_ids
        assert "C@3" not in result.entity_ids

    def test_inbound_from_b_reaches_a_and_c(self) -> None:
        result = derive(
            params={
                "root_entity_ids": ["B@2"],
                "max_hops": 1,
                "pre_filters": {"direction": "inbound"},
            },
            snapshot=_SNAPSHOT,
            query=self._directed_query(),
        )
        assert "A@1" in result.entity_ids
        assert "C@3" in result.entity_ids

    def test_any_direction_reaches_all(self) -> None:
        result = derive(
            params={
                "root_entity_ids": ["B@2"],
                "max_hops": 1,
                "pre_filters": {"direction": "any"},
            },
            snapshot=_SNAPSHOT,
            query=self._directed_query(),
        )
        assert "A@1" in result.entity_ids
        assert "C@3" in result.entity_ids

    def test_invalid_direction_defaults_to_any(self) -> None:
        result = derive(
            params={
                "root_entity_ids": ["B@2"],
                "max_hops": 1,
                "pre_filters": {"direction": "lateral"},
            },
            snapshot=_SNAPSHOT,
            query=self._directed_query(),
        )
        assert "A@1" in result.entity_ids


class TestLocalNeighborhoodConnectionTypeFilter:
    def _mixed_query(self) -> FakeQuery:
        """A → B (serving), A → C (flow)."""
        return FakeQuery(
            entities=[_entity("A@1"), _entity("B@2"), _entity("C@3")],
            connections=[
                _connection("A@1---B@2@@serving", "A@1", "B@2", "serving"),
                _connection("A@1---C@3@@flow", "A@1", "C@3", "flow"),
            ],
        )

    def test_filter_to_serving_only_excludes_c(self) -> None:
        result = derive(
            params={
                "root_entity_ids": ["A@1"],
                "max_hops": 1,
                "pre_filters": {"connection_types": ["serving"]},
            },
            snapshot=_SNAPSHOT,
            query=self._mixed_query(),
        )
        assert "B@2" in result.entity_ids
        assert "C@3" not in result.entity_ids

    def test_no_type_filter_includes_all(self) -> None:
        result = derive(
            params={"root_entity_ids": ["A@1"], "max_hops": 1},
            snapshot=_SNAPSHOT,
            query=self._mixed_query(),
        )
        assert "B@2" in result.entity_ids
        assert "C@3" in result.entity_ids


class TestLocalNeighborhoodEntityTypeFilter:
    def _typed_query(self) -> FakeQuery:
        """A → B (service), A → C (node)."""
        return FakeQuery(
            entities=[
                _entity("A@1", "application-component"),
                _entity("B@2", "application-service"),
                _entity("C@3", "technology-node"),
            ],
            connections=[
                _connection("A@1---B@2@@serving", "A@1", "B@2", "serving"),
                _connection("A@1---C@3@@serving", "A@1", "C@3", "serving"),
            ],
        )

    def test_entity_type_filter_excludes_node(self) -> None:
        result = derive(
            params={
                "root_entity_ids": ["A@1"],
                "max_hops": 1,
                "pre_filters": {"entity_types": ["application-service"]},
            },
            snapshot=_SNAPSHOT,
            query=self._typed_query(),
        )
        assert "B@2" in result.entity_ids
        assert "C@3" not in result.entity_ids

    def test_root_entities_not_filtered_by_entity_type(self) -> None:
        result = derive(
            params={
                "root_entity_ids": ["A@1"],
                "max_hops": 1,
                "pre_filters": {"entity_types": ["application-service"]},
            },
            snapshot=_SNAPSHOT,
            query=self._typed_query(),
        )
        assert "A@1" in result.entity_ids
