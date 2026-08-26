"""Artifact-local projection: every placed occurrence of a diagram or matrix, resolved
exactly as the verifier resolves them, carrying an exclusion reason when it fails
effective scope or the definition's query criteria. The verifier and the GUI ghost/hide
overlay both consume this — one service, never re-implemented.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.application.verification.artifact_verifier_registry import ArtifactRegistry
from src.application.viewpoints.placed_occurrences import resolve_placed_connections, resolve_placed_entities
from src.domain.concept_scope import ConceptScope
from src.domain.modules.module_types import ConnectionTypeName, EntityTypeName
from src.domain.ontology_representation.artifact_types import ConnectionRecord, EntityRecord
from src.domain.ontology_representation.ontology_protocol import DiagramTypeModule
from src.domain.ontology_representation.ontology_types import EntityTypeInfo
from src.domain.viewpoints.viewpoint_application_parsing import parse_viewpoint_application
from src.domain.viewpoints.viewpoint_condition_validation import RegistrySnapshot
from src.domain.viewpoints.viewpoint_criteria_evaluation import evaluate_connection_criteria, evaluate_entity_criteria
from src.domain.viewpoints.viewpoint_evaluation_context import CriteriaReadAccess, EvaluationEnvironment
from src.domain.viewpoints.viewpoint_projection import (
    ExclusionReason,
    OcclusionState,
    ProjectedOccurrence,
    ScaleLegendData,
    ViewpointProjection,
    drift_warnings,
    rule_outcome_warnings,
)
from src.domain.viewpoints.viewpoint_scale_styling import calculate_scale_bounds
from src.domain.viewpoints.viewpoint_style_evaluation import (
    RuleItemHit,
    StyleValue,
    classify_style_rule_outcomes,
    evaluate_item_style,
)
from src.domain.viewpoints.viewpoints import (
    EnforcementSetting,
    TargetKind,
    ViewpointApplication,
    ViewpointCatalog,
    ViewpointDefinition,
)


def _entity_reasons(
    entity: EntityRecord,
    definition: ViewpointDefinition,
    effective_scope: ConceptScope,
    entity_type_infos: Mapping[str, EntityTypeInfo],
    *,
    read_access: CriteriaReadAccess,
    registries: RegistrySnapshot,
) -> tuple[tuple[ExclusionReason, ...], frozenset[str]]:
    entity_type = EntityTypeName(entity.artifact_type)
    if not effective_scope.admits_entity_type(entity_type, entity_type_infos.get(entity.artifact_type)):
        return ("out_of_scope",), frozenset()
    if definition.query is None:
        return (), frozenset()
    outcome = evaluate_entity_criteria(
        definition.query.entity_criteria, entity, read_access=read_access, registries=registries
    )
    return (() if outcome.matched else ("criteria_mismatch",)), outcome.schema_drift


def _connection_reasons(
    connection: ConnectionRecord,
    definition: ViewpointDefinition,
    effective_scope: ConceptScope,
    entity_reasons: Mapping[str, tuple[ExclusionReason, ...]],
    *,
    read_access: CriteriaReadAccess,
    registries: RegistrySnapshot,
) -> tuple[tuple[ExclusionReason, ...], frozenset[str]]:
    reasons: list[ExclusionReason] = []
    if entity_reasons.get(connection.source) or entity_reasons.get(connection.target):
        reasons.append("endpoint_excluded")
    source_entity = read_access.get_entity(connection.source)
    target_entity = read_access.get_entity(connection.target)
    if source_entity is None or target_entity is None:
        return tuple(reasons), frozenset()
    conn_type = ConnectionTypeName(connection.conn_type)
    if not effective_scope.admits_connection(
        EntityTypeName(source_entity.artifact_type), EntityTypeName(target_entity.artifact_type), conn_type
    ):
        reasons.append("out_of_scope")
        return tuple(reasons), frozenset()
    if definition.query is None:
        return tuple(reasons), frozenset()
    if not definition.query.connections.enabled:
        reasons.append("criteria_mismatch")
        return tuple(reasons), frozenset()
    outcome = evaluate_connection_criteria(
        definition.query.connections.criteria, connection, read_access=read_access, registries=registries
    )
    if not outcome.matched:
        reasons.append("criteria_mismatch")
    return tuple(reasons), outcome.schema_drift


def _identity_projection(
    application: ViewpointApplication,
    placed_entities: Sequence[EntityRecord],
    placed_connections: Sequence[ConnectionRecord],
) -> ViewpointProjection:
    items = tuple(
        ProjectedOccurrence(item_id=entity.artifact_id, item_kind="entity", state="visible")
        for entity in placed_entities
    ) + tuple(
        ProjectedOccurrence(item_id=connection.artifact_id, item_kind="connection", state="visible")
        for connection in placed_connections
    )
    warning = f"unknown viewpoint slug '{application.viewpoint_slug}'"
    return ViewpointProjection(target=application.target_kind, items=items, warnings=(warning,))


def project_artifact_local(
    definition: ViewpointDefinition | None,
    application: ViewpointApplication,
    *,
    diagram_scope: ConceptScope,
    entity_type_infos: Mapping[str, EntityTypeInfo],
    placed_entities: Sequence[EntityRecord],
    placed_connections: Sequence[ConnectionRecord],
    enforcement: EnforcementSetting,
    read_access: CriteriaReadAccess,
    registries: RegistrySnapshot,
) -> ViewpointProjection:
    """§6.2: every placed occurrence appears; ``reasons`` empty iff fully matching.
    ``enforcement`` maps reasons to state (`ghost` ghosts non-matches, `warn` keeps
    everything visible with reasons populated, `off` is an identity projection FOR
    OCCLUSION — reasons are zeroed so nothing ghosts/badges, but matching-based style is
    still computed, since enforcement governs occlusion only, never whether matches style).
    """
    if definition is None:
        return _identity_projection(application, placed_entities, placed_connections)

    effective_scope = diagram_scope & definition.scope
    drift: set[str] = set()
    entity_reasons: dict[str, tuple[ExclusionReason, ...]] = {}
    items: list[ProjectedOccurrence] = []
    rule_hits: list[RuleItemHit] = []

    # Bounds first, from the *complete* placed population, and before any item is styled. A scale is a
    # property of what the diagram draws, so every placed occurrence counts toward it — including the
    # ones that will turn out excluded. Letting an exclusion move the scale would make the same entity
    # a different colour on two diagrams for a reason the reader cannot see.
    #
    # This is the call the path was missing. Without it `scale_bounds` is empty, `_scale_value` returns
    # `None` for every rule index, and a scale rule styles nothing — even one declaring explicit
    # bounds, which is why the shipped catalogue declaring them did not save it.
    styled_items = tuple(
        [(entity, "entity") for entity in placed_entities]
        + [(connection, "connection") for connection in placed_connections]
    )
    # A neutral environment, and the reason is worth stating: bindings, parameters and derived values
    # belong to an *execution*, and this path projects a stored diagram — there is no execution to
    # take them from. So a `derived.<name>` scale attribute cannot resolve here and is reported
    # `unresolvable` rather than silently unstyled, which is the honest answer for a rule that needs a
    # query this target does not run.
    scale_bounds, scale_legends, scale_drift = calculate_scale_bounds(
        definition.presentation,
        styled_items,  # type: ignore[arg-type]
        registries=registries,
        environment=EvaluationEnvironment(),
    )
    drift |= scale_drift

    for entity in placed_entities:
        reasons, entity_drift = _entity_reasons(
            entity, definition, effective_scope, entity_type_infos, read_access=read_access, registries=registries
        )
        drift |= entity_drift
        entity_reasons[entity.artifact_id] = reasons
        effective_reasons = () if enforcement == "off" else reasons
        style: Mapping[str, StyleValue] = {}
        if not effective_reasons:
            evaluation = evaluate_item_style(
                entity,
                "entity",
                definition.presentation,
                read_access=read_access,
                registries=registries,
                scale_bounds=scale_bounds,
            )
            style = evaluation.style
            drift |= evaluation.schema_drift
            rule_hits.extend(evaluation.rule_hits)
        state: OcclusionState = "ghosted" if enforcement == "ghost" and effective_reasons else "visible"
        items.append(
            ProjectedOccurrence(
                item_id=entity.artifact_id, item_kind="entity", state=state, reasons=effective_reasons, style=style
            )
        )

    for connection in placed_connections:
        reasons, conn_drift = _connection_reasons(
            connection, definition, effective_scope, entity_reasons, read_access=read_access, registries=registries
        )
        drift |= conn_drift
        effective_reasons = () if enforcement == "off" else reasons
        style = {}
        if not effective_reasons:
            evaluation = evaluate_item_style(
                connection,
                "connection",
                definition.presentation,
                read_access=read_access,
                registries=registries,
                scale_bounds=scale_bounds,
            )
            style = evaluation.style
            drift |= evaluation.schema_drift
            rule_hits.extend(evaluation.rule_hits)
        state: OcclusionState = "ghosted" if enforcement == "ghost" and effective_reasons else "visible"
        items.append(
            ProjectedOccurrence(
                item_id=connection.artifact_id,
                item_kind="connection",
                state=state,
                reasons=effective_reasons,
                style=style,
            )
        )

    # The "no silent no-op" contract, which held only on the repository path. An authored rule that
    # styles nothing was unreportable here: no `unresolvable`, no `expected-empty`, no warning. The
    # same viewpoint therefore answered differently depending on how it was reached.
    #
    # `declared_derived_names` comes from the query's derived attributes. A definition with no query
    # declares none — and with no query there are no `derived.` references for an empty set to
    # misjudge. An empty set alongside a *present* query would report every derived reference as
    # unresolvable, which is why this reads the query rather than defaulting.
    declared_derived_names = frozenset(
        attribute.name for attribute in (definition.query.derived if definition.query is not None else ())
    )
    rule_outcomes = classify_style_rule_outcomes(
        definition.presentation,
        rule_hits,
        registries=registries,
        declared_derived_names=declared_derived_names,
    )

    stale_pin = application.pinned_version < definition.version
    return ViewpointProjection(
        target=application.target_kind,
        items=tuple(items),
        stale_pin=stale_pin,
        warnings=drift_warnings(frozenset(drift)) + rule_outcome_warnings(rule_outcomes),
        scale_legends=tuple(
            ScaleLegendData(
                capability=legend.capability,
                attribute=legend.attribute,
                minimum=legend.minimum,
                maximum=legend.maximum,
                tokens=legend.tokens,
                minimum_label=legend.minimum_label,
                maximum_label=legend.maximum_label,
            )
            for legend in scale_legends
        ),
        rule_outcomes=rule_outcomes,
    )


def project_artifact_by_frontmatter(
    fm: Mapping[str, object],
    *,
    target_kind: TargetKind,
    target_id: str,
    catalog: ViewpointCatalog,
    module: DiagramTypeModule,
    entity_type_infos: Mapping[str, EntityTypeInfo],
    default_enforcement: EnforcementSetting,
    registry: ArtifactRegistry,
    registries: RegistrySnapshot,
) -> ViewpointProjection | None:
    """Assemble the artifact-local projection for one diagram/matrix from its raw
    frontmatter — the second consumer of this service (alongside the verifier rule), used
    by the GUI ghost/hide overlay endpoint. Returns ``None`` when the artifact carries no
    ``viewpoint`` application (nothing to project). Unlike the verifier (which
    special-cases an unknown slug into its own E180 error and skips work under `off`
    enforcement), this always delegates to `project_artifact_local`, which already
    implements both cases (identity projection + warning; occlusion-only `off`).
    """
    raw = fm.get("viewpoint")
    if raw is None:
        return None
    application = parse_viewpoint_application(raw, target_kind=target_kind, target_id=target_id)
    if application is None:
        return None
    plain_fm = dict(fm)
    return project_artifact_local(
        catalog.get(application.viewpoint_slug),
        application,
        diagram_scope=module.concept_scope(),
        entity_type_infos=entity_type_infos,
        placed_entities=resolve_placed_entities(plain_fm, registry),
        placed_connections=resolve_placed_connections(plain_fm, registry),
        enforcement=application.enforcement_override or default_enforcement,
        read_access=registry,
        registries=registries,
    )
