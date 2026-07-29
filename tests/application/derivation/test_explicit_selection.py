"""Tests for explicit-selection/v1 derivation strategy.

Coverage:
  - Returns only entity_ids/connection_ids that exist in the query
  - Unknown ids are silently omitted
  - Empty/missing parameters produce an empty CandidateSet
  - SPEC is registered with the correct name, version, and no supported filters
"""

from __future__ import annotations

from src.application.derivation.explicit_selection import SPEC, derive
from src.application.derivation.types import CandidateSet
from src.domain.viewpoints.view_derivations import SourceModelSnapshot
from tests.application.derivation._fixtures import FakeQuery, _connection, _entity

_SNAPSHOT = SourceModelSnapshot(repo_scope="both")


class TestExplicitSelectionSpec:
    def test_name_and_version(self) -> None:
        assert SPEC.name == "explicit-selection"
        assert SPEC.version == 1

    def test_no_supported_filters(self) -> None:
        assert SPEC.supported_filters == frozenset()

    def test_spec_name_matches(self) -> None:
        assert SPEC.name == "explicit-selection"


class TestExplicitSelectionDerive:
    def _query(self) -> FakeQuery:
        return FakeQuery(
            entities=[_entity("A@1"), _entity("B@2"), _entity("C@3")],
            connections=[
                _connection("A@1---B@2@@serving", "A@1", "B@2"),
                _connection("B@2---C@3@@flow", "B@2", "C@3"),
            ],
        )

    def test_returns_known_entities(self) -> None:
        result = derive(
            params={"entity_ids": ["A@1", "B@2"]},
            snapshot=_SNAPSHOT,
            query=self._query(),
        )
        assert result.entity_ids == frozenset({"A@1", "B@2"})
        assert result.connection_ids == frozenset()

    def test_unknown_entity_ids_omitted(self) -> None:
        result = derive(
            params={"entity_ids": ["A@1", "UNKNOWN@99"]},
            snapshot=_SNAPSHOT,
            query=self._query(),
        )
        assert result.entity_ids == frozenset({"A@1"})

    def test_returns_known_connections(self) -> None:
        result = derive(
            params={"connection_ids": ["A@1---B@2@@serving", "MISSING@@x"]},
            snapshot=_SNAPSHOT,
            query=self._query(),
        )
        assert result.connection_ids == frozenset({"A@1---B@2@@serving"})

    def test_both_entity_and_connection_ids(self) -> None:
        result = derive(
            params={
                "entity_ids": ["A@1"],
                "connection_ids": ["B@2---C@3@@flow"],
            },
            snapshot=_SNAPSHOT,
            query=self._query(),
        )
        assert result.entity_ids == frozenset({"A@1"})
        assert result.connection_ids == frozenset({"B@2---C@3@@flow"})

    def test_empty_params_returns_empty_set(self) -> None:
        result = derive(params={}, snapshot=_SNAPSHOT, query=self._query())
        assert result == CandidateSet()

    def test_non_list_entity_ids_returns_empty(self) -> None:
        result = derive(
            params={"entity_ids": "A@1"},
            snapshot=_SNAPSHOT,
            query=self._query(),
        )
        assert result.entity_ids == frozenset()

    def test_all_unknown_returns_empty(self) -> None:
        result = derive(
            params={"entity_ids": ["X@99", "Y@99"]},
            snapshot=_SNAPSHOT,
            query=self._query(),
        )
        assert result.entity_ids == frozenset()

    def test_empty_query_returns_empty(self) -> None:
        result = derive(
            params={"entity_ids": ["A@1"]},
            snapshot=_SNAPSHOT,
            query=FakeQuery(),
        )
        assert result.entity_ids == frozenset()
