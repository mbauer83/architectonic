"""Semantic triple validation for ArchiMate 4.0 connections.

Checks that each (source_type, connection_type, target_type) triple in an
outgoing file is permitted by the active ontology.  Emits E126 for illegal
triples, W126 as realization-quality guidance, W127 when a multiplicity is
set on a junction-attached connection end (junctions do not support
multiplicities — this is a read-time complement to the write-time hard block
in `artifact_write/connection.py::add_connection`, catching persisted data
that predates that guard or entered through the edit path, which does not
enforce it), W128 when a connection specialization's `restrict_endpoints`
allow-list doesn't cover the actual (source_type, target_type) pair, and W129
when a source/target entity's own specialization's `restrict_relationships`
allow-list doesn't cover the actual (conn_type, source_type, target_type)
triple for the role that entity plays.
"""

from __future__ import annotations

from src.application.global_reference_endpoints import (
    GLOBAL_ARTIFACT_REFERENCE_TYPE,
    GLOBAL_REFERENCE_SOURCE_ERROR,
    EffectiveEndpoint,
    effective_endpoint,
)
from src.application.verification.artifact_verifier_parsing import parse_frontmatter_from_path
from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.domain.modules.catalogs import ConnectionSemantics, OntologyCatalog
from src.domain.ontology_representation.specialization_values import (
    applied_specialization_slugs,
)
from src.domain.ontology_representation.specializations import (
    EndpointRestriction,
    RelationshipRestriction,
    SpecializationCatalog,
)
from src.domain.repository.connection_declaration import ConnectionDeclaration


def _entity_type(registry: ArtifactRegistry, entity_id: str) -> str | None:
    path = registry.find_file_by_id(entity_id)
    if path is None:
        return None
    fm = parse_frontmatter_from_path(path)
    if not isinstance(fm, dict):
        return None
    return str(fm.get("artifact-type", "")) or None


def _endpoint(registry: ArtifactRegistry, entity_id: str, *, read_specialization: bool) -> EffectiveEndpoint:
    """Endpoint identity with GAR proxies resolved. Non-GAR entities resolve through the
    module-level readers (kept as the fast path — and the seam tests patch), and the
    specialization read stays conditional so the no-catalog contract ("zero
    entity-resolution I/O") holds; only an actual global-artifact-reference pays for
    full reference resolution."""
    own_type = _entity_type(registry, entity_id)
    if own_type != GLOBAL_ARTIFACT_REFERENCE_TYPE:
        return EffectiveEndpoint(
            entity_type=own_type,
            specializations=(
                _entity_specializations(registry, entity_id) if read_specialization else ()
            ),
            is_global_reference=False,
        )
    return effective_endpoint(registry, entity_id)


def _entity_specializations(registry: ArtifactRegistry, entity_id: str) -> tuple[str, ...]:
    """Every specialization the entity's frontmatter applies, whichever shape the value used."""
    path = registry.find_file_by_id(entity_id)
    if path is None:
        return ()
    fm = parse_frontmatter_from_path(path)
    if not isinstance(fm, dict):
        return ()
    return applied_specialization_slugs(fm.get('specialization'))


def _permitted(
    connections_catalog: ConnectionSemantics,
    source_type: str,
    conn_type: str,
    target_type: str,
) -> tuple[bool, list[str]]:
    """Return (allowed, alternatives)."""
    allowed_set = set(connections_catalog.permissible_connection_types(source_type, target_type))
    if conn_type in allowed_set:
        return True, []
    return False, sorted(allowed_set)


_REALIZATION = "archimate-realization"
_STRUCTURE_CLASSES = frozenset(
    ["active-structure-element", "internal-active-structure-element", "external-active-structure-element",
     "technology-internal-active-structure-element", "passive-structure-element", "composite-element"]
)
_BEHAVIOR_TARGET = frozenset(["service"])


def _is_structure(ontology_catalog: OntologyCatalog, source_type: str) -> bool:
    return any(source_type in ontology_catalog.entity_types_with_class(cls) for cls in _STRUCTURE_CLASSES)


def _check_junction_multiplicity(
    ontology_catalog: OntologyCatalog,
    *,
    entity_id: str,
    entity_type: str,
    multiplicity: str,
    label: str,
    result: VerificationResult,
    loc: str,
) -> None:
    if not multiplicity or entity_type not in ontology_catalog.entity_types_with_class("junction"):
        return
    result.issues.append(
        Issue(
            Severity.WARNING,
            "W127",
            f"{label.capitalize()} multiplicity '{multiplicity}' is set on a junction connection-end "
            f"('{entity_id}' is a junction); junctions do not support multiplicities.",
            loc,
        )
    )


def _endpoint_pair_allowed(restriction: EndpointRestriction, source_type: str, target_type: str) -> bool:
    src_ok = not restriction.source_types or source_type in restriction.source_types
    tgt_ok = not restriction.target_types or target_type in restriction.target_types
    return src_ok and tgt_ok


def _check_connection_endpoint_restriction(
    catalog: SpecializationCatalog,
    *,
    slug: str,
    conn_type: str,
    source_type: str,
    target_type: str,
    result: VerificationResult,
    loc: str,
) -> None:
    info = catalog.get("connection", conn_type, slug)
    if info is None or not info.restrict_endpoints:
        return
    if not any(_endpoint_pair_allowed(r, source_type, target_type) for r in info.restrict_endpoints):
        result.issues.append(
            Issue(
                Severity.WARNING,
                "W128",
                f"Specialization '{slug}' on '{conn_type}' restricts endpoints; "
                f"({source_type} -> {target_type}) does not match any allowed pair.",
                loc,
            )
        )


def _relationship_triple_allowed(
    restriction: RelationshipRestriction, conn_type: str, source_type: str, target_type: str
) -> bool:
    if restriction.connection_type != conn_type:
        return False
    src_ok = restriction.source_type is None or restriction.source_type == source_type
    tgt_ok = restriction.target_type is None or restriction.target_type == target_type
    return src_ok and tgt_ok


def _check_entity_relationship_restriction(
    catalog: SpecializationCatalog,
    *,
    entity_id: str,
    entity_type: str,
    slug: str,
    conn_type: str,
    source_type: str,
    target_type: str,
    role: str,
    result: VerificationResult,
    loc: str,
) -> None:
    info = catalog.get("entity", entity_type, slug)
    if info is None or not info.restrict_relationships:
        return
    allowed = any(
        _relationship_triple_allowed(r, conn_type, source_type, target_type) for r in info.restrict_relationships
    )
    if not allowed:
        result.issues.append(
            Issue(
                Severity.WARNING,
                "W129",
                f"Entity '{entity_id}' specialization '{slug}' restricts relationships; "
                f"('{conn_type}': {source_type} -> {target_type}, as {role}) does not match any allowed rule.",
                loc,
            )
        )


def check_connection_semantics(
    source_id: str,
    connections: list[ConnectionDeclaration],
    registry: ArtifactRegistry,
    result: VerificationResult,
    loc: str,
    *,
    connections_catalog: ConnectionSemantics | None = None,
    ontology_catalog: OntologyCatalog | None = None,
    specialization_catalog: SpecializationCatalog | None = None,
) -> None:
    """Validate semantic triples; add E126/W126/W127/W128/W129 issues to result.

    The permitted-triple check (E126/W126) is skipped when connections_catalog is None; the
    junction-multiplicity check (W127) and the specialization endpoint/relationship checks
    (W128/W129) are independent and run whenever their respective catalog is injected,
    regardless of whether the triple itself is permitted. When *none* of the three catalogs
    is injected there is nothing this function could possibly report, so it returns
    immediately without touching the registry at all — callers (and tests) rely on this to
    mean "zero entity-resolution I/O happens" when no catalog is configured.
    """
    if connections_catalog is None and ontology_catalog is None and specialization_catalog is None:
        return

    source_endpoint = _endpoint(registry, source_id, read_specialization=specialization_catalog is not None)
    source_type = source_endpoint.entity_type
    if source_type is None:
        return
    source_specializations = source_endpoint.specializations

    for decl in connections:
        conn_type, target_id = decl.conn_type, decl.target_id
        src_mult, tgt_mult = decl.src_multiplicity, decl.tgt_multiplicity
        target_endpoint = _endpoint(registry, target_id, read_specialization=specialization_catalog is not None)
        target_type = target_endpoint.entity_type

        if (
            source_endpoint.is_global_reference
            and connections_catalog is not None
            and not connections_catalog.is_symmetric(conn_type)
        ):
            result.issues.append(Issue(Severity.ERROR, "E127", GLOBAL_REFERENCE_SOURCE_ERROR, loc))
            continue

        if ontology_catalog is not None:
            _check_junction_multiplicity(
                ontology_catalog,
                entity_id=source_id,
                entity_type=source_type,
                multiplicity=src_mult,
                label="source",
                result=result,
                loc=loc,
            )
            if target_type is not None:
                _check_junction_multiplicity(
                    ontology_catalog,
                    entity_id=target_id,
                    entity_type=target_type,
                    multiplicity=tgt_mult,
                    label="target",
                    result=result,
                    loc=loc,
                )

        if specialization_catalog is not None and target_type is not None:
            connection_specialization = str(decl.metadata.get("specialization") or "")
            if connection_specialization:
                _check_connection_endpoint_restriction(
                    specialization_catalog,
                    slug=connection_specialization,
                    conn_type=conn_type,
                    source_type=source_type,
                    target_type=target_type,
                    result=result,
                    loc=loc,
                )
            # Every applied specialization, not just the first. A concept may carry several
            # (ArchiMate §15.2) and each may declare its own relationship restrictions; checking one
            # left the rest unenforced, silently, for as long as nothing carried two.
            for source_specialization in source_specializations:
                _check_entity_relationship_restriction(
                    specialization_catalog,
                    entity_id=source_id,
                    entity_type=source_type,
                    slug=source_specialization,
                    conn_type=conn_type,
                    source_type=source_type,
                    target_type=target_type,
                    role="source",
                    result=result,
                    loc=loc,
                )
            for target_specialization in target_endpoint.specializations:
                _check_entity_relationship_restriction(
                    specialization_catalog,
                    entity_id=target_id,
                    entity_type=target_type,
                    slug=target_specialization,
                    conn_type=conn_type,
                    source_type=source_type,
                    target_type=target_type,
                    role="target",
                    result=result,
                    loc=loc,
                )

        if connections_catalog is None or target_type is None:
            continue

        ok, alternatives = _permitted(connections_catalog, source_type, conn_type, target_type)
        if ok:
            continue

        alt_str = ", ".join(alternatives) if alternatives else "none"
        result.issues.append(
            Issue(
                Severity.ERROR,
                "E126",
                f"Relationship '{conn_type}' is not permitted from "
                f"'{source_type}' to '{target_type}'. "
                f"Permitted alternatives: {alt_str}.",
                loc,
            )
        )

        if (
            ontology_catalog is not None
            and conn_type == _REALIZATION
            and target_type in _BEHAVIOR_TARGET
            and _is_structure(ontology_catalog, source_type)
        ):
            result.issues.append(
                Issue(
                    Severity.WARNING,
                    "W126",
                    f"Realization misuse: '{source_type}' (structure) cannot directly realize "
                    f"'{target_type}' (behavior). Use a function or process as realizer instead.",
                    loc,
                )
            )
