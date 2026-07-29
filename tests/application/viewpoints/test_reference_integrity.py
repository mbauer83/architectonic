"""Acceptance test for viewpoint reference integrity (the whole-stream contract).

The load-bearing invariant: a viewpoint whose criteria reference a model element that has
disappeared (here, a retired entity type) must be LOUDLY DEGRADED — the breakage surfaces
in the execution warnings AND absence claims are suppressed — never a silent empty pass
indistinguishable from a legitimately empty result. A broken query returning zero rows must
never read as a clean bill of health.
"""

from __future__ import annotations

from src.application.viewpoints.evaluate_viewpoint import ViewpointExecutionRequest, evaluate_viewpoint
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, EntityCriteriaGroup, ValueRef
from src.domain.viewpoints.viewpoint_reference_report import reference_report
from src.domain.viewpoints.viewpoints import (
    ExecutableViewpointQuery,
    PresentationSpec,
    ViewpointCatalog,
    ViewpointDefinition,
)
from tests.application.viewpoints._fixtures import Store, entity

_EXECUTION_DEFAULTS: dict[str, object] = {
    "max_entities": 500,
    "default_limit": 500,
    "timeout_seconds": 10.0,
}


def _widget_view() -> ViewpointDefinition:
    """A query-mode view selecting entities of type ``widget`` and declaring ``widget`` as
    its target population, so absence claims are possible when the type is known."""
    return ViewpointDefinition(
        slug="widgets",
        version=1,
        name="Widgets",
        selection_mode="query",
        query=ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(
                children=(
                    AttributeCondition(attribute="type", comparator="eq", value=ValueRef(literal="widget")),
                )
            )
        ),
        presentation=PresentationSpec(representation="table", target_types=("widget",)),
    )


def _registries(*, widget_known: bool) -> RegistrySnapshot:
    types = {"process"} | ({"widget"} if widget_known else set())
    return RegistrySnapshot(
        known_entity_types=frozenset(types),
        known_connection_types=frozenset({"archimate-serving"}),
        known_specialization_slugs=frozenset(),
        entity_attribute_types={},
        connection_attribute_types={},
    )


def _execute(definition: ViewpointDefinition, store: Store, registries: RegistrySnapshot, *, generation: int):
    # Distinct generations model distinct model states: retiring a type is itself a model
    # revision, so the two cases below never share a memoisation key.
    return evaluate_viewpoint(
        ViewpointExecutionRequest(slug=definition.slug),
        catalog=ViewpointCatalog((definition,)),
        read_access=store,
        registries=registries,
        index_generation=generation,
        **_EXECUTION_DEFAULTS,
    )


def test_known_type_empty_result_is_a_legitimate_empty_pass() -> None:
    """The type exists, the model simply has no instances: zero rows is honest. No
    reference warning, and the declared target population is reported (a truthful
    "0 widgets present"), not suppressed."""
    definition = _widget_view()
    store = Store(entities={"ENT@p": entity(artifact_id="ENT@p", artifact_type="process")})
    registries = _registries(widget_known=True)

    assert reference_report(definition, registries=registries, read_access=store) == ()

    result = _execute(definition, store, registries, generation=7)
    assert result.total_entity_count == 0
    assert result.target_population is not None
    assert not any("widget" in warning for warning in result.warnings)


def test_retired_type_is_loudly_degraded_not_a_silent_empty_pass() -> None:
    """The referenced type has been retired. The identical zero-row result must now be
    reported (a warning naming the broken type) AND must suppress absence claims
    (target_population is None) — the two halves of invariant I-R1."""
    definition = _widget_view()
    store = Store(entities={"ENT@p": entity(artifact_id="ENT@p", artifact_type="process")})
    registries = _registries(widget_known=False)

    report = reference_report(definition, registries=registries, read_access=store)
    assert any(broken.reference == "widget" and broken.kind == "entity-type" for broken in report)

    result = _execute(definition, store, registries, generation=8)
    assert result.total_entity_count == 0
    # I-R1, half one: the breakage surfaces loudly.
    assert any("widget" in warning for warning in result.warnings)
    # I-R1, half two: no clean bill of health — absence claims are suppressed.
    assert result.target_population is None
