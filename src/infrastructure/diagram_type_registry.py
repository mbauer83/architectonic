"""Infrastructure adapter: registry-backed diagram-type lookups."""

from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache

from src.domain.ontology_representation.ontology_protocol import DiagramRenderer, DiagramTypeModule


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


@lru_cache(maxsize=1)
def suppressed_stereotype_tokens() -> frozenset[str]:
    """The relation stereotypes an arrow style already conveys, so a label for them is noise.

    Here rather than in the write path, for the reason `find_renderer` gives: it is a question about
    what the *registry* says, and it was answered in `diagram_references` behind a second `_registry()`
    memo of its own — a module whose subject is inferring which artifacts a body names. Its one caller
    is the body preparation, which already asks this adapter for the renderer.
    """
    from src.infrastructure.app_bootstrap import build_runtime_catalogs  # noqa: PLC0415

    return build_runtime_catalogs(_registry()).diagram_types.suppressed_stereotype_tokens()


def find_renderer(name: str) -> DiagramRenderer | None:
    """The renderer for *name*, or ``None`` when no registered module provides that type.

    A repository outlives any one deployment's module set: a stored diagram names its type in its
    own frontmatter, and a host without the confidential store registers no assurance module, so
    `bowtie` is a type the catalog holds and the registry does not. Readers that resolve a *stored*
    type therefore ask this rather than `get_diagram_type`, whose `KeyError` is right only where
    the caller chose the type from the registry in the first place.

    Here rather than at the call site, for the reason `all_diagram_types` records: a caller that
    cannot get an answer from this adapter reaches past it, and the next one writes the same
    None-check again somewhere else.
    """
    module = find_diagram_type(name)
    return None if module is None else module.renderer


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
