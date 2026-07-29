"""Unit tests for the pure ``reference_report`` over every authored reference class."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.viewpoints.viewpoint_bindings import QueryParameter
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria import (
    AttributeCondition,
    ConnectionCriteriaGroup,
    ConnectionSelection,
    EntityCriteriaGroup,
    IncidentConnectionCondition,
    NeighborInclusion,
    ValueRef,
)
from src.domain.viewpoints.viewpoint_reference_report import (
    BrokenReference,
    reference_report,
    reference_report_warnings,
)
from src.domain.viewpoints.viewpoints import (
    ColumnSpec,
    ExecutableViewpointQuery,
    PresentationSpec,
    StyleRule,
    ViewpointDefinition,
)


@dataclass
class _Store:
    """Minimal ``CriteriaReadAccess`` stub — reference_report only calls ``get_entity``."""

    entities: dict[str, EntityRecord] = field(default_factory=dict)

    def get_entity(self, artifact_id: str) -> EntityRecord | None:
        return self.entities.get(artifact_id)

    def get_connection(self, artifact_id: str) -> ConnectionRecord | None:
        return None

    def find_connections_for(
        self, entity_id: str, *, direction: Literal["any", "outbound", "inbound"] = "any", conn_type: str | None = None
    ) -> list[ConnectionRecord]:
        return []


def _entity(artifact_id: str) -> EntityRecord:
    return EntityRecord(
        artifact_id=artifact_id,
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


_REGISTRIES = RegistrySnapshot(
    known_entity_types=frozenset({"application-component", "process"}),
    known_connection_types=frozenset({"archimate-serving"}),
    known_specialization_slugs=frozenset({"critical"}),
    entity_attribute_types={"risk.score": "number"},
    connection_attribute_types={"weight": "number"},
    entity_type_infos={},
)


def _definition(
    *, query: ExecutableViewpointQuery, presentation: PresentationSpec | None = None
) -> ViewpointDefinition:
    return ViewpointDefinition(
        slug="v", version=1, name="V", selection_mode="query", query=query, presentation=presentation
    )


def _report(definition: ViewpointDefinition, store: _Store | None = None) -> tuple[BrokenReference, ...]:
    return reference_report(definition, registries=_REGISTRIES, read_access=store or _Store())


def _type_condition(value: str) -> AttributeCondition:
    return AttributeCondition(attribute="type", comparator="eq", value=ValueRef(literal=value))


def test_clean_definition_reports_nothing() -> None:
    query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup(children=(_type_condition("process"),)))
    assert _report(_definition(query=query)) == ()


def test_retired_entity_type_value_in_criteria() -> None:
    query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup(children=(_type_condition("gone"),)))
    report = _report(_definition(query=query))
    assert [(b.kind, b.reference) for b in report] == [("entity-type", "gone")]
    assert report[0].severity == "ontology"


def test_unknown_specialization_value_in_criteria() -> None:
    condition = AttributeCondition(
        attribute="specialization", comparator="in", value=ValueRef(literal=["critical", "ghost"])
    )
    query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup(children=(condition,)))
    report = _report(_definition(query=query))
    assert [(b.kind, b.reference) for b in report] == [("specialization", "ghost")]


def test_unresolvable_attribute_path_in_criteria() -> None:
    condition = AttributeCondition(attribute="risk.missing", comparator="gt", value=ValueRef(literal=1))
    query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup(children=(condition,)))
    report = _report(_definition(query=query))
    assert [(b.kind, b.reference) for b in report] == [("attribute-path", "risk.missing")]


def test_retired_connection_type_in_connection_selection() -> None:
    query = ExecutableViewpointQuery(
        connections=ConnectionSelection(
            criteria=ConnectionCriteriaGroup(
                children=(AttributeCondition(attribute="type", comparator="eq", value=ValueRef(literal="gone-conn")),)
            )
        )
    )
    report = _report(_definition(query=query))
    assert [(b.kind, b.reference) for b in report] == [("connection-type", "gone-conn")]


def test_incident_connection_condition_walks_both_legs() -> None:
    incident = IncidentConnectionCondition(
        connection_criteria=ConnectionCriteriaGroup(
            children=(AttributeCondition(attribute="type", comparator="eq", value=ValueRef(literal="gone-conn")),)
        ),
        endpoint_criteria=EntityCriteriaGroup(children=(_type_condition("gone-endpoint"),)),
    )
    query = ExecutableViewpointQuery(entity_criteria=EntityCriteriaGroup(children=(incident,)))
    report = _report(_definition(query=query))
    kinds = {(b.kind, b.reference) for b in report}
    assert kinds == {("connection-type", "gone-conn"), ("entity-type", "gone-endpoint")}


def test_neighbor_inclusion_criteria() -> None:
    query = ExecutableViewpointQuery(
        include_connected=(
            NeighborInclusion(neighbor_criteria=EntityCriteriaGroup(children=(_type_condition("gone"),))),
        )
    )
    assert [b.reference for b in _report(_definition(query=query))] == ["gone"]


def test_style_rule_applies_to_slugs() -> None:
    presentation = PresentationSpec(
        representation="exploration",
        styling_rules=(StyleRule(capability="node_color", applies_to=frozenset({"process", "phantom"}), value="red"),),
    )
    query = ExecutableViewpointQuery()
    report = _report(_definition(query=query, presentation=presentation))
    # 'phantom' is neither a known type nor a known specialization slug; a node capability
    # scopes applies_to by entity context.
    assert [(b.kind, b.reference) for b in report] == [("entity-type", "phantom")]


def test_disabled_style_rule_is_quarantined_not_reported() -> None:
    presentation = PresentationSpec(
        representation="exploration",
        styling_rules=(
            StyleRule(
                capability="node_color", applies_to=frozenset({"phantom"}), value="red", disabled=True
            ),
        ),
    )
    assert _report(_definition(query=ExecutableViewpointQuery(), presentation=presentation)) == ()


def test_matrix_axis_and_column_and_target_type_references() -> None:
    presentation = PresentationSpec(
        representation="table",
        columns=(ColumnSpec(label="Risk", source="risk.missing"),),
        target_types=("gone",),
    )
    report = _report(_definition(query=ExecutableViewpointQuery(), presentation=presentation))
    kinds = {(b.kind, b.reference) for b in report}
    assert kinds == {("attribute-path", "risk.missing"), ("entity-type", "gone")}


def test_entity_id_parameter_default_is_checked_against_the_read_model() -> None:
    query = ExecutableViewpointQuery(
        parameters=(
            QueryParameter(name="anchor", value_type="entity-id", required=False, default="ENT@1.gone"),
        )
    )
    report = _report(_definition(query=query))
    assert [(b.kind, b.reference) for b in report] == [("entity-id", "ENT@1.gone")]
    assert report[0].severity == "entity-id"


def test_entity_id_parameter_default_resolves_on_stable_short_id_despite_rename() -> None:
    # Stored default carries a stale slug; the live entity is keyed by its rename-stable
    # short id in the index — a rename, not a break.
    store = _Store(entities={"ENT@1700000000.abc123": _entity("ENT@1700000000.abc123")})
    query = ExecutableViewpointQuery(
        parameters=(
            QueryParameter(
                name="anchor", value_type="entity-id", required=False, default="ENT@1700000000.abc123.old-name"
            ),
        )
    )
    assert _report(_definition(query=query), store) == ()


def test_warnings_exclude_attribute_paths_but_cover_silent_classes() -> None:
    query = ExecutableViewpointQuery(
        entity_criteria=EntityCriteriaGroup(
            children=(
                _type_condition("gone"),
                AttributeCondition(attribute="risk.missing", comparator="gt", value=ValueRef(literal=1)),
            )
        )
    )
    report = _report(_definition(query=query))
    warnings = reference_report_warnings(report)
    assert any("gone" in warning for warning in warnings)
    assert not any("risk.missing" in warning for warning in warnings)


def test_cross_tier_reference_reports_at_destination_tier() -> None:
    # An engagement-local type referenced from a registry that no longer knows it (the
    # enterprise destination tier after promotion) reports exactly as a retired type does.
    query = ExecutableViewpointQuery(
        entity_criteria=EntityCriteriaGroup(children=(_type_condition("engagement-local-type"),))
    )
    report = _report(_definition(query=query))
    assert [(b.kind, b.reference) for b in report] == [("entity-type", "engagement-local-type")]
