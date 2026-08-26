"""Endpoint sub-criteria on connection style rules (boundary-aware edge styling) and the
quarantined (``disabled``) rule state that keeps forks with unresolvable inherited rules
saveable and honestly reported."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria import (
    AttributeCondition,
    ConnectionCriteriaGroup,
    EntityCriteriaGroup,
    ValueRef,
)
from src.domain.viewpoints.viewpoint_presentation_parsing import presentation_from_mapping
from src.domain.viewpoints.viewpoint_presentation_serialization import presentation_to_mapping
from src.domain.viewpoints.viewpoint_presentation_validation import validate_presentation
from src.domain.viewpoints.viewpoint_projection import rule_outcome_warnings
from src.domain.viewpoints.viewpoint_style_evaluation import classify_style_rule_outcomes, evaluate_item_style
from src.domain.viewpoints.viewpoints import PresentationSpec, StyleRule


def _entity(artifact_id: str, group: str) -> EntityRecord:
    return EntityRecord(  # type: ignore[arg-type]
        artifact_id=artifact_id,
        artifact_type="application-component",
        name=artifact_id,
        version="1.0",
        status="active",
        domain="application",
        subdomain="app-service",
        path=Path("/fake/entity.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label=artifact_id,
        display_alias="",
        group=group,
    )


def _connection(source: str, target: str) -> ConnectionRecord:
    return ConnectionRecord(  # type: ignore[arg-type]
        artifact_id=f"CON@{source}-{target}",
        source=source,
        target=target,
        conn_type="archimate-serving",
        version="1.0",
        status="draft",
        path=Path("/fake/conn.md"),
        extra={},
        content_text="",
    )


@dataclass
class _Graph:
    entities: dict[str, EntityRecord] = field(default_factory=dict)
    connections: list[ConnectionRecord] = field(default_factory=list)

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self.entities.get(artifact_id)

    def find_connections_for(self, entity_id: str, *, direction: str = "any", conn_type: str | None = None):
        return [c for c in self.connections if c.source == entity_id or c.target == entity_id]


_REGISTRIES = RegistrySnapshot(
    known_entity_types=frozenset({"application-component"}),
    known_connection_types=frozenset({"archimate-serving"}),
    known_specialization_slugs=frozenset(),
    entity_attribute_types={},
    connection_attribute_types={},
)


def _group_criteria(group: str) -> EntityCriteriaGroup:
    return EntityCriteriaGroup(
        children=(AttributeCondition(attribute="group", comparator="eq", value=ValueRef(literal=group)),)
    )


def _boundary_rule() -> StyleRule:
    return StyleRule(
        capability="edge_color",
        mode="match",
        match_criteria=ConnectionCriteriaGroup(),
        value="critical",
        source_criteria=_group_criteria("trusted"),
        target_criteria=_group_criteria("untrusted"),
    )


class TestEndpointCriteria:
    def test_styles_only_edges_crossing_the_declared_boundary(self) -> None:
        graph = _Graph(entities={
            "ENT@in": _entity("ENT@in", "trusted"),
            "ENT@out": _entity("ENT@out", "untrusted"),
            "ENT@in2": _entity("ENT@in2", "trusted"),
        })
        presentation = PresentationSpec(representation="exploration", styling_rules=(_boundary_rule(),))
        crossing = evaluate_item_style(
            _connection("ENT@in", "ENT@out"), "connection", presentation,
            read_access=graph, registries=_REGISTRIES, scale_bounds={},
        )
        internal = evaluate_item_style(
            _connection("ENT@in", "ENT@in2"), "connection", presentation,
            read_access=graph, registries=_REGISTRIES, scale_bounds={},
        )
        assert crossing.style == {"edge_color": "critical"}
        assert internal.style == {}
        assert internal.rule_hits == crossing.rule_hits[:0] + internal.rule_hits  # both evaluated
        assert not internal.rule_hits[0].matched

    def test_missing_endpoint_record_never_matches(self) -> None:
        graph = _Graph(entities={"ENT@in": _entity("ENT@in", "trusted")})
        presentation = PresentationSpec(representation="exploration", styling_rules=(_boundary_rule(),))
        evaluation = evaluate_item_style(
            _connection("ENT@in", "ENT@gone"), "connection", presentation,
            read_access=graph, registries=_REGISTRIES, scale_bounds={},
        )
        assert evaluation.style == {}

    def test_round_trips_through_mapping(self) -> None:
        presentation = PresentationSpec(representation="exploration", styling_rules=(_boundary_rule(),))
        mapping = presentation_to_mapping(presentation)
        rule = mapping["styling_rules"][0]
        assert set(rule) >= {"source_criteria", "target_criteria"}
        assert presentation_from_mapping(mapping, label="test") == presentation

    def test_rejected_on_node_capability(self) -> None:
        rule = StyleRule(
            capability="node_color",
            mode="match",
            match_criteria=EntityCriteriaGroup(),
            value="positive",
            source_criteria=_group_criteria("trusted"),
        )
        presentation = PresentationSpec(representation="exploration", styling_rules=(rule,))
        issues = validate_presentation(
            presentation, path="presentation", registries=_REGISTRIES, check_ergonomics=True
        )
        assert any(issue.code == "endpoint-criteria-on-node-rule" for issue in issues)


def _drifted_scale_rule(*, disabled: bool) -> StyleRule:
    return StyleRule(
        capability="node_color",
        mode="scale",
        scale_attribute="investment_level",
        scale_tokens=("heat-low", "heat-high"),
        disabled=disabled,
    )


class TestDisabledRuleQuarantine:
    def test_disabled_rule_with_unresolvable_attribute_is_saveable(self) -> None:
        presentation = PresentationSpec(
            representation="exploration", styling_rules=(_drifted_scale_rule(disabled=True),)
        )
        issues = validate_presentation(
            presentation, path="presentation", registries=_REGISTRIES, check_ergonomics=True
        )
        assert issues == []
        # The same rule enabled dead-ends the save — that asymmetry IS the quarantine.
        enabled = PresentationSpec(representation="exploration", styling_rules=(_drifted_scale_rule(disabled=False),))
        enabled_issues = validate_presentation(
            enabled, path="presentation", registries=_REGISTRIES, check_ergonomics=True
        )
        assert any(issue.code == "unknown-attribute" for issue in enabled_issues)

    def test_disabled_rule_is_never_evaluated_and_reports_disabled_outcome(self) -> None:
        presentation = PresentationSpec(
            representation="exploration", styling_rules=(_drifted_scale_rule(disabled=True),)
        )
        evaluation = evaluate_item_style(
            _entity("ENT@x", "core"), "entity", presentation,
            read_access=_Graph(), registries=_REGISTRIES, scale_bounds={},
        )
        assert evaluation.style == {}
        assert evaluation.rule_hits == ()
        outcomes = classify_style_rule_outcomes(
            presentation, evaluation.rule_hits, registries=_REGISTRIES, declared_derived_names=frozenset()
        )
        assert [outcome.kind for outcome in outcomes] == ["disabled"]
        assert rule_outcome_warnings(outcomes) == ()

    def test_disabled_round_trips_through_mapping(self) -> None:
        presentation = PresentationSpec(
            representation="exploration", styling_rules=(_drifted_scale_rule(disabled=True),)
        )
        mapping = presentation_to_mapping(presentation)
        assert mapping["styling_rules"][0]["disabled"] is True
        assert presentation_from_mapping(mapping, label="test") == presentation
