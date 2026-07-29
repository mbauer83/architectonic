"""Signal-attribute declaration grammar: parse/serialize round-trip, strict
key validation (graph keys forbidden with a signal source and vice versa),
source-mix duplicate names rejected (F3.10), and the execution partition."""

from __future__ import annotations

import pytest

from src.domain.viewpoints.viewpoint_binding_validation import validate_query_values
from src.domain.viewpoints.viewpoint_bindings import DerivedAttribute
from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, EntityCriteriaGroup, ValueRef
from src.domain.viewpoints.viewpoint_derived_attribute_deferral import partition_derived_attributes
from src.domain.viewpoints.viewpoint_query_parsing import query_from_mapping
from src.domain.viewpoints.viewpoint_query_serialization import query_to_mapping
from src.domain.viewpoints.viewpoints import QUERY_SCHEMA_VERSION, ExecutableViewpointQuery


def _query_mapping(derived: list[dict[str, object]]) -> dict[str, object]:
    return {
        "query_schema": QUERY_SCHEMA_VERSION,
        "entity_criteria": {"kind": "group", "children": []},
        "derived": derived,
    }


class TestParsing:
    def test_signal_attribute_round_trips(self) -> None:
        raw = _query_mapping([
            {"name": "open_vulns", "source": "security-signal",
             "metric": "distinct_open_vulnerabilities"},
            {"name": "dependents", "reduce": "count"},
        ])
        query = query_from_mapping(raw, label="query")
        signal = query.derived[0]
        assert signal.source == "security-signal"
        assert signal.metric == "distinct_open_vulnerabilities"
        assert query.derived[1].source == "graph"
        serialized = query_to_mapping(query)
        assert serialized["derived"][0] == {  # type: ignore[index]
            "name": "open_vulns", "source": "security-signal",
            "metric": "distinct_open_vulnerabilities",
        }
        assert query_from_mapping(serialized, label="query") == query

    def test_signal_source_requires_a_metric(self) -> None:
        with pytest.raises(ValueError, match="requires a metric"):
            query_from_mapping(_query_mapping([
                {"name": "x", "source": "security-signal"},
            ]), label="query")

    def test_signal_source_forbids_graph_keys(self) -> None:
        with pytest.raises(ValueError, match="graph keys"):
            query_from_mapping(_query_mapping([
                {"name": "x", "source": "security-signal", "metric": "finding_total",
                 "reduce": "sum", "of": "attr"},
            ]), label="query")

    def test_metric_is_invalid_on_a_graph_attribute(self) -> None:
        with pytest.raises(ValueError, match="only valid with source"):
            query_from_mapping(_query_mapping([
                {"name": "x", "metric": "finding_total"},
            ]), label="query")

    def test_unknown_source_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="source is unknown"):
            query_from_mapping(_query_mapping([
                {"name": "x", "source": "weather"},
            ]), label="query")


class TestSourceMixValidation:
    def test_duplicate_names_across_sources_are_rejected(self) -> None:
        from tests.application.viewpoints._fixtures import REGISTRIES

        issues, _types = validate_query_values(
            bindings=(),
            parameters=(),
            derived=(
                DerivedAttribute(name="risk"),
                DerivedAttribute(name="risk", source="security-signal", metric="finding_total"),
            ),
            path="query",
            registries=REGISTRIES,
            check_ergonomics=True,
            max_bindings=8,
            max_parameters=4,
            max_derived_attributes=8,
        )
        assert any("unique" in issue.message for issue in issues)

    def test_signal_attribute_declares_a_numeric_type(self) -> None:
        from tests.application.viewpoints._fixtures import REGISTRIES

        issues, types = validate_query_values(
            bindings=(),
            parameters=(),
            derived=(DerivedAttribute(name="score", source="security-signal", metric="max_cvss_score"),),
            path="query",
            registries=REGISTRIES,
            check_ergonomics=True,
            max_bindings=8,
            max_parameters=4,
            max_derived_attributes=8,
        )
        assert issues == []
        assert types.derived["score"] == "number"


class TestPartition:
    def test_partition_crosses_source_with_criteria_reference(self) -> None:
        query = ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(children=(
                AttributeCondition(attribute="derived.eager_sig", comparator="gt",
                                   value=ValueRef(literal=0)),
                AttributeCondition(attribute="derived.eager_graph", comparator="gt",
                                   value=ValueRef(literal=0)),
            )),
            derived=(
                DerivedAttribute(name="eager_sig", source="security-signal", metric="finding_total"),
                DerivedAttribute(name="lazy_sig", source="security-signal", metric="max_cvss_score"),
                DerivedAttribute(name="eager_graph"),
                DerivedAttribute(name="lazy_graph"),
            ),
        )
        partition = partition_derived_attributes(query)
        assert [a.name for a in partition.eager_signal] == ["eager_sig"]
        assert [a.name for a in partition.deferred_signal] == ["lazy_sig"]
        assert [a.name for a in partition.eager_graph] == ["eager_graph"]
        assert [a.name for a in partition.deferred_graph] == ["lazy_graph"]
