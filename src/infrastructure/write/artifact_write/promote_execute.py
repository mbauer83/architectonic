"""Execute a promotion plan — copy artifact files to enterprise repo."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.application.artifacts.query import ArtifactRepository
from src.application.verification.artifact_verifier import ArtifactRegistry
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.artifact_index import notify_paths_changed, shared_artifact_index
from src.infrastructure.verification.verifier_factory import build_artifact_verifier
from src.infrastructure.write.artifact_write._promote_conflicts import build_handler
from src.infrastructure.write.artifact_write._promote_file_ops import (
    TargetResolver,
    copy_entity,
    copy_simple,
    make_target_resolver,
    update_body_references,
    update_outgoing_references,
)
from src.infrastructure.write.artifact_write._promote_viewpoints import ViewpointResolution, apply_viewpoint_resolutions
from src.infrastructure.write.artifact_write.parse_existing import parse_entity_file
from src.infrastructure.write.artifact_write.promote_to_enterprise import (
    ConflictResolution,
    PromotionPlan,
    PromotionResult,
)
from src.infrastructure.write.artifact_write.promote_transaction import (
    FileBackupTransaction,
    PromotionTransaction,
)
from src.infrastructure.write.artifact_write.verify import collect_verification_errors


@dataclass
class _ExecCtx:
    """Shared state threaded through the phases of a single promotion execution."""

    plan: PromotionPlan
    engagement_root: Path
    enterprise_root: Path
    registry: ArtifactRegistry
    result: PromotionResult
    eng_repo: ArtifactRepository
    resolve_target: TargetResolver
    conn_ids: set[str]
    resolutions: dict[str, ConflictResolution]
    slug_remap: dict[str, str]
    ent_copied: list[Path] = field(default_factory=list)
    ent_backups: list[tuple[Path, bytes | None]] = field(default_factory=list)


def _copy_entities(ctx: _ExecCtx) -> None:
    for eid in ctx.plan.entities_to_add:
        copy_entity(
            eid, ctx.engagement_root, ctx.enterprise_root, ctx.registry, ctx.result,
            ctx.ent_copied, ctx.ent_backups, ctx.resolve_target, ctx.conn_ids,
            group_slug_remap=ctx.slug_remap or None,
        )


def _apply_entity_conflicts(ctx: _ExecCtx) -> None:
    for conflict in ctx.plan.conflicts:
        res = ctx.resolutions.get(conflict.engagement_id)
        if res is None:
            ctx.result.plan.warnings.append(f"No resolution for conflict {conflict.engagement_id} — skipped")
            continue
        handler = build_handler(res)
        if handler is None:
            ctx.result.plan.warnings.append(
                f"Unrecognised resolution strategy {res.strategy!r} for {conflict.engagement_id} — skipped"
            )
            continue
        handler.handle(
            conflict, ctx.engagement_root, ctx.enterprise_root, ctx.registry,
            ctx.result, ctx.ent_backups, ctx.resolve_target, ctx.conn_ids,
        )


def _copy_simple_artifacts(ctx: _ExecCtx) -> None:
    def _copy(did: str) -> None:
        copy_simple(
            did, ctx.engagement_root, ctx.enterprise_root, ctx.registry,
            ctx.result, ctx.ent_copied, ctx.ent_backups, ctx.slug_remap,
        )

    def _resolve(dc: Any, kind: str) -> None:
        _resolve_simple_conflict(
            dc, kind, ctx.engagement_root, ctx.enterprise_root, ctx.registry,
            ctx.result, ctx.ent_backups, ctx.resolutions,
        )

    for did in ctx.plan.documents_to_add:
        _copy(did)
    for dc in ctx.plan.doc_conflicts:
        _resolve(dc, "document")
    for did in ctx.plan.diagrams_to_add:
        _copy(did)
    for diag_dc in ctx.plan.diagram_conflicts:
        _resolve(diag_dc, "diagram")


def _accepted_engagement_ids(confs: list[Any], resolutions: dict[str, ConflictResolution]) -> list[str]:
    return [
        c.engagement_id
        for c in confs
        if (r := resolutions.get(c.engagement_id)) is not None and r.strategy == "accept_engagement"
    ]


def _replace_promoted_with_gars(ctx: _ExecCtx) -> None:
    plan = ctx.plan
    for eid in list(plan.entities_to_add) + [c.engagement_id for c in plan.conflicts]:
        _replace_artifact_with_gar(eid, ctx.engagement_root, ctx.eng_repo, ctx.registry, ctx.result, "entity")
    for did in plan.documents_to_add + _accepted_engagement_ids(plan.doc_conflicts, ctx.resolutions):
        doc = ctx.eng_repo.get_document(did)
        _replace_artifact_with_gar(
            did, ctx.engagement_root, ctx.eng_repo, ctx.registry, ctx.result, "document",
            name=doc.title if doc else did,
        )
    for did in plan.diagrams_to_add + _accepted_engagement_ids(plan.diagram_conflicts, ctx.resolutions):
        diag = ctx.eng_repo.get_diagram(did)
        _replace_artifact_with_gar(
            did, ctx.engagement_root, ctx.eng_repo, ctx.registry, ctx.result, "diagram",
            name=diag.name if diag else did,
        )


def execute_promotion(
    plan: PromotionPlan,
    engagement_root: Path,
    enterprise_root: Path,
    registry: ArtifactRegistry,
    *,
    conflict_resolutions: list[ConflictResolution] | None = None,
    group_mapping_resolutions: dict[str, str] | None = None,
    viewpoint_resolutions: Mapping[str, ViewpointResolution] | None = None,
    transaction: PromotionTransaction | None = None,
) -> PromotionResult:
    """Execute a plan: enterprise writes inside *transaction*, then engagement cleanup.

    The transaction brackets every enterprise-side write; callers that promote on
    the enterprise working branch pass a ``GitWorktreeTransaction`` so an abort is
    a branch reset. Engagement-side GAR replacement runs strictly AFTER the
    transaction commits: a failure there must never take the (verified) enterprise
    state down with it — that would unlink engagement originals while rolling back
    the enterprise copies, losing the artifact on both sides.
    """
    result = PromotionResult(plan=plan, executed=False)
    if plan.schema_errors:
        result.verification_errors = list(plan.schema_errors)
        return result

    from src.infrastructure.write.artifact_write.global_artifact_reference import build_gar_map  # noqa: PLC0415

    eng_repo = ArtifactRepository(shared_artifact_index(engagement_root))
    promoted_ids = set(plan.entities_to_add) | {c.engagement_id for c in plan.conflicts}
    slug_remap = group_mapping_resolutions or {}
    ctx = _ExecCtx(
        plan=plan,
        engagement_root=engagement_root,
        enterprise_root=enterprise_root,
        registry=registry,
        result=result,
        eng_repo=eng_repo,
        resolve_target=make_target_resolver(build_gar_map(eng_repo), promoted_ids, registry.enterprise_entity_ids()),
        conn_ids=set(plan.connection_ids),
        resolutions={r.engagement_id: r for r in (conflict_resolutions or [])},
        slug_remap=slug_remap,
    )
    tx = transaction if transaction is not None else FileBackupTransaction(ctx.ent_copied, ctx.ent_backups)

    try:
        tx.begin()
    except Exception as exc:  # noqa: BLE001
        result.verification_errors.append(f"Could not begin the promotion transaction — nothing written: {exc}")
        return result

    try:
        _copy_entities(ctx)
        _apply_entity_conflicts(ctx)
        _copy_simple_artifacts(ctx)
        apply_viewpoint_resolutions(
            plan.viewpoint_dependencies,
            viewpoint_resolutions,
            engagement_root=engagement_root,
            enterprise_root=enterprise_root,
            registry=registry,
            backups=ctx.ent_backups,
        )
        if ctx.ent_copied:
            notify_paths_changed(ctx.ent_copied)

        result.verification_errors = collect_verification_errors(enterprise_root, include_diagrams=True)
        if result.verification_errors:
            tx.abort()
            notify_paths_changed([enterprise_root])
            result.rolled_back = True
            return result

        if plan.group_mapping:
            from src.infrastructure.write.artifact_write._promote_groups import (  # noqa: PLC0415
                update_enterprise_groups,
            )

            update_enterprise_groups(enterprise_root, engagement_root, plan.group_mapping, slug_remap)

        tx.commit()
        result.executed = True
    except Exception as exc:  # noqa: BLE001
        tx.abort()
        notify_paths_changed([enterprise_root])
        result.rolled_back = True
        result.executed = False
        result.verification_errors.append(str(exc))
        return result

    try:
        _replace_promoted_with_gars(ctx)
        notify_paths_changed([engagement_root])
    except Exception as exc:  # noqa: BLE001
        result.plan.warnings.append(
            "Promotion succeeded, but replacing the promoted engagement artifacts with GAR "
            f"proxies did not complete: {exc}. The enterprise repository is intact and was NOT "
            "rolled back; the engagement repository may still hold originals of promoted "
            "artifacts. Review the engagement copies of the promoted artifacts and remove or "
            "convert the leftovers."
        )
    return result


def _resolve_simple_conflict(
    dc: Any,
    kind: str,
    eng_root: Path,
    ent_root: Path,
    registry: Any,
    result: Any,
    backups: list[Any],
    resolutions: dict[str, Any],
) -> None:
    res = resolutions.get(dc.engagement_id)
    if res and res.strategy == "accept_engagement":
        eng_path = registry.find_file_by_id(dc.engagement_id)
        ent_path = registry.find_file_by_id(dc.enterprise_id)
        if not eng_path or not ent_path:
            result.plan.warnings.append(f"Could not find files for conflict {dc.engagement_id}")
            return
        content = eng_path.read_text(encoding="utf-8").replace(dc.engagement_id, dc.enterprise_id, 1)
        backups.append((ent_path, ent_path.read_bytes()))
        ent_path.write_text(content, encoding="utf-8")
        result.updated_files.append(str(ent_path.relative_to(ent_root)))
    elif res and res.strategy not in ("accept_enterprise", None):
        result.plan.warnings.append(f"Merge not supported for {kind}s; skipping {dc.engagement_id}")


def _infer_gar_name_subtype(src: Path, aid: str, artifact_type: str, name: str | None) -> tuple[str, str | None]:
    """Resolve the GAR display name and (for entities) the underlying entity subtype from the source file."""
    if name is not None and artifact_type != "entity":
        return name, None
    try:
        fm = parse_entity_file(src).frontmatter
        resolved_name = name if name is not None else str(fm.get("name", aid))
        subtype = (str(fm.get("artifact-type", "")) or None) if artifact_type == "entity" else None
        return resolved_name, subtype
    except Exception:  # noqa: BLE001
        return (name if name is not None else aid), None


def _remove_promoted_file(path: Path, eng_root: Path, result: Any) -> None:
    """Unlink a promoted source file, recording the removal; missing files are ignored."""
    try:
        path.unlink()
        result.updated_files.append(f"[removed] {path.relative_to(eng_root)}")
    except OSError:
        pass


def _replace_artifact_with_gar(
    aid: str,
    eng_root: Path,
    eng_repo: Any,
    registry: Any,
    result: Any,
    artifact_type: str,
    *,
    name: str | None = None,
) -> None:
    """Replace a promoted engagement artifact with a GAR proxy."""
    src = registry.find_file_by_id(aid)
    if src is None or not src.is_relative_to(eng_root):
        return
    name, entity_subtype = _infer_gar_name_subtype(src, aid, artifact_type, name)

    from src.infrastructure.write.artifact_write.global_artifact_reference import (
        ensure_global_artifact_reference,  # noqa: PLC0415
    )

    gar_result = ensure_global_artifact_reference(
        engagement_repo=eng_repo,
        engagement_root=eng_root,
        verifier=build_artifact_verifier(None, catalogs=process_runtime_catalogs()),
        clear_repo_caches=lambda _: None,
        global_artifact_id=aid,
        global_artifact_name=name,
        global_artifact_type=artifact_type,
        global_artifact_entity_type=entity_subtype,
        dry_run=False,
    )
    result.updated_files.append(f"[created GAR] {gar_result.artifact_id}")

    if artifact_type == "entity":
        update_outgoing_references(aid, gar_result.artifact_id, eng_root, result)
    else:
        update_body_references(aid, eng_root, result)

    _remove_promoted_file(src, eng_root, result)
    if artifact_type == "entity":
        outgoing = src.with_suffix(".outgoing.md")
        if outgoing.exists():
            _remove_promoted_file(outgoing, eng_root, result)
