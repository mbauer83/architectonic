"""Registry internal consistency: the checks that need no repository at all.

Split out of `startup_validation` for the reason the schema-policy half already was — the module
held two validations that share nothing but the moment they run. This one is pure and in-memory:
every type a module references it must also declare, its classification levels must be able to mean
what they say, and every bridge must name things that exist. It runs inside `build_module_registry`,
so a broken module fails at startup rather than inside whichever consumer walked it first.

The repository half — which compares indexed content against the registry — stays in
`startup_validation`, which re-exports both so callers see one door.
"""

from __future__ import annotations

import re as _re
from collections.abc import Iterable, Iterator
from itertools import chain
from typing import TYPE_CHECKING

from src.domain.diagrams.bindings import CORE_CORRESPONDENCE_KINDS
from src.domain.relationships.permitted_mappings import concept_scope_from_mapping_spec

if TYPE_CHECKING:
    from src.domain.modules.bridges import BridgeDeclaration
    from src.domain.modules.module_registry import ModuleRegistry


class RegistryConsistencyError(Exception):
    """Raised when a module's permitted_relationships reference undeclared types."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__("\n".join(errors))


def validate_registry_consistency(registry: "ModuleRegistry") -> None:
    """Raise RegistryConsistencyError if any module has internal type drift.

    Checks for each registered ontology and diagram type that every entity type
    and connection type referenced in permitted_relationships is actually declared
    in that module's own types (or, for diagram types, in effective_entity/connection_types).
    """
    errors = _collect_consistency_errors(registry)
    if errors:
        raise RegistryConsistencyError(errors)


def _ontology_consistency_msgs(registry: "ModuleRegistry") -> Iterator[str]:
    """Every type referenced in an ontology's permitted_relationships must be declared in it."""
    for om_name, om in registry.all_ontologies().items():
        known_entity = set(om.entity_types.keys())
        known_conn = set(om.connection_types.keys())
        for src, targets in om.permitted_relationships.by_source().items():
            if src not in known_entity:
                yield f"Ontology {om_name!r}: permitted_relationships source {str(src)!r} is not a declared entity type"
            for tgt, conn in targets:
                if tgt not in known_entity:
                    yield (f"Ontology {om_name!r}: permitted_relationships target {str(tgt)!r}"
                           " is not a declared entity type")
                if conn not in known_conn:
                    yield (f"Ontology {om_name!r}: permitted_relationships connection {str(conn)!r}"
                           " is not a declared connection type")


def _classification_level_msgs(registry: "ModuleRegistry") -> Iterator[str]:
    """Every ontology's classification levels must be able to mean what they say.

    At startup rather than at first use: a module whose keying level is ambiguous decides nothing
    about whether a pair is permitted, and the consumer that discovers it would be whichever one
    happened to walk the levels first — a refusal reported far from the declaration that caused it.
    """
    from src.domain.ontology_representation.classification_levels import (  # noqa: PLC0415
        ClassificationLevelsError,
        classification_levels_for,
        validate_classification_levels,
    )

    for om_name, om in registry.all_ontologies().items():
        try:
            validate_classification_levels(classification_levels_for(om), module=om_name)
        except ClassificationLevelsError as exc:
            yield f"Ontology {om_name!r}: {exc}"


def _diagram_type_consistency_msgs(registry: "ModuleRegistry") -> Iterator[str]:
    """Diagram permitted_relationships entity types must be diagram-owned or declared in an ontology.

    effective_entity_types() is intentionally avoided; for model-backed diagram types (e.g. C4) it
    calls get_module_registry(), which would recurse during build. Diagram types backed entirely by
    an external ontology (no diagram_only_types) are skipped; connection vocabulary is not re-checked.
    """
    all_ontology_entity_names = frozenset(str(k) for k in registry.all_entity_types().keys())
    for dt_name, dt in registry.all_diagram_types().items():
        diagram_entity_names = frozenset(oe.entity_type for oe in dt.ui_config.diagram_only_types)
        if not diagram_entity_names:
            continue
        all_valid = diagram_entity_names | all_ontology_entity_names
        for src, targets in dt.own_permitted_relationships.by_source().items():
            if str(src) not in all_valid:
                yield (f"Diagram type {dt_name!r}: permitted_relationships source {str(src)!r}"
                       " is not a known entity type")
            for tgt, _conn in targets:
                if str(tgt) not in all_valid:
                    yield (f"Diagram type {dt_name!r}: permitted_relationships target {str(tgt)!r}"
                           " is not a known entity type")


def _permitted_mapping_source_msgs(registry: "ModuleRegistry") -> Iterator[str]:
    """Every permitted_mappings source ontology token must resolve via registry.find_ontology.

    Diagram-owned entity types declare cross-ontology mapping sources by module name
    (e.g. ``ontology: archimate-4-0``); a stale or mistyped token (such as a package name)
    would otherwise fail silently at first use instead of at startup.
    """
    for dt_name, dt in registry.all_diagram_types().items():
        for oe in dt.ui_config.diagram_only_types:
            for source in oe.permitted_mappings.sources:
                if registry.find_ontology(source.ontology) is None:
                    yield (
                        f"Diagram type {dt_name!r}: permitted_mappings source ontology "
                        f"{source.ontology!r} (entity type {oe.entity_type!r}) is not a registered ontology"
                    )


def _dedupe(messages: Iterable[str]) -> list[str]:
    """Preserve first-occurrence order while dropping duplicate messages."""
    seen: set[str] = set()
    ordered: list[str] = []
    for msg in messages:
        if msg not in seen:
            seen.add(msg)
            ordered.append(msg)
    return ordered


_ID_PREFIX_GRAMMAR = _re.compile(r"^[A-Z]+$")


def _id_prefix_consistency_msgs(registry: "ModuleRegistry") -> Iterator[str]:
    """Every workspace-scoped diagram entity type must declare a unique, grammar-valid id_prefix."""
    seen_prefixes: dict[str, str] = {}  # prefix → first declaring type
    for dk in registry.all_diagram_types().values():
        for oe in dk.ui_config.diagram_only_types:
            if oe.identity_scope != "workspace":
                continue
            if not oe.id_prefix:
                yield (
                    f"Diagram type {str(dk.name)!r}: entity type {oe.entity_type!r} has "
                    f"identity_scope 'workspace' but declares no id_prefix"
                )
                continue
            if not _ID_PREFIX_GRAMMAR.match(oe.id_prefix):
                yield (
                    f"Diagram type {str(dk.name)!r}: entity type {oe.entity_type!r} "
                    f"id_prefix {oe.id_prefix!r} does not match grammar [A-Z]+"
                )
                continue
            if oe.id_prefix in seen_prefixes:
                yield (
                    f"Diagram type {str(dk.name)!r}: entity type {oe.entity_type!r} "
                    f"id_prefix {oe.id_prefix!r} already declared by {seen_prefixes[oe.id_prefix]!r}"
                )
            else:
                seen_prefixes[oe.id_prefix] = oe.entity_type


def _collect_consistency_errors(registry: "ModuleRegistry") -> list[str]:
    errors = _dedupe(chain(
        _ontology_consistency_msgs(registry),
        _classification_level_msgs(registry),
        _diagram_type_consistency_msgs(registry),
        _id_prefix_consistency_msgs(registry),
        _permitted_mapping_source_msgs(registry),
    ))
    errors.extend(_collect_bridge_errors(registry))
    return errors


def _collect_bridge_errors(registry: "ModuleRegistry") -> list[str]:
    """Validate bridge declarations from all registered diagram type modules.

    Five checks per bridge (see SPEC-phase-4 §3.2):
    1. from.type is a declared diagram-owned entity type in from.module.
    2. to.module is a registered ontology.
    3. every to.type exists in to.module.
    4. correspondence_kind is a core or module-declared kind.
    5. bridge to.types agree with the diagram type's permitted_mappings for from.type.
    """
    errors: list[str] = []
    all_ontologies = dict(registry.all_ontologies())

    for dt_name, dt in registry.all_diagram_types().items():
        bridges = getattr(dt, "bridges", ())
        if not bridges:
            continue
        diagram_entity_names = frozenset(oe.entity_type for oe in dt.ui_config.diagram_only_types)
        permitted_mappings: dict[str, frozenset[str]] = {
            oe.entity_type: frozenset(
                str(entity_type)
                for entity_type in (concept_scope_from_mapping_spec(oe.permitted_mappings, registry).entity_types or ())
            )
            for oe in dt.ui_config.diagram_only_types
        }
        for bridge in bridges:
            _check_bridge(bridge, dt_name, diagram_entity_names, permitted_mappings, all_ontologies, errors)

    return errors


def _check_bridge(
    bridge: "BridgeDeclaration",
    dt_name: str,
    diagram_entity_names: frozenset[str],
    permitted_mappings: dict[str, frozenset[str]],
    all_ontologies: dict,
    errors: list[str],
) -> None:
    prefix = f"Bridge {bridge.name!r} in diagram type {dt_name!r}"

    # 1. from.type must be a declared diagram-owned entity type
    if bridge.from_type not in diagram_entity_names:
        errors.append(f"{prefix}: from.type {bridge.from_type!r} is not a diagram-owned entity type")
        return

    # 2. to.module must be a registered ontology
    ontology = all_ontologies.get(bridge.to_module)
    if ontology is None:
        errors.append(f"{prefix}: to.module {bridge.to_module!r} is not a registered ontology")
        return

    # 3. every to.type must exist in to.module
    known_to_types = set(ontology.entity_types.keys())
    missing_types = [t for t in bridge.to_types if t not in known_to_types]
    if missing_types:
        errors.append(
            f"{prefix}: to.types {missing_types} not found in ontology {bridge.to_module!r}"
        )

    # 4. correspondence_kind must be a core kind
    if bridge.correspondence_kind not in CORE_CORRESPONDENCE_KINDS:
        errors.append(
            f"{prefix}: correspondence_kind {bridge.correspondence_kind!r} is not a core kind; "
            f"module-declared kinds are not yet supported"
        )

    # 5. class preservation: each preserves_class must be present on every to.type
    for cls in bridge.preserves_classes:
        lacking = [
            t for t in bridge.to_types
            if t in known_to_types and cls not in ontology.entity_types[t].classes
        ]
        if lacking:
            errors.append(
                f"{prefix}: preserves_classes claims {cls!r} but "
                f"to.types {lacking} in {bridge.to_module!r} lack that class"
            )

    # 5b. descent-style overlap: bridge to.types must be a subset of permitted_mappings
    allowed_targets = permitted_mappings.get(bridge.from_type, frozenset())
    if allowed_targets:
        extra = [t for t in bridge.to_types if t not in allowed_targets]
        if extra:
            errors.append(
                f"{prefix}: to.types {extra} not in permitted_mappings for "
                f"{bridge.from_type!r} — bridge contradicts allowed_bindings"
            )
