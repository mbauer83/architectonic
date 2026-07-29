"""Regression: full-vocabulary diagram types resolve effective types from the
injected registry, never a process-global one.

Previously ``matrix``/``c4`` read ``get_module_registry()`` (a service locator), so
their effective types reflected whatever global vocabulary happened to be cached.
When that global included the optional assurance vocabulary but a freshly-built
registry did not (or vice versa), ``effective_entity_types()`` leaked types absent
from the registry under test — an order-dependent protocol-compliance failure.
"""

from __future__ import annotations

from src.diagram_types.c4.system_context import module as c4_module
from src.diagram_types.matrix import module as matrix_module
from src.domain.modules.module_registry import ModuleRegistry
from src.infrastructure.app_bootstrap import (
    _ALL_ONTOLOGY_MODULES,
    build_module_registry,
    register_default_diagram_types,
)


def _registry_without_assurance() -> ModuleRegistry:
    registry = ModuleRegistry()
    for ontology in _ALL_ONTOLOGY_MODULES:
        if ontology.name != "assurance":
            registry.register_ontology(ontology)
    register_default_diagram_types(registry)
    return registry


def test_matrix_effective_types_bounded_by_injected_registry() -> None:
    lean = _registry_without_assurance()
    full = build_module_registry(complete_vocabulary=True)
    # The two registries genuinely differ — otherwise the test proves nothing.
    assert set(lean.all_entity_types()) < set(full.all_entity_types())

    assert set(matrix_module.effective_entity_types(lean)) == set(lean.all_entity_types())
    assert set(matrix_module.effective_connection_types(lean)) == set(lean.all_connection_types())


def test_c4_effective_types_subset_of_injected_registry() -> None:
    lean = _registry_without_assurance()
    assert set(c4_module.effective_entity_types(lean)) <= set(lean.all_entity_types())
    assert set(c4_module.effective_connection_types(lean)) <= set(lean.all_connection_types())
