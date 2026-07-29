"""Memoisation contract for ``cached_reference_report``: keyed by (index_generation,
definition digest), bypassed when the generation is unknown, self-clearing on either
change."""

from __future__ import annotations

from src.application.viewpoints.reference_report_cache import (
    cached_reference_report,
    clear_reference_report_cache,
)
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria import AttributeCondition, EntityCriteriaGroup, ValueRef
from src.domain.viewpoints.viewpoints import ExecutableViewpointQuery, ViewpointDefinition
from tests.application.viewpoints._fixtures import Store


def _definition() -> ViewpointDefinition:
    return ViewpointDefinition(
        slug="v",
        version=1,
        name="V",
        selection_mode="query",
        query=ExecutableViewpointQuery(
            entity_criteria=EntityCriteriaGroup(
                children=(AttributeCondition(attribute="type", comparator="eq", value=ValueRef(literal="widget")),)
            )
        ),
    )


def _registries(*, widget_known: bool) -> RegistrySnapshot:
    return RegistrySnapshot(
        known_entity_types=frozenset({"widget"} if widget_known else set()),
        known_connection_types=frozenset(),
        known_specialization_slugs=frozenset(),
        entity_attribute_types={},
        connection_attribute_types={},
    )


def test_same_generation_and_digest_returns_the_cached_object() -> None:
    clear_reference_report_cache()
    definition, store = _definition(), Store()
    first = cached_reference_report(
        definition, registries=_registries(widget_known=False), read_access=store, index_generation=1
    )
    second = cached_reference_report(
        definition, registries=_registries(widget_known=False), read_access=store, index_generation=1
    )
    assert first is second
    assert [b.reference for b in first] == ["widget"]


def test_new_generation_is_a_cache_miss() -> None:
    clear_reference_report_cache()
    definition, store = _definition(), Store()
    broken = cached_reference_report(
        definition, registries=_registries(widget_known=False), read_access=store, index_generation=1
    )
    healed = cached_reference_report(
        definition, registries=_registries(widget_known=True), read_access=store, index_generation=2
    )
    assert [b.reference for b in broken] == ["widget"]
    assert healed == ()  # the model changed back — recomputed, self-healed


def test_unknown_generation_bypasses_the_cache() -> None:
    clear_reference_report_cache()
    definition, store = _definition(), Store()
    first = cached_reference_report(
        definition, registries=_registries(widget_known=False), read_access=store, index_generation=None
    )
    # A different registry at the same (None) generation must NOT be served a stale hit.
    second = cached_reference_report(
        definition, registries=_registries(widget_known=True), read_access=store, index_generation=None
    )
    assert [b.reference for b in first] == ["widget"]
    assert second == ()
