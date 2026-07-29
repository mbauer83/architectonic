"""Diagram/matrix viewpoint-application verifier rule: unknown slug (E180, always an
error), stale pinned version (W180), out-of-scope placed entity/connection (W181), and
criteria-mismatch placed entity/connection (W182) — distinct from metamodel-violation codes
elsewhere in this package. W180/W181/W182 are suppressed entirely when the effective
enforcement setting is ``off``; both ``warn`` and ``ghost`` still emit them, since ghosting is
a GUI rendering behavior applied independently of this check — a CI/`arch-repo verify` run
should still see the same signal the GUI ghosts.

Obtains its artifact-local projection from ``project_artifact_local`` (companion plan §6.2/
§6.3) — the same application service the GUI's ghost/hide overlay consumes — rather than
re-implementing scope/criteria evaluation here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.application.viewpoints.artifact_projection import project_artifact_local
from src.application.viewpoints.placed_occurrences import resolve_placed_connections, resolve_placed_entities
from src.domain.concept_scope import ConceptScope
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.ontology_representation.ontology_protocol import DiagramTypeModule
from src.domain.ontology_representation.ontology_types import EntityTypeInfo
from src.domain.viewpoints.viewpoint_application_parsing import parse_viewpoint_application
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_projection import ProjectedOccurrence
from src.domain.viewpoints.viewpoints import EnforcementSetting, TargetKind, ViewpointCatalog

if TYPE_CHECKING:
    from src.application.runtime_catalogs import RuntimeCatalogs


def check_viewpoint_for_diagram_type(
    fm: dict,
    *,
    target_kind: TargetKind,
    runtime_catalogs: "RuntimeCatalogs",
    registry: ArtifactRegistry | None,
    registry_snapshot: RegistrySnapshot,
    result: VerificationResult,
    loc: str,
) -> DiagramTypeModule | None:
    """Resolve this file's diagram-type module (matrix files are always type "matrix") and,
    if resolved, run the viewpoint-application check against it. Returns the resolved
    module (or ``None``) so callers needing it for other checks don't re-resolve it."""
    diag_type = "matrix" if target_kind == "matrix" else str(fm.get("diagram-type", ""))
    module = runtime_catalogs.diagram_types.find_diagram_type(diag_type)
    if module is not None and registry is not None:
        check_viewpoint_application(
            fm,
            target_kind=target_kind,
            target_id=str(fm.get("artifact-id", "")),
            catalog=runtime_catalogs.viewpoints,
            diagram_scope=module.concept_scope(),
            entity_type_infos=runtime_catalogs.ontology.all_entity_types(),
            placed_entities=resolve_placed_entities(fm, registry),
            placed_connections=resolve_placed_connections(fm, registry),
            default_enforcement=runtime_catalogs.viewpoint_enforcement,
            read_access=registry,
            registries=registry_snapshot,
            result=result,
            loc=loc,
        )
    return module


def check_viewpoint_application(
    fm: dict,
    *,
    target_kind: TargetKind,
    target_id: str,
    catalog: ViewpointCatalog,
    diagram_scope: ConceptScope,
    entity_type_infos: Mapping[str, EntityTypeInfo],
    placed_entities: Sequence[EntityRecord],
    placed_connections: Sequence[ConnectionRecord],
    default_enforcement: EnforcementSetting,
    read_access: ArtifactRegistry,
    registries: RegistrySnapshot,
    result: VerificationResult,
    loc: str,
) -> None:
    raw = fm.get("viewpoint")
    if raw is None:
        return
    application = parse_viewpoint_application(raw, target_kind=target_kind, target_id=target_id)
    if application is None:
        return

    definition = catalog.get(application.viewpoint_slug)
    if definition is None:
        result.issues.append(
            Issue(Severity.ERROR, "E180", f"Unknown viewpoint slug '{application.viewpoint_slug}'", loc)
        )
        return

    enforcement = application.enforcement_override or default_enforcement
    if enforcement == "off":
        return

    projection = project_artifact_local(
        definition,
        application,
        diagram_scope=diagram_scope,
        entity_type_infos=entity_type_infos,
        placed_entities=placed_entities,
        placed_connections=placed_connections,
        enforcement=enforcement,
        read_access=read_access,
        registries=registries,
    )

    if projection.stale_pin:
        result.issues.append(
            Issue(
                Severity.WARNING,
                "W180",
                f"Viewpoint '{application.viewpoint_slug}' application pinned to version "
                f"{application.pinned_version}, but the current definition is version "
                f"{definition.version} — re-pin after review.",
                loc,
            )
        )

    entities_by_id = {entity.artifact_id: entity for entity in placed_entities}
    connections_by_id = {connection.artifact_id: connection for connection in placed_connections}
    for occurrence in projection.items:
        description = _describe_item(occurrence, entities_by_id, connections_by_id)
        if "out_of_scope" in occurrence.reasons:
            result.issues.append(
                Issue(
                    Severity.WARNING,
                    "W181",
                    f"{description} is out of scope for viewpoint '{application.viewpoint_slug}'.",
                    loc,
                )
            )
        if "criteria_mismatch" in occurrence.reasons:
            result.issues.append(
                Issue(
                    Severity.WARNING,
                    "W182",
                    f"{description} does not satisfy the query criteria of viewpoint "
                    f"'{application.viewpoint_slug}'.",
                    loc,
                )
            )


def _describe_item(
    occurrence: ProjectedOccurrence,
    entities_by_id: Mapping[str, EntityRecord],
    connections_by_id: Mapping[str, ConnectionRecord],
) -> str:
    if occurrence.item_kind == "entity":
        entity = entities_by_id[occurrence.item_id]
        return f"Entity '{entity.artifact_id}' (type '{entity.artifact_type}')"
    connection = connections_by_id[occurrence.item_id]
    return f"Connection '{connection.artifact_id}' (type '{connection.conn_type}')"
