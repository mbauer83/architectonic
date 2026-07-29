"""MCP write tools: promotion to enterprise."""

from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP  # type: ignore[import-not-found]

if TYPE_CHECKING:
    from src.infrastructure.write.artifact_write._promote_viewpoints import ViewpointResolution

from src.infrastructure.mcp.artifact_mcp.tool_annotations import DESTRUCTIVE_LOCAL_WRITE
from src.infrastructure.mcp.artifact_mcp.write._common import (
    clear_caches_for_repo,
    registry_cached,
    repo_cached,
    resolve_repo_roots,
    roots_key,
)


def artifact_promote_to_enterprise(
    *,
    entity_id: str,
    entity_ids: list[str] | None = None,
    connection_ids: list[str] | None = None,
    document_ids: list[str] | None = None,
    diagram_ids: list[str] | None = None,
    dry_run: bool = True,
    conflict_resolutions: list[dict[str, object]] | None = None,
    exclude_entities: list[str] | None = None,
    exclude_connections: list[str] | None = None,
    viewpoint_resolutions: dict[str, str] | None = None,
    group_mapping_resolutions: dict[str, str] | None = None,
    repo_root: str | None = None,
    enterprise_root: str | None = None,
) -> dict[str, object]:
    """Promote entities, connections, documents, and diagrams from engagement to enterprise repo.

    Defaults use repos from arch-init workspace config (repo_root, enterprise_root optional).
    Promotion is explicit: only the selected artifacts are promoted.
    After promotion, promoted engagement artifacts are replaced by GAR proxies.
    dry_run=true returns the plan without modifying any files.
    viewpoint_resolutions maps a viewpoint slug to 'promote_alongside' or 'repin'.
    """
    from typing import cast

    from src.infrastructure.app_bootstrap import build_runtime_catalogs, get_module_registry
    from src.infrastructure.mcp.artifact_mcp.context import resolve_enterprise_repo_root
    from src.infrastructure.write.artifact_write.promote_execute import execute_promotion
    from src.infrastructure.write.artifact_write.promote_to_enterprise import ConflictResolution, plan_promotion

    valid_viewpoint_resolutions = ("promote_alongside", "repin")
    invalid = sorted(
        f"{slug!r}: {value!r}"
        for slug, value in (viewpoint_resolutions or {}).items()
        if value not in valid_viewpoint_resolutions
    )
    if invalid:
        raise ValueError(
            f"Invalid viewpoint_resolutions ({', '.join(invalid)}); each value must be one of "
            f"{valid_viewpoint_resolutions}"
        )
    vp_resolutions = cast("dict[str, ViewpointResolution] | None", viewpoint_resolutions)

    eng_root = resolve_repo_roots(
        repo_scope="engagement",
        repo_root=repo_root,
        repo_preset=None,
        enterprise_root=None,
    )[0]
    ent_root = resolve_enterprise_repo_root(enterprise_root=enterprise_root)
    both_roots = resolve_repo_roots(
        repo_scope="both",
        repo_root=repo_root,
        repo_preset=None,
        enterprise_root=enterprise_root,
    )
    both_key = roots_key(both_roots)
    registry = registry_cached(both_key)
    repo = repo_cached(both_key)

    plan = plan_promotion(
        entity_id,
        registry,
        repo,
        entity_ids=entity_ids or [entity_id],
        connection_ids=set(connection_ids) if connection_ids else None,
        exclude_entity_ids=set(exclude_entities) if exclude_entities else None,
        exclude_connection_ids=set(exclude_connections) if exclude_connections else None,
        document_ids=document_ids or None,
        diagram_ids=diagram_ids or None,
        engagement_root=eng_root,
        enterprise_root=ent_root,
        catalogs=build_runtime_catalogs(get_module_registry()),
        viewpoint_resolutions=vp_resolutions,
    )

    out: dict[str, object] = {
        "dry_run": dry_run,
        "entity_id": entity_id,
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
        "connections_to_promote": plan.connection_ids,
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

    if not dry_run:
        from src.infrastructure.git.enterprise_git_ops import ensure_working_branch
        from src.infrastructure.write.artifact_write.promote_transaction import GitWorktreeTransaction

        ensure_working_branch(ent_root)

        resolutions = [
            ConflictResolution(
                engagement_id=str(r["engagement_id"]),
                strategy=r["strategy"],  # type: ignore[arg-type]
                merged_fields=r.get("merged_fields"),  # type: ignore[arg-type]
            )
            for r in (conflict_resolutions or [])
        ]
        result = execute_promotion(
            plan,
            eng_root,
            ent_root,
            registry,
            conflict_resolutions=resolutions,
            group_mapping_resolutions=group_mapping_resolutions or None,
            viewpoint_resolutions=vp_resolutions,
            transaction=GitWorktreeTransaction(ent_root),
        )
        out.update(
            {
                "executed": result.executed,
                "copied_files": result.copied_files,
                "updated_files": result.updated_files,
                "verification_errors": result.verification_errors,
                "rolled_back": result.rolled_back,
                # Execution can append warnings (e.g. incomplete GAR replacement) —
                # re-serialize so they are not lost behind the plan-time snapshot.
                "warnings": plan.warnings,
            }
        )
        if result.executed:
            clear_caches_for_repo(eng_root)

    return out


def register(mcp: FastMCP) -> None:
    from src.infrastructure.mcp.artifact_mcp.mutation_registration import register_mutation_tool  # noqa: PLC0415

    register_mutation_tool(
        mcp,
        artifact_promote_to_enterprise,
        name="artifact_promote_to_enterprise",
        title="Artifact Write: Promote to Enterprise",
        description=(
            "Promote an explicit selection of entities, connections, documents, and diagrams "
            "from the engagement repo to the enterprise repo (entity_ids, connection_ids, "
            "document_ids, diagram_ids; entity_id names the selection root). Defaults use "
            "arch-init workspace config. After successful promotion each promoted engagement "
            "artifact is replaced by a global-artifact-reference (GAR) proxy. dry_run=true "
            "returns the plan — including conflicts, missing_dependencies and viewpoint "
            "dependencies — without modifying files. conflict_resolutions, "
            "group_mapping_resolutions and viewpoint_resolutions resolve what the plan "
            "reports; exclude_entities / exclude_connections prune the selection."
        ),
        annotations=DESTRUCTIVE_LOCAL_WRITE,
        structured_output=True,
    )
