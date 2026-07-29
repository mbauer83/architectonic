"""Unit tests for style-rule evaluation (companion plan §5.2): Appendix-C "Style rules"
cluster — first-match-wins ordering, ``applies_to`` scoping, half-open range bands,
``default_style`` fallback, and relational styling via ``IncidentConnectionCondition``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria import (
    AttributeCondition,
    ConnectionCriteriaGroup,
    EntityCriteriaGroup,
    IncidentConnectionCondition,
    ValueRef,
)
from src.domain.viewpoints.viewpoint_evaluation_context import CriteriaReadAccess, EvaluationEnvironment
from src.domain.viewpoints.viewpoint_style_evaluation import (
    Item,
    ItemKind,
    ScaleBounds,
    StyleValue,
    evaluate_item_style,
)
from src.domain.viewpoints.viewpoints import PresentationSpec, RangeBand, StyleRule


def _style_and_drift(
    item: Item,
    item_kind: ItemKind,
    presentation: PresentationSpec | None,
    *,
    read_access: CriteriaReadAccess,
    registries: RegistrySnapshot,
    environment: EvaluationEnvironment = EvaluationEnvironment(),
    scale_bounds: Mapping[int, ScaleBounds] = {},
) -> tuple[Mapping[str, StyleValue], frozenset[str]]:
    evaluation = evaluate_item_style(
        item,
        item_kind,
        presentation,
        read_access=read_access,
        registries=registries,
        environment=environment,
        scale_bounds=scale_bounds,
    )
    return evaluation.style, evaluation.schema_drift


def _entity(**kw: object) -> EntityRecord:
    defaults: dict[str, object] = dict(
        artifact_id="ENT@A",
        artifact_type="application-component",
        name="A",
        version="1.0",
        status="draft",
        domain="application",
        subdomain="app-service",
        path=Path("/fake/entity.md"),
        keywords=(),
        extra={},
        content_text="",
        display_blocks={},
        display_label="A",
        display_alias="",
    )
    defaults.update(kw)
    return EntityRecord(**defaults)  # type: ignore[arg-type]


def _connection(**kw: object) -> ConnectionRecord:
    defaults: dict[str, object] = dict(
        artifact_id="CON@001",
        source="ENT@A",
        target="ENT@B",
        conn_type="archimate-serving",
        version="1.0",
        status="draft",
        path=Path("/fake/conn.md"),
        extra={},
        content_text="",
    )
    defaults.update(kw)
    return ConnectionRecord(**defaults)  # type: ignore[arg-type]


@dataclass
class _Graph:
    entities: dict[str, EntityRecord] = field(default_factory=dict)
    connections: list[ConnectionRecord] = field(default_factory=list)

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self.entities.get(artifact_id)

    def find_connections_for(self, entity_id: str, *, direction: str = "any", conn_type: str | None = None):
        return [c for c in self.connections if c.source == entity_id or c.target == entity_id]


_REGISTRIES = RegistrySnapshot(
    known_entity_types=frozenset({"application-component", "process"}),
    known_connection_types=frozenset({"archimate-serving"}),
    known_specialization_slugs=frozenset(),
    entity_attribute_types={"risk_score": "number"},
    connection_attribute_types={},
)


def _status_rule(capability: str, status: str, value: str) -> StyleRule:
    return StyleRule(
        capability=capability,
        mode="match",
        match_criteria=EntityCriteriaGroup(
            children=(AttributeCondition(attribute="status", comparator="eq", value=ValueRef(literal=status)),)
        ),
        value=value,
    )


class TestFirstMatchWins:
    def test_first_matching_rule_per_capability_wins(self) -> None:
        entity = _entity(status="deprecated")
        presentation = PresentationSpec(
            representation="table",
            styling_rules=(
                _status_rule("badges", "deprecated", "badge-warning"),
                _status_rule("badges", "deprecated", "badge-danger"),  # would also match — ignored
            ),
        )
        style, drift = _style_and_drift(
            entity, "entity", presentation, read_access=_Graph(), registries=_REGISTRIES
        )
        assert style == {"badges": "badge-warning"}
        assert drift == frozenset()

    def test_non_matching_rule_falls_through_to_next(self) -> None:
        entity = _entity(status="active")
        presentation = PresentationSpec(
            representation="table",
            styling_rules=(
                _status_rule("badges", "deprecated", "badge-warning"),
                _status_rule("badges", "active", "badge-ok"),
            ),
        )
        style, _ = _style_and_drift(entity, "entity", presentation, read_access=_Graph(), registries=_REGISTRIES)
        assert style == {"badges": "badge-ok"}


class TestDefaultStyle:
    def test_no_rule_matches_falls_back_to_default(self) -> None:
        entity = _entity(status="active")
        presentation = PresentationSpec(
            representation="table",
            styling_rules=(_status_rule("badges", "deprecated", "badge-warning"),),
            default_style={"badges": "badge-neutral"},
        )
        style, _ = _style_and_drift(entity, "entity", presentation, read_access=_Graph(), registries=_REGISTRIES)
        assert style == {"badges": "badge-neutral"}


class TestAppliesToScoping:
    def test_rule_scoped_to_other_type_does_not_apply(self) -> None:
        entity = _entity(artifact_type="application-component", status="deprecated")
        rule = _status_rule("badges", "deprecated", "badge-warning")
        rule = StyleRule(
            capability=rule.capability,
            applies_to=frozenset({"process"}),
            mode=rule.mode,
            match_criteria=rule.match_criteria,
            value=rule.value,
        )
        presentation = PresentationSpec(representation="table", styling_rules=(rule,))
        style, _ = _style_and_drift(entity, "entity", presentation, read_access=_Graph(), registries=_REGISTRIES)
        assert style == {}

    def test_rule_scoped_to_matching_type_applies(self) -> None:
        entity = _entity(artifact_type="application-component", status="deprecated")
        rule = _status_rule("badges", "deprecated", "badge-warning")
        rule = StyleRule(
            capability=rule.capability,
            applies_to=frozenset({"application-component"}),
            mode=rule.mode,
            match_criteria=rule.match_criteria,
            value=rule.value,
        )
        presentation = PresentationSpec(representation="table", styling_rules=(rule,))
        style, _ = _style_and_drift(entity, "entity", presentation, read_access=_Graph(), registries=_REGISTRIES)
        assert style == {"badges": "badge-warning"}

    def test_rule_scoped_to_a_non_primary_specialization_applies(self) -> None:
        # WU-V3: `applies_to` matches ANY of a concept's specializations, not only the first.
        entity = _entity(status="deprecated", specializations=("service", "audited"))
        rule = _status_rule("badges", "deprecated", "badge-warning")
        rule = StyleRule(
            capability=rule.capability,
            applies_to=frozenset({"audited"}),  # the SECOND specialization
            mode=rule.mode,
            match_criteria=rule.match_criteria,
            value=rule.value,
        )
        presentation = PresentationSpec(representation="table", styling_rules=(rule,))
        style, _ = _style_and_drift(entity, "entity", presentation, read_access=_Graph(), registries=_REGISTRIES)
        assert style == {"badges": "badge-warning"}


class TestRangeBands:
    _BANDS = (
        RangeBand(minimum=None, maximum=4, value="badge-ok"),
        RangeBand(minimum=4, maximum=7, value="badge-caution"),
        RangeBand(minimum=7, maximum=None, value="badge-danger"),
    )

    def _presentation(self) -> PresentationSpec:
        return PresentationSpec(
            representation="table",
            styling_rules=(
                StyleRule(capability="badges", mode="range", range_attribute="risk_score", range_bands=self._BANDS),
            ),
        )

    def test_half_open_lower_boundary_included(self) -> None:
        entity = _entity(extra={"risk_score": 4})
        style, _ = _style_and_drift(
            entity, "entity", self._presentation(), read_access=_Graph(), registries=_REGISTRIES
        )
        assert style == {"badges": "badge-caution"}

    def test_half_open_upper_boundary_excluded(self) -> None:
        entity = _entity(extra={"risk_score": 7})
        style, _ = _style_and_drift(
            entity, "entity", self._presentation(), read_access=_Graph(), registries=_REGISTRIES
        )
        assert style == {"badges": "badge-danger"}

    def test_unbounded_band_matches_extreme_value(self) -> None:
        entity = _entity(extra={"risk_score": 0})
        style, _ = _style_and_drift(
            entity, "entity", self._presentation(), read_access=_Graph(), registries=_REGISTRIES
        )
        assert style == {"badges": "badge-ok"}

    def test_missing_attribute_falls_back_to_default(self) -> None:
        entity = _entity(extra={})
        presentation = PresentationSpec(
            representation="table",
            styling_rules=(
                StyleRule(capability="badges", mode="range", range_attribute="risk_score", range_bands=self._BANDS),
            ),
            default_style={"badges": "badge-neutral"},
        )
        style, _ = _style_and_drift(entity, "entity", presentation, read_access=_Graph(), registries=_REGISTRIES)
        assert style == {"badges": "badge-neutral"}

    def test_out_of_band_value_falls_back_to_default(self) -> None:
        bands = (RangeBand(minimum=0, maximum=1, value="badge-ok"),)
        entity = _entity(extra={"risk_score": 99})
        rule = StyleRule(capability="badges", mode="range", range_attribute="risk_score", range_bands=bands)
        presentation = PresentationSpec(
            representation="table", styling_rules=(rule,), default_style={"badges": "badge-neutral"}
        )
        style, _ = _style_and_drift(entity, "entity", presentation, read_access=_Graph(), registries=_REGISTRIES)
        assert style == {"badges": "badge-neutral"}


class TestRelationalStyling:
    def test_incident_condition_in_match_criteria_styles_matching_entities(self) -> None:
        served = _entity(artifact_id="ENT@served", artifact_type="process")
        server = _entity(artifact_id="ENT@server", artifact_type="application-component")
        idle = _entity(artifact_id="ENT@idle", artifact_type="application-component")
        connection = _connection(artifact_id="CON@1", source="ENT@server", target="ENT@served")
        graph = _Graph(
            entities={"ENT@served": served, "ENT@server": server, "ENT@idle": idle}, connections=[connection]
        )
        rule = StyleRule(
            capability="node_color",
            mode="match",
            match_criteria=EntityCriteriaGroup(
                children=(
                    IncidentConnectionCondition(
                        direction="outgoing",
                        connection_criteria=ConnectionCriteriaGroup(),
                        endpoint_criteria=EntityCriteriaGroup(
                            children=(
                                AttributeCondition(
                                    attribute="type", comparator="eq", value=ValueRef(literal="process")
                                ),
                            )
                        ),
                    ),
                )
            ),
            value="highlight",
        )
        presentation = PresentationSpec(representation="exploration", styling_rules=(rule,))
        style_server, _ = _style_and_drift(
            server, "entity", presentation, read_access=graph, registries=_REGISTRIES
        )
        style_idle, _ = _style_and_drift(idle, "entity", presentation, read_access=graph, registries=_REGISTRIES)
        assert style_server == {"node_color": "highlight"}
        assert style_idle == {}


class TestConnectionStyling:
    def test_edge_capability_styles_matching_connection(self) -> None:
        connection = _connection(conn_type="archimate-serving")
        rule = StyleRule(
            capability="edge_color",
            mode="match",
            match_criteria=ConnectionCriteriaGroup(
                children=(
                    AttributeCondition(attribute="type", comparator="eq", value=ValueRef(literal="archimate-serving")),
                )
            ),
            value="blue",
        )
        presentation = PresentationSpec(representation="exploration", styling_rules=(rule,))
        style, _ = _style_and_drift(
            connection, "connection", presentation, read_access=_Graph(), registries=_REGISTRIES
        )
        assert style == {"edge_color": "blue"}

    def test_node_capability_rule_is_skipped_for_connections(self) -> None:
        # Regression: a node-scoped rule (entity match criteria) must never be evaluated
        # against a connection. Previously every rule was tried against every item, so a
        # `node_color` match rule reached a connection and tripped the
        # ConnectionCriteriaGroup assert, 500-ing the whole projection. status="draft"
        # would *match* if evaluated — so an empty result proves it was skipped by kind,
        # not merely unmatched.
        connection = _connection(status="draft")
        node_rule = _status_rule("node_color", "draft", "highlight")
        presentation = PresentationSpec(representation="exploration", styling_rules=(node_rule,))
        style, drift = _style_and_drift(
            connection, "connection", presentation, read_access=_Graph(), registries=_REGISTRIES
        )
        assert style == {}
        assert drift == frozenset()

    def test_mixed_node_and_edge_rules_apply_only_to_their_kind(self) -> None:
        node_rule = _status_rule("node_color", "draft", "highlight")
        edge_rule = StyleRule(
            capability="edge_color",
            mode="match",
            match_criteria=ConnectionCriteriaGroup(
                children=(
                    AttributeCondition(attribute="type", comparator="eq", value=ValueRef(literal="archimate-serving")),
                )
            ),
            value="blue",
        )
        presentation = PresentationSpec(representation="exploration", styling_rules=(node_rule, edge_rule))
        entity_style, _ = _style_and_drift(
            _entity(status="draft"), "entity", presentation, read_access=_Graph(), registries=_REGISTRIES
        )
        connection_style, _ = _style_and_drift(
            _connection(status="draft"), "connection", presentation, read_access=_Graph(), registries=_REGISTRIES
        )
        assert entity_style == {"node_color": "highlight"}
        assert connection_style == {"edge_color": "blue"}


class TestNoPresentation:
    def test_none_presentation_yields_empty_style(self) -> None:
        entity = _entity()
        style, drift = _style_and_drift(entity, "entity", None, read_access=_Graph(), registries=_REGISTRIES)
        assert style == {}
        assert drift == frozenset()


class TestSchemaDrift:
    def test_range_attribute_unknown_at_evaluation_time_yields_drift(self) -> None:
        entity = _entity(extra={})
        presentation = PresentationSpec(
            representation="table",
            styling_rules=(
                StyleRule(
                    capability="badges",
                    mode="range",
                    range_attribute="unknown_field",
                    range_bands=(RangeBand(minimum=None, maximum=None, value="x"),),
                ),
            ),
        )
        _, drift = _style_and_drift(entity, "entity", presentation, read_access=_Graph(), registries=_REGISTRIES)
        assert drift == frozenset({"unknown_field"})
