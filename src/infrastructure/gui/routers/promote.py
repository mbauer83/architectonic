"""Promotion endpoints — plan and execute entity promotion to enterprise repo."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.application.runtime_catalogs import RuntimeCatalogs
from src.infrastructure.app_bootstrap import runtime_catalogs_dependency
from src.infrastructure.gui.contracts.promotion import (
    PromotionPlanResponse,
    PromotionResultResponse,
)
from src.infrastructure.gui.routers import state as s

router = APIRouter()


class PromotionPlanBody(BaseModel):
    entity_id: str | None = None
    entity_ids: list[str] = []
    connection_ids: list[str] = []
    exclude_entity_ids: list[str] = []
    exclude_connection_ids: list[str] = []
    document_ids: list[str] = []
    diagram_ids: list[str] = []
    viewpoint_resolutions: dict[str, Literal["promote_alongside", "repin"]] = {}


class ConflictResolutionBody(BaseModel):
    engagement_id: str
    strategy: Literal["accept_engagement", "accept_enterprise", "merge"]
    merged_fields: dict[str, Any] | None = None


class PromotionExecuteBody(BaseModel):
    entity_id: str | None = None
    entity_ids: list[str] = []
    connection_ids: list[str] = []
    exclude_entity_ids: list[str] = []
    exclude_connection_ids: list[str] = []
    document_ids: list[str] = []
    diagram_ids: list[str] = []
    conflict_resolutions: list[ConflictResolutionBody] = []
    group_mapping_resolutions: dict[str, str] = {}
    viewpoint_resolutions: dict[str, Literal["promote_alongside", "repin"]] = {}
    dry_run: bool = True


@router.post("/api/promote/plan", response_model=PromotionPlanResponse)
def promotion_plan(
    body: PromotionPlanBody,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    """Compute the promotion plan for an explicit selection of entities and connections."""
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry
    from src.infrastructure.artifact_index import combined_artifact_index
    from src.infrastructure.write.artifact_write.promote_to_enterprise import plan_promotion

    eng_root, ent_root = s.get_both_roots()
    registry = ArtifactRegistry(combined_artifact_index(eng_root, ent_root))
    repo = s.get_repo()
    try:
        plan = plan_promotion(
            body.entity_id,
            registry,
            repo,
            entity_ids=body.entity_ids or None,
            connection_ids=set(body.connection_ids) or None,
            exclude_entity_ids=set(body.exclude_entity_ids) or None,
            exclude_connection_ids=set(body.exclude_connection_ids) or None,
            document_ids=body.document_ids or None,
            diagram_ids=body.diagram_ids or None,
            engagement_root=eng_root,
            enterprise_root=ent_root,
            catalogs=catalogs,
            viewpoint_resolutions=body.viewpoint_resolutions or None,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {
        "entity_id": body.entity_id or (body.entity_ids[0] if body.entity_ids else ""),
        "entities_to_add": plan.entities_to_add,
        "conflicts": [
            {
                "engagement_id": c.engagement_id,
                "enterprise_id": c.enterprise_id,
                "artifact_type": c.artifact_type,
                "engagement_name": c.engagement_name,
                "enterprise_name": c.enterprise_name,
                "engagement_fields": c.engagement_fields,
                "enterprise_fields": c.enterprise_fields,
            }
            for c in plan.conflicts
        ],
        "connection_ids": plan.connection_ids,
        "already_in_enterprise": plan.already_in_enterprise,
        "documents_to_add": plan.documents_to_add,
        "diagrams_to_add": plan.diagrams_to_add,
        "doc_conflicts": [
            {
                "engagement_id": c.engagement_id,
                "enterprise_id": c.enterprise_id,
                "doc_type": c.doc_type,
                "engagement_title": c.engagement_title,
                "enterprise_title": c.enterprise_title,
            }
            for c in plan.doc_conflicts
        ],
        "diagram_conflicts": [
            {
                "engagement_id": c.engagement_id,
                "enterprise_id": c.enterprise_id,
                "diagram_type": c.diagram_type,
                "engagement_name": c.engagement_name,
                "enterprise_name": c.enterprise_name,
            }
            for c in plan.diagram_conflicts
        ],
        "warnings": plan.warnings,
        "schema_errors": plan.schema_errors,
        "structural_closure": [
            {
                "entity_id": r.entity_id,
                "entity_name": r.entity_name,
                "kind": r.kind,
                "missing": [
                    {"artifact_id": m.artifact_id, "name": m.name, "artifact_type": m.artifact_type}
                    for m in r.missing
                ],
            }
            for r in plan.structural_closure
        ],
        "group_mapping": [
            {
                "engagement_slug": m.engagement_slug,
                "engagement_group_id": m.engagement_group_id,
                "match_status": m.match_status,
                "enterprise_slug": m.enterprise_slug,
                "enterprise_group_id": m.enterprise_group_id,
            }
            for m in plan.group_mapping
        ],
        "available_enterprise_groups": plan.available_enterprise_groups,
        "viewpoint_dependencies": [
            {
                "target_id": d.target_id,
                "target_kind": d.target_kind,
                "slug": d.slug,
                "pinned_version": d.pinned_version,
                "status": d.status,
                "enterprise_version": d.enterprise_version,
            }
            for d in plan.viewpoint_dependencies
        ],
        "missing_dependencies": [
            {
                "artifact_id": m.artifact_id,
                "name": m.name,
                "record_type": m.record_type,
                "required_by": m.required_by,
                "kind": m.kind,
            }
            for m in plan.missing_dependencies
        ],
    }


@router.post("/api/promote/execute", response_model=PromotionResultResponse)
def promotion_execute(
    body: PromotionExecuteBody,
    catalogs: RuntimeCatalogs = Depends(runtime_catalogs_dependency),
) -> dict[str, Any]:
    """Execute a promotion plan built from an explicit selection of entities and connections."""
    from src.application.verification.artifact_verifier_registry import ArtifactRegistry
    from src.infrastructure.artifact_index import combined_artifact_index
    from src.infrastructure.write.artifact_write.promote_execute import execute_promotion
    from src.infrastructure.write.artifact_write.promote_to_enterprise import ConflictResolution, plan_promotion

    eng_root, ent_root = s.get_both_roots()
    registry = ArtifactRegistry(combined_artifact_index(eng_root, ent_root))
    repo = s.get_repo()
    try:
        plan = plan_promotion(
            body.entity_id,
            registry,
            repo,
            entity_ids=body.entity_ids or None,
            connection_ids=set(body.connection_ids) or None,
            exclude_entity_ids=set(body.exclude_entity_ids) or None,
            exclude_connection_ids=set(body.exclude_connection_ids) or None,
            document_ids=body.document_ids or None,
            diagram_ids=body.diagram_ids or None,
            engagement_root=eng_root,
            enterprise_root=ent_root,
            catalogs=catalogs,
            viewpoint_resolutions=body.viewpoint_resolutions or None,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    if body.dry_run:
        return {
            "dry_run": True,
            "executed": False,
            "copied_files": [],
            "updated_files": [],
            "verification_errors": [],
            "rolled_back": False,
        }

    from src.infrastructure.git.enterprise_git_ops import ensure_working_branch
    from src.infrastructure.write.artifact_write.promote_transaction import GitWorktreeTransaction

    resolutions = [
        ConflictResolution(
            engagement_id=r.engagement_id,
            strategy=r.strategy,
            merged_fields=r.merged_fields,
        )
        for r in body.conflict_resolutions
    ]

    def _branch_and_promote():
        # One write lease for the whole promotion transaction: working branch +
        # copy + state update. Failure resets the branch — never a file loop.
        ensure_working_branch(ent_root)
        return execute_promotion(
            plan,
            eng_root,
            ent_root,
            registry,
            conflict_resolutions=resolutions,
            group_mapping_resolutions=body.group_mapping_resolutions or None,
            viewpoint_resolutions=body.viewpoint_resolutions or None,
            transaction=GitWorktreeTransaction(ent_root),
        )

    result = s.authorized_write(
            "promotion_execute_promotion", _branch_and_promote)
    if result.executed:
        repo.refresh()
    return {
        "dry_run": False,
        "executed": result.executed,
        "copied_files": result.copied_files,
        "updated_files": result.updated_files,
        "verification_errors": result.verification_errors,
        "rolled_back": result.rolled_back,
        "warnings": result.plan.warnings,
    }
