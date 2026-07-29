"""trace_patterns are wired into the query block: they parse onto ExecutableViewpointQuery,
round-trip through serialization, and registry-aware validation flags unknown types."""

from __future__ import annotations

from src.domain.viewpoints.viewpoint_query_parsing import query_from_mapping
from src.domain.viewpoints.viewpoint_query_serialization import query_to_mapping
from src.domain.viewpoints.viewpoint_trace_pattern_validation import validate_trace_pattern_types
from src.domain.viewpoints.viewpoint_trace_patterns import (
    BranchesRef,
    InlineBranches,
    NamedBranchEdge,
    StoredEdge,
    TracePattern,
    TracePatternSet,
)


def _query_mapping() -> dict:
    return {
        "query_schema": 1,
        "trace_patterns": [
            {
                "name": "motivation", "kind": "branch-complete-realization", "applies_to": ["goal", "outcome"],
                "branches": {
                    "g2o": {"kind": "stored-edge", "connection": "archimate-realization",
                            "direction": "incoming", "endpoint": {"type": "outcome"}},
                },
                "leaf": {"kind": "none"},
            },
        ],
    }


class TestQueryWiring:
    def test_trace_patterns_parse_onto_the_query(self) -> None:
        query = query_from_mapping(_query_mapping(), label="vp")
        assert [p.name for p in query.trace_patterns.patterns] == ["motivation"]

    def test_absent_trace_patterns_default_to_empty(self) -> None:
        query = query_from_mapping({"query_schema": 1}, label="vp")
        assert query.trace_patterns.patterns == ()

    def test_round_trip_through_serialization(self) -> None:
        once = query_from_mapping(_query_mapping(), label="vp")
        twice = query_from_mapping(query_to_mapping(once), label="vp")
        assert once.trace_patterns == twice.trace_patterns

    def test_empty_trace_patterns_omitted_from_serialization(self) -> None:
        query = query_from_mapping({"query_schema": 1}, label="vp")
        assert "trace_patterns" not in query_to_mapping(query)


def _pattern_set() -> TracePatternSet:
    return TracePatternSet((
        TracePattern(
            name="m", applies_to=("goal", "bogus-type"),
            branches=InlineBranches(
                (NamedBranchEdge("e", StoredEdge("archimate-realization", "incoming", "outcome")),)
            ),
        ),
        TracePattern(name="o", applies_to=("goal",), branches=BranchesRef("m")),
    ))


class TestRegistryAwareTypeValidation:
    def test_unknown_applies_to_type_flagged(self) -> None:
        issues = validate_trace_pattern_types(
            _pattern_set(),
            known_entity_types=frozenset({"goal", "outcome"}),
            known_connection_types=frozenset({"archimate-realization"}),
            path="q",
        )
        assert any(i.code == "unknown-entity-type" and "bogus-type" in i.message for i in issues)

    def test_unknown_connection_type_flagged(self) -> None:
        issues = validate_trace_pattern_types(
            _pattern_set(),
            known_entity_types=frozenset({"goal", "outcome", "bogus-type"}),
            known_connection_types=frozenset(),  # archimate-realization now unknown
            path="q",
        )
        assert any(i.code == "unknown-connection-type" for i in issues)

    def test_all_known_types_clean(self) -> None:
        issues = validate_trace_pattern_types(
            _pattern_set(),
            known_entity_types=frozenset({"goal", "outcome", "bogus-type"}),
            known_connection_types=frozenset({"archimate-realization"}),
            path="q",
        )
        assert issues == []
