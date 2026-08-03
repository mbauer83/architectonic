from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from src.application.entity_type_predicates import is_internal_entity_type
from src.application.identifier_allocator import get_default_allocator
from src.application.modeling.artifact_write import format_entity_markdown
from src.application.profile_quarantine import assert_not_quarantined
from src.application.repo_path_helpers import model_root_legacy
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.domain.modules.module_types import EntityTypeName
from src.domain.ontology_representation.ontology_types import EntityTypeInfo
from src.domain.repository.groups import UNCATEGORIZED
from src.infrastructure.app_bootstrap import process_runtime_catalogs
from src.infrastructure.atomic_file import write_atomic

from ._artifact_deduplication import (
    ensure_unique_entity_random_part,
    extract_friendly_slug,
    get_repository,
    validate_entity_unique,
)
from .boundary import assert_engagement_write_root, modification_stamp, normalize_specializations
from .types import WriteResult
from .verify import verify_content_in_temp_path


def verification_to_entity_dict(path: Path, res) -> dict[str, object]:
    return {
        "path": str(path),
        "file_type": "entity",
        "valid": res.valid,
        "issues": [
            {"severity": i.severity, "code": i.code, "message": i.message, "location": i.location} for i in res.issues
        ],
    }


def entity_path(repo_root: Path, info: EntityTypeInfo, eid: str, group: str = UNCATEGORIZED) -> Path:
    """Return the target path for an entity file.

    Legacy (uncategorized) : <repo>/model/<domain>/<type>/<id>.md
    Group-aware (target)   : <repo>/projects/<group>/model/<domain>/<type>/<id>.md
    """
    if group == UNCATEGORIZED:
        return model_root_legacy(repo_root) / Path(*info.hierarchy) / f"{eid}.md"
    return repo_root / "projects" / group / "model" / Path(*info.hierarchy) / f"{eid}.md"


def _alias_for(info: EntityTypeInfo, eid: str) -> str:
    return f"{info.prefix}_{eid.split('.')[1]}" if "." in eid else eid.replace("-", "_")


def _render_display(info: EntityTypeInfo, name: str, eid: str) -> tuple[str, str]:
    """Return ``(display_section_id, display_content)`` for a new entity."""
    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415, process_runtime_catalogs

    ontology = get_module_registry().ontology_for_entity_type(EntityTypeName(info.artifact_type))
    if ontology is None:
        return "archimate", f"label: {name}\nalias: {_alias_for(info, eid)}"
    return ontology.display_section_id, ontology.render_display_section(info.artifact_type, name, _alias_for(info, eid))


def create_entity(
    *,
    repo_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    artifact_type: str,
    name: str,
    summary: str | None,
    properties: dict[str, Any] | None,
    attribute_types: dict[str, str] | None = None,
    notes: str | None,
    keywords: list[str] | None = None,
    specializations: Sequence[str] | None = None,
    artifact_id: str | None,
    version: str,
    status: str,
    last_updated: str | None,
    dry_run: bool,
    group: str = UNCATEGORIZED,
) -> WriteResult:
    assert_engagement_write_root(repo_root)

    from src.infrastructure.app_bootstrap import (  # noqa: PLC0415, process_runtime_catalogs
        get_module_registry,
    )

    catalogs = process_runtime_catalogs()
    if is_internal_entity_type(artifact_type, catalogs.ontology):
        raise ValueError(
            "global-artifact-reference entities may not be created directly. "
            "Use ensure_global_artifact_reference (MCP) or "
            "POST /api/global-entity-reference (GUI) instead."
        )
    applied = normalize_specializations(specializations)
    assert_not_quarantined(repo_root, "entity", artifact_type, list(applied) or [""], catalogs=catalogs)

    info = get_module_registry().find_entity_type(EntityTypeName(artifact_type))
    if info is None:
        raise ValueError(f"Unknown entity artifact_type: {artifact_type!r}")

    last = last_updated or modification_stamp()

    eid = artifact_id or get_default_allocator().allocate(prefix=info.prefix, name_hint=name)
    repo = get_repository(repo_root)

    try:
        eid = ensure_unique_entity_random_part(eid, artifact_type, repo, info.prefix, name)
    except ValueError as e:
        error_msg = str(e)
        path = entity_path(repo_root, info, eid, group)
        return WriteResult(
            wrote=False,
            path=path,
            artifact_id=eid,
            content=None,
            warnings=[error_msg],
            verification={
                "valid": False,
                "issues": [
                    {
                        "severity": "error",
                        "code": "random_part_collision",
                        "message": error_msg,
                        "location": None,
                    }
                ],
            },
        )

    friendly_slug = extract_friendly_slug(eid)
    try:
        validate_entity_unique(repo, artifact_type, friendly_slug)
    except ValueError as e:
        error_msg = str(e)
        path = entity_path(repo_root, info, eid, group)
        return WriteResult(
            wrote=False,
            path=path,
            artifact_id=eid,
            content=None,
            warnings=[error_msg],
            verification={
                "valid": False,
                "issues": [
                    {
                        "severity": "error",
                        "code": "duplicate_artifact",
                        "message": error_msg,
                        "location": None,
                    }
                ],
            },
        )

    path = entity_path(repo_root, info, eid, group)
    display_section_id, display_content = _render_display(info, name, eid)

    content = format_entity_markdown(
        artifact_id=eid,
        artifact_type=artifact_type,
        name=name,
        version=version,
        status=status,
        last_updated=last,
        keywords=keywords,
        specializations=applied,
        summary=summary,
        properties=properties,
        attribute_types=attribute_types,
        notes=notes,
        display_section_id=display_section_id,
        display_content=display_content,
        repo_root=repo_root,
    )

    if dry_run:
        res = verify_content_in_temp_path(
            verifier=verifier,
            file_type="entity",
            desired_name=path.name,
            content=content,
            schema_repo_root=repo_root,
        )
        return WriteResult(
            wrote=False,
            path=path,
            artifact_id=eid,
            content=content,
            warnings=[],
            verification=verification_to_entity_dict(path, res),
        )

    prev = path.read_text(encoding="utf-8") if path.exists() else None
    write_atomic(path, content)

    res = verifier.verify_entity_file(path)
    if not res.valid:
        if prev is None:
            try:
                path.unlink()
            except OSError:
                pass
        else:
            write_atomic(path, prev)
        return WriteResult(
            wrote=False,
            path=path,
            artifact_id=eid,
            content=content,
            warnings=[],
            verification=verification_to_entity_dict(path, res),
        )

    clear_repo_caches(path)

    return WriteResult(
        wrote=True,
        path=path,
        artifact_id=eid,
        content=None,
        warnings=[],
        verification=verification_to_entity_dict(path, res),
    )
