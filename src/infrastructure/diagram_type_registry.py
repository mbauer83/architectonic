"""Infrastructure adapter: registry-backed diagram-type lookups."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache

from src.domain.ontology_representation.ontology_protocol import DiagramTypeModule


@lru_cache(maxsize=1)
def _registry():
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    return get_module_registry()


def get_diagram_type(name: str) -> DiagramTypeModule:
    """Return the registered diagram type named *name*."""
    return _registry().get_diagram_type(name)


def find_diagram_type(name: str) -> DiagramTypeModule | None:
    """Return the registered diagram type named *name*, if any."""
    return _registry().find_diagram_type(name)


def all_diagram_types() -> Mapping[str, DiagramTypeModule]:
    """Every registered diagram type, by name.

    The adapter offered lookup-by-name but no enumeration, so each caller that needed the whole
    set reached past it to `get_module_registry()` — which is the module-registry singleton this
    adapter exists to keep out of its callers.
    """
    return _registry().all_diagram_types()


def diagram_type_domain(name: str) -> str | None:
    """Infer the primary non-common domain exposed by a diagram type."""
    diagram_type_mod = find_diagram_type(name)
    if diagram_type_mod is None:
        return None
    domains = {
        info.hierarchy[0]
        for info in diagram_type_mod.effective_entity_types().values()
        if not info.internal and info.hierarchy
    }
    non_common = {domain for domain in domains if domain != "common"}
    if len(non_common) == 1:
        return next(iter(non_common))
    if len(non_common) == 0 and len(domains) == 1:
        return next(iter(domains))
    return None


def domain_order() -> list[str]:
    """Return ontology-driven domain ordering."""
    return _registry().domain_order()
