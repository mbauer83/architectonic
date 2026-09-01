"""Admin-mode entity writes (enterprise repo). See admin_ops for the boundary contract."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.application.identifier_allocator import get_default_allocator
from src.application.modeling.artifact_write_formatting import format_entity_markdown
from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.domain.modules.module_types import EntityTypeName

from ._admin_commit import commit_with_verification, dry_result
from ._entity_edit_support import _UNSET, merge_fields, render_entity, subject_of
from .boundary import assert_enterprise_write_root, modification_stamp
from .entity import verification_to_entity_dict
from .entity_delete import _delete_entity_core
from .parse_existing import parse_entity_file
from .types import WriteResult
from .verify import verify_content_in_temp_path

__all__ = ["_UNSET", "admin_create_entity", "admin_delete_entity", "admin_edit_entity"]


def admin_create_entity(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    artifact_type: str,
    name: str,
    summary: str | None,
    properties: dict[str, str] | None,
    notes: str | None,
    keywords: list[str] | None = None,
    artifact_id: str | None,
    version: str,
    status: str,
    last_updated: str | None,
    dry_run: bool,
) -> WriteResult:
    assert_enterprise_write_root(repo_root)
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    info = get_module_registry().find_entity_type(EntityTypeName(artifact_type))
    if info is None:
        raise ValueError(f"Unknown entity artifact_type: {artifact_type!r}")

    eid = artifact_id or get_default_allocator().allocate(prefix=info.prefix, name_hint=name)
    from src.infrastructure.write.artifact_write.entity import _render_display, entity_path  # noqa: PLC0415

    path = entity_path(repo_root, info, eid)
    display_section_id, display_content = _render_display(info, name, eid)
    content = format_entity_markdown(
        artifact_id=eid, artifact_type=artifact_type, name=name, version=version, status=status,
        last_updated=last_updated or modification_stamp(), keywords=keywords, summary=summary,
        properties=properties, notes=notes, display_section_id=display_section_id,
        display_content=display_content, repo_root=repo_root,
    )

    if dry_run:
        res = verify_content_in_temp_path(
            verifier=verifier, file_type="entity", desired_name=path.name, content=content,
            schema_repo_root=repo_root,
        )
        return dry_result(
            path=path, artifact_id=eid, content=content, verification=verification_to_entity_dict(path, res)
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    return commit_with_verification(
        path=path, content=content, artifact_id=eid, verify=verifier.verify_entity_file,
        to_dict=verification_to_entity_dict, clear_repo_caches=clear_repo_caches,
    )


def admin_edit_entity(
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
    dry_run: bool,
) -> WriteResult:
    """Edit an enterprise entity, over the same field vocabulary an engagement edit has.

    `attribute_types` and `specializations` were absent here — not refused, just never given. The
    merge call had them wired to "keep whatever is there", so an enterprise entity's declared
    attribute types and specializations could be read and written back but never changed, through
    either of the two authorised paths into this repository. Nothing said so: no refusal, no comment,
    no test. Promotion, the other path, carries both.
    """
    assert_enterprise_write_root(repo_root)

    entity_file = registry.find_file_by_id(artifact_id)
    if entity_file is None:
        raise ValueError(f"Entity '{artifact_id}' not found in model")

    parsed = parse_entity_file(entity_file)
    subject = subject_of(parsed, addressed_as=artifact_id)
    artifact_id, artifact_type = subject.artifact_id, subject.artifact_type

    merged = merge_fields(
        parsed, name=name, version=version, status=status,
        keywords=keywords, specializations=specializations, summary=summary, properties=properties,
        attribute_types=attribute_types, notes=notes,
    )
    content = render_entity(
        parsed=parsed, merged=merged, artifact_type=artifact_type,
        # No relocation: an enterprise edit renames nothing and moves nothing, so the effective id is
        # the one the file already declares.
        effective_artifact_id=artifact_id, name_changed=name is not None, repo_root=repo_root,
    )

    if dry_run:
        res = verify_content_in_temp_path(
            verifier=verifier, file_type="entity", desired_name=entity_file.name, content=content,
            schema_repo_root=repo_root,
        )
        return dry_result(
            path=entity_file, artifact_id=artifact_id, content=content,
            verification=verification_to_entity_dict(entity_file, res),
        )

    return commit_with_verification(
        path=entity_file, content=content, artifact_id=artifact_id, verify=verifier.verify_entity_file,
        to_dict=verification_to_entity_dict, clear_repo_caches=clear_repo_caches,
    )


def admin_delete_entity(
    *,
    repo_root: Path,
    registry: ArtifactRegistry,
    clear_repo_caches: Callable[[Path], None],
    artifact_id: str,
    dry_run: bool,
) -> WriteResult:
    assert_enterprise_write_root(repo_root)
    return _delete_entity_core(
        repo_root=repo_root, registry=registry, clear_repo_caches=clear_repo_caches,
        artifact_id=artifact_id, dry_run=dry_run,
    )
