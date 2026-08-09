"""Startup validation: registry internal consistency, repo/registry compatibility, and schema policy.

Three independent checks, and this module is the one door to all three:

- ``validate_registry_consistency`` — pure in-memory check that every type referenced
  in permitted_relationships is actually declared in the same module.  Fast, no I/O,
  runs inside ``build_module_registry`` so broken YAML is caught at startup.
  Implemented in ``_startup_registry_consistency``.

- ``validate_repo_compatibility`` — scans indexed repo content and compares types found
  against the module registry.  Any type present in the repo but absent from the registry
  is reported as an error.  Implemented below: it is the only half that needs a repository.

- ``validate_schema_policy`` — implemented in ``_startup_schema_policy``.

The two halves that live elsewhere are re-exported at the foot of this module, so every caller
keeps importing one name from one place regardless of where the implementation sits.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from src.application.artifacts.schema import list_schema_files

if TYPE_CHECKING:
    from src.application.artifacts.repository import ArtifactRepository
    from src.domain.modules.module_registry import ModuleRegistry


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


# ── Re-exported halves (implementations in the two sibling modules) ───────────
from src.application._startup_registry_consistency import (  # noqa: E402,F401
    RegistryConsistencyError as RegistryConsistencyError,
)
from src.application._startup_registry_consistency import (  # noqa: E402,F401
    validate_registry_consistency as validate_registry_consistency,
)
from src.application._startup_schema_policy import SchemaPolicyError as SchemaPolicyError  # noqa: E402,F401
from src.application._startup_schema_policy import validate_schema_policy as validate_schema_policy  # noqa: E402,F401
