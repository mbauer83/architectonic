"""Promote artifacts from engagement to enterprise repository.

"Promote" means transferring artifact files from the engagement repo into the
enterprise repo.  Supported types: entities (+ connections), documents, diagrams.
This is a one-way operation.

Conflict detection:
- Entities: matched by (artifact_type, normalized_name) OR (artifact_type, id_suffix)
- Documents: matched by (doc_type, normalized_title)
- Diagrams:  matched by (diagram_type, normalized_name)

Schema superset verification (see promote_schema_check.py) blocks promotion when
engagement schemata are not supersets of the corresponding enterprise schemata.

Execution logic lives in promote_execute.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from src.application.artifacts.query import ArtifactRepository
from src.application.runtime_catalogs import RuntimeCatalogs
from src.application.verification.artifact_verifier import ArtifactRegistry
from src.infrastructure.write.artifact_write._promote_groups import GroupMappingEntry
from src.infrastructure.write.artifact_write._promote_planning import (
    _build_enterprise_id_suffix_index,
    _build_enterprise_name_index,
    _collect_promotable_connections,
    _entity_frontmatter,
    _match_enterprise,
    _normalize_name,
    _partition_selected,
    build_enterprise_classifier_indexes,
)
from src.infrastructure.write.artifact_write._promote_viewpoints import (
    ViewpointDependency,
    ViewpointResolution,
    collect_viewpoint_dependencies,
    viewpoint_dependency_errors,
)
from src.infrastructure.write.artifact_write.promote_reference_closure import (
    MissingDependency,
    compute_reference_closure,
    missing_dependency_errors,
)
from src.infrastructure.write.artifact_write.promote_schema_check import check_promotion_schema_compatibility
from src.infrastructure.write.artifact_write.promote_structural_closure import (
    StructuralClosureRequirement,
    compute_structural_closure,
    structural_closure_errors,
)
from src.infrastructure.write.artifact_write.promote_type_closure import compute_type_closure

__all__ = [
    "ConflictResolution",
    "DiagramPromotionConflict",
    "DocPromotionConflict",
    "MissingDependency",
    "PromotionConflict",
    "PromotionPlan",
    "PromotionResult",
    "ViewpointDependency",
    "ViewpointResolution",
    "_normalize_name",
    "plan_promotion",
]

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class PromotionConflict:
    """An engagement entity that matches an enterprise entity by type+name."""

    engagement_id: str
    enterprise_id: str
    artifact_type: str
    engagement_name: str
    enterprise_name: str
    engagement_fields: dict[str, Any]
    enterprise_fields: dict[str, Any]


@dataclass
class DocPromotionConflict:
    """An engagement document that matches an enterprise document by doc_type+title."""

    engagement_id: str
    enterprise_id: str
    doc_type: str
    engagement_title: str
    enterprise_title: str


@dataclass
class DiagramPromotionConflict:
    """An engagement diagram that matches an enterprise diagram by diagram_type+name."""

    engagement_id: str
    enterprise_id: str
    diagram_type: str
    engagement_name: str
    enterprise_name: str


@dataclass
class ConflictResolution:
    engagement_id: str
    strategy: Literal["accept_engagement", "accept_enterprise", "merge"]
    merged_fields: dict[str, Any] | None = None


@dataclass
class PromotionPlan:
    root_entity: str
    entities_to_add: list[str]
    conflicts: list[PromotionConflict]
    connection_ids: list[str]
    already_in_enterprise: list[str]
    warnings: list[str]
    documents_to_add: list[str] = field(default_factory=list)
    diagrams_to_add: list[str] = field(default_factory=list)
    doc_conflicts: list[DocPromotionConflict] = field(default_factory=list)
    diagram_conflicts: list[DiagramPromotionConflict] = field(default_factory=list)
    schema_errors: list[str] = field(default_factory=list)
    structural_closure: list[StructuralClosureRequirement] = field(default_factory=list)
    group_mapping: list[GroupMappingEntry] = field(default_factory=list)
    available_enterprise_groups: list[dict[str, str]] = field(default_factory=list)
    type_closure_additions: list[str] = field(default_factory=list)
    type_closure_reasons: dict[str, str] = field(default_factory=dict)
    broken_type_closure: list[str] = field(default_factory=list)
    viewpoint_dependencies: list[ViewpointDependency] = field(default_factory=list)
    missing_dependencies: list[MissingDependency] = field(default_factory=list)


@dataclass
class PromotionResult:
    plan: PromotionPlan
    executed: bool
    copied_files: list[str] = field(default_factory=list)
    updated_files: list[str] = field(default_factory=list)
    verification_errors: list[str] = field(default_factory=list)
    rolled_back: bool = False


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


def _classify_candidates(
    candidates: list[str],
    *,
    repo: ArtifactRepository,
    registry: ArtifactRegistry,
    name_index: dict[tuple[str, str], Any],
    suffix_index: dict[tuple[str, str], Any],
    warnings: list[str],
) -> tuple[list[str], list[PromotionConflict]]:
    """Sort candidates into clean additions and enterprise conflicts."""
    to_add: list[str] = []
    conflicts: list[PromotionConflict] = []
    for eid in candidates:
        rec = repo.get_entity(eid)
        if rec is None:
            warnings.append(f"Entity record not found for {eid}")
            continue
        ent_rec = _match_enterprise(rec, eid, name_index, suffix_index)
        if ent_rec is None:
            to_add.append(eid)
            continue
        conflicts.append(
            PromotionConflict(
                engagement_id=eid,
                enterprise_id=ent_rec.artifact_id,
                artifact_type=rec.artifact_type,
                engagement_name=rec.name,
                enterprise_name=ent_rec.name,
                engagement_fields=_entity_frontmatter(registry, eid),
                enterprise_fields=_entity_frontmatter(registry, ent_rec.artifact_id),
            )
        )
    return to_add, conflicts


def plan_promotion(
    entity_id: str | None,
    registry: ArtifactRegistry,
    repo: ArtifactRepository,
    *,
    entity_ids: list[str] | None = None,
    connection_ids: set[str] | None = None,
    exclude_entity_ids: set[str] | None = None,
    exclude_connection_ids: set[str] | None = None,
    document_ids: list[str] | None = None,
    diagram_ids: list[str] | None = None,
    engagement_root: Path | None = None,
    enterprise_root: Path | None = None,
    catalogs: RuntimeCatalogs | None = None,
    viewpoint_resolutions: Mapping[str, ViewpointResolution] | None = None,
) -> PromotionPlan:
    """Compute an explicit promotion plan from a caller-selected artifact set."""
    all_entities = registry.entity_ids()
    enterprise_ids = registry.enterprise_entity_ids()
    gar_ids = {eid for eid in all_entities if eid.startswith("GAR@")}

    selected_ids = list(dict.fromkeys(entity_ids or ([entity_id] if entity_id else [])))
    if not selected_ids and not document_ids and not diagram_ids:
        raise ValueError("At least one artifact must be selected for promotion")
    missing = [eid for eid in selected_ids if eid not in all_entities]
    if missing:
        raise ValueError(f"Entity '{missing[0]}' not found in model")

    ent_name_index = _build_enterprise_name_index(repo, registry)
    ent_id_suffix_index = _build_enterprise_id_suffix_index(repo, registry)
    warnings: list[str] = []
    already, candidates = _partition_selected(
        selected_ids, enterprise_ids=enterprise_ids, gar_ids=gar_ids, warnings=warnings
    )
    to_add, conflicts = _classify_candidates(
        candidates,
        repo=repo,
        registry=registry,
        name_index=ent_name_index,
        suffix_index=ent_id_suffix_index,
        warnings=warnings,
    )
    conn_ids = _collect_promotable_connections(
        registry,
        promotable=set(candidates),
        selected_set=set(selected_ids),
        explicit_connection_ids=set(connection_ids or ()),
    )

    exc_ents = exclude_entity_ids or set()
    exc_conns = exclude_connection_ids or set()
    if exc_ents:
        to_add = [e for e in to_add if e not in exc_ents]
        already = [e for e in already if e not in exc_ents]
        conflicts = [c for c in conflicts if c.engagement_id not in exc_ents]
    if exc_conns:
        conn_ids = [c for c in conn_ids if c not in exc_conns]

    from src.infrastructure.write.artifact_write._promote_plan_content import (  # noqa: PLC0415
        plan_diagrams,
        plan_docs,
    )

    docs_to_add, doc_conflicts = plan_docs(document_ids, repo, registry, already, warnings)
    clf_indexes = build_enterprise_classifier_indexes(repo, registry) if diagram_ids else None
    diags_to_add, diagram_conflicts = plan_diagrams(
        diagram_ids, repo, registry, already, warnings, classifier_indexes=clf_indexes
    )

    closure = compute_type_closure(diags_to_add, repo, registry)
    type_closure_additions = closure.additions
    type_closure_reasons = closure.reasons
    broken_type_closure = closure.broken
    if type_closure_additions:
        diags_to_add = list(dict.fromkeys(diags_to_add + type_closure_additions))

    schema_errors = check_promotion_schema_compatibility(
        entity_ids=to_add + [c.engagement_id for c in conflicts],
        has_diagrams=bool(diags_to_add or diagram_conflicts),
        document_ids=docs_to_add + [c.engagement_id for c in doc_conflicts],
        registry=registry,
        repo=repo,
        connection_ids=list(conn_ids),
        catalogs=catalogs,
    )
    for clf_id in broken_type_closure:
        schema_errors.append(
            f"Broken type closure: classifier {clf_id} is referenced in a promoted diagram "
            "but its host diagram cannot be found — exclude the referencing diagram or include its host"
        )
    structural_closure = compute_structural_closure(
        set(to_add) | {c.engagement_id for c in conflicts},
        repo=repo,
        enterprise_ids=set(enterprise_ids),
    )
    schema_errors.extend(structural_closure_errors(structural_closure))

    missing_dependencies: list[MissingDependency] = []
    if engagement_root is not None:
        from src.infrastructure.write.artifact_write.promote_schema_check import _default_catalogs  # noqa: PLC0415

        missing_dependencies = compute_reference_closure(
            document_ids=docs_to_add + [c.engagement_id for c in doc_conflicts],
            diagram_ids=diags_to_add + [c.engagement_id for c in diagram_conflicts],
            promoted_entity_ids=set(to_add) | {c.engagement_id for c in conflicts},
            repo=repo,
            registry=registry,
            engagement_root=engagement_root,
            catalogs=catalogs or _default_catalogs(),
        )
        schema_errors.extend(missing_dependency_errors(missing_dependencies))

    group_mapping: list[GroupMappingEntry] = []
    available_enterprise_groups: list[dict[str, str]] = []
    if engagement_root is not None and enterprise_root is not None:
        from src.infrastructure.write.artifact_write._promote_groups import compute_group_mapping  # noqa: PLC0415

        all_entity_ids = to_add + [c.engagement_id for c in conflicts]
        group_mapping, available_enterprise_groups = compute_group_mapping(
            all_entity_ids, registry, engagement_root, enterprise_root
        )

    viewpoint_dependencies: list[ViewpointDependency] = []
    if engagement_root is not None and enterprise_root is not None:
        promoted_diagram_ids = diags_to_add + [c.engagement_id for c in diagram_conflicts]
        viewpoint_dependencies = collect_viewpoint_dependencies(
            promoted_diagram_ids, repo=repo, ent_root=enterprise_root
        )
        schema_errors.extend(
            viewpoint_dependency_errors(
                viewpoint_dependencies,
                eng_root=engagement_root,
                ent_root=enterprise_root,
                catalogs=catalogs,
                resolutions=viewpoint_resolutions,
            )
        )

    return PromotionPlan(
        root_entity=selected_ids[0] if selected_ids else (document_ids or diagram_ids or [""])[0],
        entities_to_add=to_add,
        conflicts=conflicts,
        connection_ids=conn_ids,
        already_in_enterprise=already,
        warnings=warnings,
        documents_to_add=docs_to_add,
        diagrams_to_add=diags_to_add,
        doc_conflicts=doc_conflicts,
        diagram_conflicts=diagram_conflicts,
        schema_errors=schema_errors,
        structural_closure=structural_closure,
        group_mapping=group_mapping,
        available_enterprise_groups=available_enterprise_groups,
        viewpoint_dependencies=viewpoint_dependencies,
        missing_dependencies=missing_dependencies,
        type_closure_additions=type_closure_additions,
        type_closure_reasons=type_closure_reasons,
        broken_type_closure=broken_type_closure,
    )
