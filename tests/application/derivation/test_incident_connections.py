"""Tests for incident-connections/v1 derivation strategy.

Coverage:
  - Returns connections incident to entity_ids and their endpoint entities
  - Direction filtering: outbound, inbound, any
  - connection_types pre_filter
  - No recursion: only direct edges, not transitive
  - Unknown entity_ids are excluded
  - SPEC registered with correct filters
"""

from __future__ import annotations

from src.application.derivation.incident_connections import SPEC, derive
from src.domain.viewpoints.view_derivations import SourceModelSnapshot
from tests.application.derivation._fixtures import FakeQuery, _connection, _entity

_SNAPSHOT = SourceModelSnapshot(repo_scope="engagement")


class TestIncidentConnectionsSpec:
    def test_name_and_version(self) -> None:
        assert SPEC.name == "incident-connections"
        assert SPEC.version == 1

    def test_supported_filters(self) -> None:
        assert "direction" in SPEC.supported_filters
        assert "connection_types" in SPEC.supported_filters
        assert "entity_types" not in SPEC.supported_filters

    def test_spec_name(self) -> None:
        assert SPEC.name == "incident-connections"


def _hub_query() -> FakeQuery:
    """B is a hub: A → B, B → C, D → B."""
    return FakeQuery(
        entities=[_entity("A@1"), _entity("B@2"), _entity("C@3"), _entity("D@4")],
        connections=[
            _connection("A@1---B@2@@serving", "A@1", "B@2", "serving"),
            _connection("B@2---C@3@@flow", "B@2", "C@3", "flow"),
            _connection("D@4---B@2@@access", "D@4", "B@2", "access"),
        ],
    )


class TestIncidentConnectionsBasic:
    def test_all_incident_connections_from_hub(self) -> None:
        result = derive(
            params={"entity_ids": ["B@2"]},
            snapshot=_SNAPSHOT,
            query=_hub_query(),
        )
        assert "A@1---B@2@@serving" in result.connection_ids
        assert "B@2---C@3@@flow" in result.connection_ids
        assert "D@4---B@2@@access" in result.connection_ids

    def test_endpoint_entities_included(self) -> None:
        result = derive(
            params={"entity_ids": ["B@2"]},
            snapshot=_SNAPSHOT,
            query=_hub_query(),
        )
        assert "A@1" in result.entity_ids
        assert "B@2" in result.entity_ids
        assert "C@3" in result.entity_ids
        assert "D@4" in result.entity_ids

    def test_entity_with_no_connections_returns_itself(self) -> None:
        result = derive(
            params={"entity_ids": ["A@1"]},
            snapshot=_SNAPSHOT,
            query=FakeQuery(entities=[_entity("A@1")]),
        )
        assert result.entity_ids == frozenset({"A@1"})
        assert result.connection_ids == frozenset()

    def test_unknown_entity_id_excluded(self) -> None:
        result = derive(
            params={"entity_ids": ["UNKNOWN@99"]},
            snapshot=_SNAPSHOT,
            query=_hub_query(),
        )
        assert result.entity_ids == frozenset()
        assert result.connection_ids == frozenset()

    def test_empty_entity_ids_returns_empty(self) -> None:
        result = derive(
            params={"entity_ids": []},
            snapshot=_SNAPSHOT,
            query=_hub_query(),
        )
        assert result.entity_ids == frozenset()

    def test_non_recursive_no_transitive_connections(self) -> None:
        """Incident from A returns A→B but NOT B→C (no recursion)."""
        result = derive(
            params={"entity_ids": ["A@1"]},
            snapshot=_SNAPSHOT,
            query=_hub_query(),
        )
        assert "A@1---B@2@@serving" in result.connection_ids
        assert "B@2---C@3@@flow" not in result.connection_ids


class TestIncidentConnectionsDirection:
    def test_outbound_from_hub_returns_only_b_to_c(self) -> None:
        result = derive(
            params={
                "entity_ids": ["B@2"],
                "pre_filters": {"direction": "outbound"},
            },
            snapshot=_SNAPSHOT,
            query=_hub_query(),
        )
        assert "B@2---C@3@@flow" in result.connection_ids
        assert "A@1---B@2@@serving" not in result.connection_ids
        assert "D@4---B@2@@access" not in result.connection_ids

    def test_inbound_to_hub_returns_a_and_d(self) -> None:
        result = derive(
            params={
                "entity_ids": ["B@2"],
                "pre_filters": {"direction": "inbound"},
            },
            snapshot=_SNAPSHOT,
            query=_hub_query(),
        )
        assert "A@1---B@2@@serving" in result.connection_ids
        assert "D@4---B@2@@access" in result.connection_ids
        assert "B@2---C@3@@flow" not in result.connection_ids

    def test_invalid_direction_defaults_to_any(self) -> None:
        result = derive(
            params={
                "entity_ids": ["B@2"],
                "pre_filters": {"direction": "sideways"},
            },
            snapshot=_SNAPSHOT,
            query=_hub_query(),
        )
        assert len(result.connection_ids) == 3


class TestIncidentConnectionsTypeFilter:
    def test_filter_to_serving_excludes_flow_and_access(self) -> None:
        result = derive(
            params={
                "entity_ids": ["B@2"],
                "pre_filters": {"connection_types": ["serving"]},
            },
            snapshot=_SNAPSHOT,
            query=_hub_query(),
        )
        assert "A@1---B@2@@serving" in result.connection_ids
        assert "B@2---C@3@@flow" not in result.connection_ids
        assert "D@4---B@2@@access" not in result.connection_ids

    def test_filter_to_multiple_types(self) -> None:
        result = derive(
            params={
                "entity_ids": ["B@2"],
                "pre_filters": {"connection_types": ["serving", "flow"]},
            },
            snapshot=_SNAPSHOT,
            query=_hub_query(),
        )
        assert "A@1---B@2@@serving" in result.connection_ids
        assert "B@2---C@3@@flow" in result.connection_ids
        assert "D@4---B@2@@access" not in result.connection_ids

    def test_no_type_filter_returns_all(self) -> None:
        result = derive(
            params={"entity_ids": ["B@2"]},
            snapshot=_SNAPSHOT,
            query=_hub_query(),
        )
        assert len(result.connection_ids) == 3

    def test_multiple_input_entities_deduplicates_connections(self) -> None:
        """A and B share the A→B connection; frozenset guarantees no duplicates."""
        result = derive(
            params={"entity_ids": ["A@1", "B@2"]},
            snapshot=_SNAPSHOT,
            query=_hub_query(),
        )
        assert "A@1---B@2@@serving" in result.connection_ids
        assert len([c for c in result.connection_ids if "A@1---B@2" in c]) == 1
