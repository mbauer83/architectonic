"""global_artifact_reference.py — Create and look up GAR proxy stubs.

A Global Artifact Reference (GAR) is an automatically-managed stub in the
engagement repo that acts as a transparent proxy for any promoted (enterprise)
artifact: entity, document, or diagram.
GAR proxies may NOT be created or edited through the standard API;
this module is the only authorised creator.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.application.artifact_query import ArtifactRepository
from src.application.identifier_allocator import get_default_allocator
from src.application.modeling.artifact_write_formatting import format_entity_markdown
from src.application.verification.artifact_verifier import ArtifactVerifier
from src.domain.modules.module_types import EntityTypeName

from .boundary import assert_engagement_write_root, modification_stamp
from .types import WriteResult

_GAR_TYPE = "global-artifact-reference"
_GAR_ID_KEY = "global-artifact-id"
_GAR_TYPE_KEY = "global-artifact-type"
_GAR_ENTITY_TYPE_KEY = "global-artifact-entity-type"  # original artifact_type for entity GARs


def find_existing_gar(repo: ArtifactRepository, global_artifact_id: str) -> str | None:
    """Return the artifact_id of an existing GAR for *global_artifact_id*, or None."""
    for rec in repo.list_entities(artifact_type=_GAR_TYPE):
        if rec.extra.get(_GAR_ID_KEY) == global_artifact_id:
            return rec.artifact_id
    return None


def ensure_global_artifact_reference(
    *,
    engagement_repo: ArtifactRepository,
    engagement_root: Path,
    verifier: ArtifactVerifier,
    clear_repo_caches: Callable[[Path], None],
    global_artifact_id: str,
    global_artifact_name: str,
    global_artifact_type: str,  # "entity" | "document" | "diagram"
    global_artifact_entity_type: str | None = None,  # e.g. "capability" for entity GARs
    dry_run: bool = False,
) -> WriteResult:
    """Return (or create) a GAR for *global_artifact_id* in the engagement repo."""
    assert_engagement_write_root(engagement_root)

    existing = find_existing_gar(engagement_repo, global_artifact_id)
    if existing is not None:
        from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415
        from src.infrastructure.write.artifact_write.entity import entity_path  # noqa: PLC0415

        gar_info = get_module_registry().get_entity_type(EntityTypeName(_GAR_TYPE))
        path = entity_path(engagement_root, gar_info, existing)
        return WriteResult(
            wrote=False,
            path=path,
            artifact_id=existing,
            content=None,
            warnings=["GAR already exists"],
            verification=None,
        )

    from src.infrastructure.app_bootstrap import get_module_registry  # noqa: PLC0415

    info = get_module_registry().get_entity_type(EntityTypeName(_GAR_TYPE))
    eid = get_default_allocator().allocate(prefix=info.prefix, name_hint=global_artifact_name)
    from src.infrastructure.write.artifact_write.entity import (  # noqa: PLC0415
        _alias_for,
        entity_path,
    )

    path = entity_path(engagement_root, info, eid)
    alias = _alias_for(info, eid)

    content = format_entity_markdown(
        artifact_id=eid,
        artifact_type=_GAR_TYPE,
        name=global_artifact_name,
        version="0.1.0",
        status="active",
        last_updated=modification_stamp(),
        summary=f"Engagement-repo proxy for promoted {global_artifact_type} `{global_artifact_id}`.",
        properties=None,
        notes=None,
        display_section_id="archimate",
        display_content=f"label: {global_artifact_name}\nalias: {alias}",
        repo_root=engagement_root,
        extra_frontmatter={
            _GAR_ID_KEY: global_artifact_id,
            _GAR_TYPE_KEY: global_artifact_type,
            **({_GAR_ENTITY_TYPE_KEY: global_artifact_entity_type} if global_artifact_entity_type else {}),
        },
    )

    if dry_run:
        return WriteResult(
            wrote=False,
            path=path,
            artifact_id=eid,
            content=content,
            warnings=[],
            verification=None,
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    res = verifier.verify_entity_file(path)
    if not res.valid:
        try:
            path.unlink()
        except OSError:
            pass
        return WriteResult(
            wrote=False,
            path=path,
            artifact_id=eid,
            content=content,
            warnings=[],
            verification={
                "valid": False,
                "issues": [{"severity": i.severity, "code": i.code, "message": i.message} for i in res.issues],
            },
        )

    clear_repo_caches(path)

    return WriteResult(
        wrote=True,
        path=path,
        artifact_id=eid,
        content=None,
        warnings=[],
        verification={"valid": True, "issues": []},
    )


def build_gar_map(engagement_repo: ArtifactRepository) -> dict[str, str]:
    """Return {gar_artifact_id: global_artifact_id} for all GARs in the engagement repo."""
    result: dict[str, str] = {}
    for rec in engagement_repo.list_entities(artifact_type=_GAR_TYPE):
        gaid = rec.extra.get(_GAR_ID_KEY)
        if isinstance(gaid, str) and gaid:
            result[rec.artifact_id] = gaid
    return result
