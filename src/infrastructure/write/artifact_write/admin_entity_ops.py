"""Admin-mode entity writes (enterprise repo). See admin_ops for the boundary contract."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from src.application.identifier_allocator import get_default_allocator
from src.application.modeling.artifact_write_formatting import format_entity_markdown
from src.application.verification.artifact_verifier import ArtifactRegistry, ArtifactVerifier
from src.domain.modules.module_types import EntityTypeName

from ._admin_commit import commit_with_verification, dry_result
from ._entity_edit_support import _UNSET, merge_fields
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
    notes: object = _UNSET,
    keywords: object = _UNSET,
    version: str | None = None,
    status: str | None = None,
    dry_run: bool,
) -> WriteResult:
    assert_enterprise_write_root(repo_root)

    entity_file = registry.find_file_by_id(artifact_id)
    if entity_file is None:
        raise ValueError(f"Entity '{artifact_id}' not found in model")

    parsed = parse_entity_file(entity_file)
    # The address used to reach the file is not the file's identity. Both the full and the short
    # form resolve, and writing the short one back produced an `artifact-id` with no slug, which
    # fails its own id pattern (E101) — so the edit verified false and refused, for an entity that
    # was fine. The file declares what it is.
    artifact_id = str(parsed.frontmatter.get("artifact-id") or artifact_id)
    artifact_type = str(parsed.frontmatter.get("artifact-type", ""))
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    get_module_registry().get_entity_type(EntityTypeName(artifact_type))

    merged = merge_fields(
        parsed, name=name, version=version, status=status,
        keywords=keywords, summary=summary, properties=properties,
        attribute_types=_UNSET, notes=notes,
    )
    display_content = parsed.display_content
    if name is not None and display_content:
        display_content = re.sub(r"(?m)^(label:\s*).*$", rf"\g<1>{merged.name}", display_content, count=1)

    content = format_entity_markdown(
        artifact_id=artifact_id, artifact_type=artifact_type, name=merged.name, version=merged.version,
        status=merged.status, last_updated=modification_stamp(), keywords=merged.keywords, summary=merged.summary,
        specializations=merged.specializations,
        properties=merged.properties, attribute_types=merged.attribute_types, notes=merged.notes,
        display_section_id=parsed.display_section_id, display_content=display_content, repo_root=repo_root,
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
