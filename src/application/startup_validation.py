"""Startup validation: registry internal consistency, repo/registry compatibility, and schema policy.

Two independent checks:

- ``validate_registry_consistency`` — pure in-memory check that every type referenced
  in permitted_relationships is actually declared in the same module.  Fast, no I/O,
  runs inside ``build_module_registry`` so broken YAML is caught at startup.

- ``validate_repo_compatibility`` — scans indexed repo content and compares types found
  against the module registry.  Any type present in the repo but absent from the registry
  is reported as an error.
"""

from __future__ import annotations

import re as _re
from collections.abc import Iterable, Iterator
from itertools import chain
from typing import TYPE_CHECKING

from src.application.artifacts.schema import list_schema_files
from src.domain.diagrams.bindings import CORE_CORRESPONDENCE_KINDS
from src.domain.relationships.permitted_mappings import concept_scope_from_mapping_spec

if TYPE_CHECKING:
    from src.application.artifacts.repository import ArtifactRepository
    from src.domain.modules.bridges import BridgeDeclaration
    from src.domain.modules.module_registry import ModuleRegistry


# ── Registry consistency ──────────────────────────────────────────────────────


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


# ── Repo compatibility ────────────────────────────────────────────────────────


class RepoCompatibilityError(Exception):
    """Raised when indexed repo content references types unknown to the registry."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = list(errors)
        super().__init__("\n".join(errors))


def validate_repo_compatibility(
    repo: "ArtifactRepository",
    registry: "ModuleRegistry",
    *,
    complete_registry: "ModuleRegistry | None" = None,
) -> list[str]:
    """Raise RepoCompatibilityError on hard incompatibilities; return tolerable warnings.

    A type absent from the active *registry* but present in *complete_registry* belongs to a
    module that is merely disabled (e.g. the assurance module when no confidential store is
    configured). Such artifacts are inert, not corrupt, so they yield a warning rather than
    aborting startup — a repository containing optional-module content stays usable without
    that module. Types unknown to every module remain hard errors. When *complete_registry*
    is omitted, every unknown type is a hard error (backward-compatible).

    Checks: entity artifact_type, connection conn_type, diagram diagram_type, attribute and
    connection-metadata schema filenames, and element-class declarations.
    """
    errors, warnings = _collect_errors(repo, registry, complete_registry)
    if errors:
        raise RepoCompatibilityError(errors)
    return warnings


def _split_unknown_types(
    typed_ids: Iterable[tuple[str, str]],
    active: set[str],
    complete: set[str],
    label: str,
) -> tuple[list[str], list[str]]:
    """Partition repo types missing from *active* into hard errors and disabled-module warnings.

    A type present in *complete* (some module declares it) but absent from *active* (that module
    is disabled) is tolerated with a warning; a type in neither is an unknown-type error.
    """
    first_example: dict[str, str] = {}
    for type_name, artifact_id in typed_ids:
        if type_name and type_name not in active and type_name not in first_example:
            first_example[type_name] = artifact_id
    errors: list[str] = []
    warnings: list[str] = []
    for t, example in sorted(first_example.items()):
        if t in complete:
            warnings.append(
                f"{label} type {t!r} belongs to a disabled module — its artifacts are inert "
                f"(example artifact: {example}); enable the module to use them"
            )
        else:
            errors.append(f"Unknown {label} type {t!r} (example artifact: {example})")
    return errors, warnings


def _schema_inventory_findings(
    repo: "ArtifactRepository", *, known_entity_types: set[str], known_connection_types: set[str]
) -> tuple[list[str], list[str]]:
    """``(errors, warnings)`` from the classified schema-file inventory
    (``artifact_schema.list_schema_files``, the one owner of the filename conventions):
    entity-attribute and entity-attachment schemas must name a known entity type,
    connection-metadata and connection-attachment schemas a known connection type
    (errors); a filename matching no
    convention is warned about — it would otherwise be silently ignored by every loader —
    but never aborts startup. An unknown specialization slug is deliberately not checked
    here: that is the verifier's orphan-attachment warning."""
    errors: list[str] = []
    warnings: list[str] = []
    for repo_root in repo.repo_roots:
        for ref in list_schema_files(repo_root):
            location = f"(file: .arch-repo/schemata/{ref.filename})"
            if ref.kind in ("entity-attributes", "specialization-attachment"):
                if ref.subject not in known_entity_types:
                    errors.append(f"Attribute schema for unknown entity type {ref.subject!r} {location}")
            elif ref.kind in ("connection-metadata", "connection-specialization-attachment"):
                if ref.subject not in known_connection_types:
                    errors.append(f"Connection metadata schema for unknown connection type {ref.subject!r} {location}")
            elif ref.kind == "unrecognized":
                warnings.append(f"Schema filename matches no known convention and is ignored {location}")
    return errors, warnings


def _element_class_errors(registry: "ModuleRegistry", known_element_classes: set[str]) -> list[str]:
    """Report entity/diagram types referencing element classes that no module declares."""
    errors: list[str] = []
    for om in registry.all_ontologies().values():
        for etype, einfo in om.entity_types.items():
            errors.extend(
                f"Entity type {etype!r} references undeclared element class {cls!r}"
                for cls in einfo.classes
                if cls not in known_element_classes
            )
    for dk in registry.all_diagram_types().values():
        for oe in dk.ui_config.diagram_only_types:
            errors.extend(
                f"Diagram type {dk.name!r} entity type {oe.entity_type!r} "
                f"references undeclared element class {cls!r}"
                for cls in oe.classes
                if cls not in known_element_classes
            )
    return errors


def _entity_connection_diagram_sets(registry: "ModuleRegistry") -> tuple[set[str], set[str], set[str]]:
    entity_types = {str(t) for t in registry.all_entity_types()} | {
        str(t) for t in registry.all_diagram_entity_types()
    }
    connection_types = {str(t) for t in registry.all_connection_types()}
    diagram_types = {str(t) for t in registry.all_diagram_types()}
    return entity_types, connection_types, diagram_types


def _collect_errors(
    repo: "ArtifactRepository",
    registry: "ModuleRegistry",
    complete_registry: "ModuleRegistry | None" = None,
) -> tuple[list[str], list[str]]:
    active_e, active_c, active_d = _entity_connection_diagram_sets(registry)
    complete_e, complete_c, complete_d = (
        _entity_connection_diagram_sets(complete_registry)
        if complete_registry is not None
        else (active_e, active_c, active_d)
    )

    errors: list[str] = []
    warnings: list[str] = []
    # Diagram-derived projections (diagram-only entities with a host diagram, and the
    # synthetic ``…#conn/…`` connections extracted from a diagram's diagram-entities) are not
    # authored model artifacts: their ``artifact_type``/``conn_type`` is the host diagram type's
    # internal group-key / edge-kind (e.g. a free-ontology GSN diagram's ``nodes`` /
    # ``supported-by``). They are governed by their registered diagram type's renderer, not the
    # model ontology vocabulary, so they are out of scope for this compatibility check. The host
    # ``diagram_type`` itself is still validated below.
    for typed_ids, active, complete, label in (
        (
            ((e.artifact_type, e.artifact_id) for e in repo.list_entities() if e.host_diagram_id is None),
            active_e, complete_e, "entity",
        ),
        (
            ((c.conn_type, c.artifact_id) for c in repo.list_connections() if "#conn/" not in c.artifact_id),
            active_c, complete_c, "connection",
        ),
        (((d.diagram_type, d.artifact_id) for d in repo.list_diagrams()), active_d, complete_d, "diagram"),
    ):
        type_errors, type_warnings = _split_unknown_types(typed_ids, active, complete, label)
        errors.extend(type_errors)
        warnings.extend(type_warnings)

    # Schema files for disabled-module types are tolerated (checked against the complete set);
    # only schemas for types no module declares are errors.
    inventory_errors, inventory_warnings = _schema_inventory_findings(
        repo, known_entity_types=complete_e, known_connection_types=complete_c
    )
    errors.extend(inventory_errors)
    warnings.extend(inventory_warnings)

    try:
        known_element_classes: set[str] = {str(c) for c in registry.all_element_classes()}
    except ValueError as exc:
        errors.append(f"Element class declaration conflict: {exc}")
        return errors, warnings

    errors.extend(_element_class_errors(registry, known_element_classes))
    return errors, warnings


# ── Schema-policy check (re-exported; implementation in _startup_schema_policy) ─
from src.application._startup_schema_policy import SchemaPolicyError as SchemaPolicyError  # noqa: E402,F401
from src.application._startup_schema_policy import validate_schema_policy as validate_schema_policy  # noqa: E402,F401
