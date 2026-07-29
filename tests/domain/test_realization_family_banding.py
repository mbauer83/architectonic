"""Band contract of the shipped realization-family viewpoints: assessed targets split
into mutually exclusive realized/unrealized bands (union = all targets), a derived-only
realization chain still counts as realized, and contextual realizers are never banded."""

from __future__ import annotations

from src.application.viewpoints.repository_projection import project_repository
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
from tests.fixtures.viewpoints.derivation_examples import ExampleGraph, catalog, connection, entity

_CATALOGS = build_runtime_catalogs(get_module_registry())


def _registries() -> RegistrySnapshot:
    relationship_catalog = catalog()
    return RegistrySnapshot(
        known_entity_types=frozenset(relationship_catalog.all_entity_types()),
        known_connection_types=frozenset(relationship_catalog.all_connection_types()),
        known_specialization_slugs=frozenset(),
        entity_attribute_types={},
        connection_attribute_types={},
        derivation_catalog=relationship_catalog,
    )


def _graph() -> ExampleGraph:
    """Three goals: directly realized, realized only via a 2-hop derived chain
    (realization ∘ realization), and unrealized — plus the realizing elements."""
    return ExampleGraph(
        entities={
            "goal-direct": entity("goal-direct", "goal"),
            "goal-derived": entity("goal-derived", "goal"),
            "goal-unrealized": entity("goal-unrealized", "goal"),
            "direct-realizer": entity("direct-realizer", "function"),
            "chain-requirement": entity("chain-requirement", "requirement"),
            "chain-function": entity("chain-function", "function"),
        },
        connections=[
            connection("r1", "direct-realizer", "goal-direct", "archimate-realization"),
            connection("r2", "chain-requirement", "goal-derived", "archimate-realization"),
            connection("r3", "chain-function", "chain-requirement", "archimate-realization"),
        ],
    )


def test_goal_realization_bands_are_exclusive_over_targets_and_never_touch_realizers() -> None:
    definition = _CATALOGS.viewpoints.get("goal-realization")
    assert definition is not None
    projection = project_repository(definition, read_access=_graph(), registries=_registries())

    styles = {
        item.item_id: item.style.get("node_color")
        for item in projection.items
        if item.item_kind == "entity"
    }
    realized = {item_id for item_id, token in styles.items() if token == "positive"}
    unrealized = {item_id for item_id, token in styles.items() if token == "critical"}

    targets = {"goal-direct", "goal-derived", "goal-unrealized"}
    assert realized | unrealized == targets  # union invariant: every assessed target is banded
    assert realized & unrealized == set()  # band exclusivity
    assert realized == {"goal-direct", "goal-derived"}  # derived-only chain still counts
    assert unrealized == {"goal-unrealized"}
    # Contextual realizers are displayed (included via the realization inclusions) but
    # NEVER banded — a realizer with no incoming realization of its own is context, not
    # an unrealized target.
    assert "direct-realizer" in styles and styles["direct-realizer"] is None
    assert styles.get("chain-requirement") is None
