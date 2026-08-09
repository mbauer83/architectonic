"""The ontology, handed to the pure link verifier.

`domain.scratchpad.link_verdict` decides *what a verdict is* and loads nothing to do it. This is
the other half: it reaches into the module registry once and hands over three plain callables. The
seam exists so the many verdict cases stay testable without a registry, and so the scratchpad never
grows its own opinion about what the ontology permits — it asks.

The two tiers come from the ontology's own `classification_levels` (B3): the level with
`keys_relationships` is what `permits` consults, and a level with `narrows_relationships` is what
`narrows` does. A meta-ontology declaring no narrowing tier simply gets no `narrows`, and the
verdicts collapse to one tier without a special case anywhere.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from src.domain.modules.module_registry import ModuleRegistry
from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.domain.ontology_representation.classification_levels import (
    ClassificationLevel,
    classification_levels_for,
)
from src.domain.ontology_representation.ontology_protocol import OntologyModule
from src.domain.ontology_representation.specializations import specialization_narrows
from src.domain.scratchpad import Endpoint, LinkVerdict, TypingOptions, verify_link


@dataclass(frozen=True, slots=True)
class OntologyView:
    """Everything the scratchpad asks of a meta-ontology, and nothing more."""

    name: str
    levels: tuple[ClassificationLevel, ...]
    entity_types: tuple[str, ...]
    connection_types: tuple[str, ...]


def ontology_view(registry: ModuleRegistry, meta_ontology: str) -> OntologyView:
    """The slice of one registered ontology the scratchpad needs.

    `meta_ontology` is the scratchpad's own declaration; an unknown one is an empty view rather
    than an exception, because a scratchpad naming a vocabulary this workspace does not have is
    still readable — it simply cannot verify anything, which is what `unverified` already means.
    """
    module = _module_for(registry, meta_ontology)
    if module is None:
        return OntologyView(name=meta_ontology, levels=(), entity_types=(), connection_types=())
    return OntologyView(
        name=meta_ontology,
        levels=classification_levels_for(module),
        entity_types=tuple(sorted(str(name) for name in module.entity_types)),
        connection_types=tuple(sorted(str(name) for name in module.connection_types)),
    )


def _module_for(registry: ModuleRegistry, meta_ontology: str) -> OntologyModule | None:
    modules = registry.all_ontologies()
    return modules.get(meta_ontology) or _by_alias(modules, meta_ontology)


def _by_alias(modules: Mapping[str, OntologyModule], meta_ontology: str) -> OntologyModule | None:
    """`archimate-4` in a scratchpad, `archimate-4-0` in the registry.

    A scratchpad names its meta-ontology in the form a person would write, and the registry keys on
    the module's own name. Matching on the shared prefix keeps one spelling from being a silent
    "this ontology does not exist".
    """
    normalized = meta_ontology.replace("_", "-").rstrip("-")
    for name, module in modules.items():
        candidate = str(name).replace("_", "-")
        if candidate == normalized or candidate.startswith(f"{normalized}-"):
            return module
    return None


def typing_options(registry: ModuleRegistry, meta_ontology: str) -> tuple[TypingOptions, ...]:
    """What a note may be narrowed to, level by level, in the order the ontology declares.

    Only the type level is populated today: a specialization's options depend on the type chosen,
    so the canvas asks again once it has one.
    """
    view = ontology_view(registry, meta_ontology)
    return tuple(
        TypingOptions(
            level_id=level.id,
            label=level.label,
            values=view.entity_types if level.source == "type" else (),
            required=level.required,
        )
        for level in view.levels
    )


def verdict_for(
    registry: ModuleRegistry,
    *,
    meta_ontology: str,
    source: Endpoint,
    target: Endpoint,
    connection_type: str | None,
) -> LinkVerdict:
    """Verify one drawn link against the scratchpad's meta-ontology."""
    module = _module_for(registry, meta_ontology)
    if module is None:
        return verify_link(
            source, target, connection_type=connection_type,
            permits=lambda *_: False, permitted_types=lambda *_: (),
        )

    permitted = module.permitted_relationships

    # `permits` takes (source, target, connection) — the ontology's own argument order, not the
    # reading order of a triple. Passing them the way the sentence reads is silently always False.
    def permits(source_type: str, conn: str, target_type: str) -> bool:
        return permitted.permits(
            EntityTypeName(source_type), EntityTypeName(target_type), ConnectionTypeName(conn)
        )

    def permitted_types(source_type: str, target_type: str) -> Sequence[str]:
        return tuple(sorted(str(conn) for conn in permitted.permitted_connection_types(
            EntityTypeName(source_type), EntityTypeName(target_type)
        )))

    return verify_link(
        source, target, connection_type=connection_type,
        permits=permits, permitted_types=permitted_types,
        narrows=_narrowing_probe(module),
    )


def _narrowing_probe(
    module: OntologyModule,
) -> Callable[[str, str, str, str], str | None] | None:
    """Ask a specialization whether it restricts this triple, returning the slug that did.

    Returns `None` when the ontology declares no narrowing level: the tier is optional, and a
    meta-ontology without one should produce one-tier verdicts rather than a stubbed second tier.
    """
    levels = classification_levels_for(module)
    if not any(level.narrows_relationships for level in levels):
        return None
    catalog = module.specialization_catalog

    def narrows(slug: str, conn: str, source_type: str, target_type: str) -> str | None:
        # A slug may specialize either end's entity type or the connection type; whichever declares
        # it is the one whose restrictions apply.
        probes: tuple[tuple[Literal["entity", "connection"], str], ...] = (
            ("entity", source_type), ("entity", target_type), ("connection", conn),
        )
        for concept, parent in probes:
            info = catalog.get(concept, parent, slug)
            if info is not None and specialization_narrows(
                info, conn_type=conn, source_type=source_type, target_type=target_type
            ):
                return slug
        return None

    return narrows
