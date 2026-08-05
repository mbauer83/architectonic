"""Entity editing and promotion operations."""

import re
from collections.abc import Callable
from pathlib import Path

from src.application.modeling.artifact_write import format_entity_markdown, slugify
from src.application.profile_quarantine import assert_not_quarantined
from src.application.rename_followers import ArtifactRenamed, announce_rename
from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.domain.modules.module_types import EntityTypeName
from src.infrastructure.app_bootstrap import process_runtime_catalogs

from ._artifact_deduplication import get_repository, validate_entity_unique
from ._entity_edit_support import (
    _UNSET,
    MergedFields,
    count_rename_referrers,
    merge_fields,
)
from ._entity_rename import (
    apply_referrer_rewrites,
    plan_referrer_rewrites,
    rename_entity_via_m4,
    rewrite_document_links_for_moved_entity,
)
from .boundary import assert_engagement_write_root, modification_stamp
from .entity import entity_path, verification_to_entity_dict
from .parse_existing import ParsedEntity, parse_entity_file
from .types import WriteResult
from .verify import verify_content_in_temp_path

__all__ = ["_UNSET", "edit_entity", "promote_entity"]


def _resolve_target_identity(
    *,
    repo_root: Path,
    entity_file: Path,
    artifact_type: str,
    artifact_id: str,
    current_name: str,
    new_name: str | None,
    eff_name: str,
    group: str | None,
) -> tuple[str, Path]:
    """Resolve the artifact-id and file path a rename and/or group-move imply.

    Returns the (possibly unchanged) effective id and target file. Raises if a
    rename would collide with an existing file or a duplicate entity name.
    """
    effective_artifact_id = artifact_id
    target_entity_file = entity_file

    if new_name is not None and slugify(eff_name) != slugify(current_name):
        next_slug = slugify(eff_name)
        effective_artifact_id = f"{artifact_id.rsplit('.', 1)[0]}.{next_slug}"
        target_entity_file = entity_file.with_name(f"{effective_artifact_id}.md")
        if target_entity_file.exists() and target_entity_file != entity_file:
            raise ValueError(f"Target entity file already exists: {target_entity_file.name}")
        validate_entity_unique(
            get_repository(repo_root), artifact_type, next_slug, exclude_artifact_id=artifact_id
        )

    if group is not None:
        from src.application.repo_path_helpers import group_fn_entity  # noqa: PLC0415
        from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415, process_runtime_catalogs

        if group != group_fn_entity(entity_file, repo_root):
            info = get_module_registry().get_entity_type(EntityTypeName(artifact_type))
            target_entity_file = entity_path(repo_root, info, effective_artifact_id, group)
            target_entity_file.parent.mkdir(parents=True, exist_ok=True)

    return effective_artifact_id, target_entity_file


def _render_entity(
    *,
    parsed: ParsedEntity,
    merged: MergedFields,
    artifact_type: str,
    effective_artifact_id: str,
    name_changed: bool,
    repo_root: Path,
) -> str:
    """Format the entity markdown, relabelling the display block when the name changed."""
    display_content = parsed.display_content
    if name_changed and display_content:
        display_content = re.sub(r"(?m)^(label:\s*).*$", rf"\g<1>{merged.name}", display_content, count=1)
    return format_entity_markdown(
        artifact_id=effective_artifact_id,
        artifact_type=artifact_type,
        name=merged.name,
        version=merged.version,
        status=merged.status,
        last_updated=modification_stamp(),
        keywords=merged.keywords,
        specializations=merged.specializations,
        summary=merged.summary,
        properties=merged.properties,
        attribute_types=merged.attribute_types,
        notes=merged.notes,
        display_section_id=parsed.display_section_id,
        display_content=display_content,
        repo_root=repo_root,
    )


def _entity_result(
    *, wrote: bool, path: Path, artifact_id: str, content: str | None, warnings: list[str], verification: object
) -> WriteResult:
    return WriteResult(
        wrote=wrote,
        path=path,
        artifact_id=artifact_id,
        content=content,
        warnings=warnings,
        verification=verification_to_entity_dict(path, verification),
    )


def edit_entity(
    *,
    repo_root: Path,
    registry: ArtifactRegistry,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    name: str | None = None,
    summary: object = _UNSET,
    properties: object = _UNSET,
    attribute_types: object = _UNSET,
    notes: object = _UNSET,
    keywords: object = _UNSET,
    specializations: object = _UNSET,
    version: str | None = None,
    status: str | None = None,
    group: str | None = None,
    dry_run: bool,
) -> WriteResult:
    """Edit an existing entity file by merging partial updates.

    Only provided fields are changed; omitted fields keep their current value.
    ``last-updated`` is always bumped to today.
    """
    assert_engagement_write_root(repo_root)

    entity_file = registry.find_file_by_id(artifact_id)
    if entity_file is None:
        raise ValueError(f"Entity '{artifact_id}' not found in model")

    parsed = parse_entity_file(entity_file)
    # find_file_by_id() accepts the short form (PREFIX@epoch.random) as well as the full one,
    # so canonicalize before anything downstream consumes the id: the frontmatter it renders
    # must carry the full form the verifier requires, and _resolve_target_identity() rsplits
    # the slug off to build a rename target. The frontmatter is the authority for its own id.
    artifact_id = str(parsed.frontmatter.get("artifact-id", "")) or artifact_id
    artifact_type = str(parsed.frontmatter.get("artifact-type", ""))
    from src.infrastructure.app_bootstrap import (  # noqa: PLC0415, process_runtime_catalogs
        get_module_registry,
    )

    get_module_registry().get_entity_type(EntityTypeName(artifact_type))

    merged = merge_fields(
        parsed,
        name=name,
        version=version,
        status=status,
        keywords=keywords,
        specializations=specializations,
        summary=summary,
        properties=properties,
        attribute_types=attribute_types,
        notes=notes,
    )
    # Gate on the EFFECTIVE (post-merge) specialization set: an edit that moves an entity
    # onto a quarantined profile pair must be refused just like a create (WU-Q3).
    assert_not_quarantined(
        repo_root, "entity", artifact_type, list(merged.specializations) or [""],
        catalogs=process_runtime_catalogs(),
    )
    effective_artifact_id, target_entity_file = _resolve_target_identity(
        repo_root=repo_root,
        entity_file=entity_file,
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        current_name=str(parsed.frontmatter.get("name", "")),
        new_name=name,
        eff_name=merged.name,
        group=group,
    )
    content = _render_entity(
        parsed=parsed,
        merged=merged,
        artifact_type=artifact_type,
        effective_artifact_id=effective_artifact_id,
        name_changed=name is not None,
        repo_root=repo_root,
    )

    preview_res = verify_content_in_temp_path(
        verifier=verifier, file_type="entity", desired_name=target_entity_file.name, content=content,
        schema_repo_root=repo_root,
    )

    renamed = effective_artifact_id != artifact_id
    warnings: list[str] = []
    if dry_run:
        if renamed:
            impacted = count_rename_referrers(repo_root, artifact_id, entity_file.with_suffix(".outgoing.md"))
            warnings.append(
                f"Rename will update artifact-id to {effective_artifact_id} and rewrite {impacted} outgoing file(s)."
            )
        return _entity_result(
            wrote=False, path=target_entity_file, artifact_id=effective_artifact_id,
            content=content, warnings=warnings, verification=preview_res,
        )

    if not preview_res.valid:
        return _entity_result(
            wrote=False, path=target_entity_file, artifact_id=effective_artifact_id,
            content=content, warnings=warnings, verification=preview_res,
        )

    moved = target_entity_file != entity_file
    prev = entity_file.read_text(encoding="utf-8")

    if not moved:
        # In-place content update: single atomic write, no M4 needed
        entity_file.write_text(content, encoding="utf-8")
        res = verifier.verify_entity_file(entity_file)
        if not res.valid:
            entity_file.write_text(prev, encoding="utf-8")
            return _entity_result(
                wrote=False, path=entity_file, artifact_id=effective_artifact_id,
                content=content, warnings=warnings, verification=res,
            )
        clear_repo_caches(entity_file)
        return _entity_result(
            wrote=True, path=entity_file, artifact_id=effective_artifact_id,
            content=None, warnings=warnings, verification=res,
        )

    # Identity-changing rename
    old_sidecar = entity_file.with_suffix(".outgoing.md")
    if not old_sidecar.exists():
        # Sidecar-less: lone atomic os.rename (write new content, then rename atomically)
        import os  # noqa: PLC0415

        entity_file.write_text(content, encoding="utf-8")
        os.rename(str(entity_file), str(target_entity_file))
        res = verifier.verify_entity_file(target_entity_file)
        if not res.valid:
            os.rename(str(target_entity_file), str(entity_file))
            entity_file.write_text(prev, encoding="utf-8")
            return _entity_result(
                wrote=False, path=target_entity_file, artifact_id=effective_artifact_id,
                content=content, warnings=warnings, verification=res,
            )
        clear_repo_caches(entity_file)
        clear_repo_caches(target_entity_file)
        renamed_paths: list[Path] = []
        # The entity has no sidecar of its own, but other entities may still reference it,
        # and those references carry the slug that just changed.
        referrer_paths = apply_referrer_rewrites(
            plan_referrer_rewrites(repo_root=repo_root, new_artifact_id=effective_artifact_id)
        )
    else:
        # Rename with sidecar: route through M4 for atomic entity+sidecar commit
        new_sidecar = target_entity_file.with_suffix(".outgoing.md")

        def _rebuild_index_for_rename() -> None:
            for _p in (entity_file, target_entity_file, old_sidecar, new_sidecar):
                clear_repo_caches(_p)

        renamed_paths = rename_entity_via_m4(
            entity_file=entity_file,
            target_entity_file=target_entity_file,
            new_content=content,
            repo_root=repo_root,
            artifact_id=artifact_id,
            effective_artifact_id=effective_artifact_id,
            rebuild_index=_rebuild_index_for_rename,
        )
        res = preview_res  # intent already verified pre-write; M4 is idempotent post-commit
        # Every path the transaction wrote is reported, not only the four the index must re-read.
        # `clear_repo_caches` is how an *enclosing* transaction learns which files to carry out of
        # its staging repository: `artifact_bulk_write` builds its commit manifest from exactly the
        # paths its operations report. Reporting only the entity and its sidecar — on the grounds
        # that "referrers were committed inside the same transaction" — was true of the inner M4
        # commit and false of the outer one, so a rename in a batch renamed the entity and left
        # every referrer in the live repository naming the old slug, while the identical rename
        # through the single-entity path was correct.
        known = {entity_file, target_entity_file, old_sidecar, new_sidecar}
        referrer_paths = [path for path in renamed_paths if path not in known]

    for path in referrer_paths:
        clear_repo_caches(path)

    # Document-body relative links link by path, not by id, so neither the M4 transaction
    # nor the referrer rewrites touch them.
    doc_link_paths = rewrite_document_links_for_moved_entity(
        repo_root=repo_root, old_path=entity_file, new_path=target_entity_file
    )
    for path in doc_link_paths:
        clear_repo_caches(path)

    total_rewrites = len(renamed_paths) + len(referrer_paths) + len(doc_link_paths)
    warnings.append(f"Renamed artifact-id to {effective_artifact_id} and updated {total_rewrites} outgoing file(s).")
    # Announced after the rename is committed, never before: a tier that holds this id can then
    # follow, and one that cannot — a locked confidential store, an unconfigured capability — leaves
    # the rename alone. References there resolve by the id's stem, so they stay correct meanwhile and
    # the next rename heals them.
    warnings.extend(
        announce_rename(ArtifactRenamed(old_artifact_id=artifact_id, new_artifact_id=effective_artifact_id))
    )
    return _entity_result(
        wrote=True, path=target_entity_file, artifact_id=effective_artifact_id,
        content=None, warnings=warnings, verification=res,
    )


def promote_entity(
    *,
    repo_root: Path,
    registry: ArtifactRegistry,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    dry_run: bool,
) -> WriteResult:
    """Promote entity status: draft -> active -> deprecated.

    Bumps version (minor for draft->active, major for active->deprecated).
    Rejects promotion if entity has verification errors.
    """
    assert_engagement_write_root(repo_root)

    entity_file = registry.find_file_by_id(artifact_id)
    if entity_file is None:
        raise ValueError(f"Entity '{artifact_id}' not found in model")

    pre_check = verifier.verify_entity_file(entity_file)
    errors = [i for i in pre_check.issues if i.severity == "error"]
    if errors:
        raise ValueError(
            f"Cannot promote: {len(errors)} verification error(s): " + "; ".join(i.message for i in errors[:3])
        )

    parsed = parse_entity_file(entity_file)
    current_status = str(parsed.frontmatter.get("status", "draft"))

    promotion_map = {"draft": "active", "active": "deprecated"}
    next_status = promotion_map.get(current_status)
    if next_status is None:
        raise ValueError(f"Cannot promote from '{current_status}' — terminal state")

    current_version = str(parsed.frontmatter.get("version", "0.1.0"))
    new_version = _bump_version(current_version, current_status)

    return edit_entity(
        repo_root=repo_root,
        registry=registry,
        verifier=verifier,
        clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id,
        status=next_status,
        version=new_version,
        dry_run=dry_run,
    )


def _bump_version(version: str, current_status: str) -> str:
    """Bump version: draft->active bumps minor, active->deprecated bumps major."""
    parts = version.split(".")
    if len(parts) != 3:
        return version
    major, minor, _patch = int(parts[0]), int(parts[1]), int(parts[2])
    if current_status == "draft":
        return f"{major}.{minor + 1}.0"
    return f"{major + 1}.0.0"
