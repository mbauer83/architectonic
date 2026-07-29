"""Group-mapping helpers for the promotion workflow.

Computes how each engagement model-project slug maps to enterprise groups,
and applies group-mapping resolutions when executing a promotion.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.application.verification.artifact_verifier import ArtifactRegistry


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


class GroupMappingEntry:
    """Mapping entry for one engagement model-project slug."""

    __slots__ = (
        "engagement_slug",
        "engagement_group_id",
        "match_status",
        "enterprise_slug",
        "enterprise_group_id",
    )

    def __init__(
        self,
        *,
        engagement_slug: str,
        engagement_group_id: str,
        match_status: Literal["matched_by_id", "conflict", "new"],
        enterprise_slug: str,
        enterprise_group_id: str | None,
    ) -> None:
        self.engagement_slug = engagement_slug
        self.engagement_group_id = engagement_group_id
        self.match_status = match_status
        self.enterprise_slug = enterprise_slug
        self.enterprise_group_id = enterprise_group_id


# ---------------------------------------------------------------------------
# Plan helpers
# ---------------------------------------------------------------------------


def compute_group_mapping(
    entity_ids: list[str],
    registry: "ArtifactRegistry",
    engagement_root: Path,
    enterprise_root: Path,
) -> tuple[list[GroupMappingEntry], list[dict[str, str]]]:
    """Return (group_mapping, available_enterprise_groups) for a promotion plan.

    group_mapping: one entry per unique engagement model-project slug in entity_ids.
    available_enterprise_groups: all enterprise model-project groups (slug, id, name).
    """
    from src.application.group_registry import load_group_registry  # noqa: PLC0415
    from src.application.modeling.artifact_write import slugify  # noqa: PLC0415
    from src.application.repo_path_helpers import group_fn_entity  # noqa: PLC0415
    from src.domain.ontology_representation.artifact_types import infer_engagement_label
    from src.domain.repository.groups import UNCATEGORIZED

    eng_reg = load_group_registry(engagement_root)
    ent_reg = load_group_registry(enterprise_root)

    ent_by_id = {e.id: e for e in ent_reg.model_projects}
    ent_by_slug = {e.slug: e for e in ent_reg.model_projects}
    engagement_label = slugify(infer_engagement_label(engagement_root, scope="engagement"))

    seen: set[str] = set()
    mapping: list[GroupMappingEntry] = []

    for eid in entity_ids:
        path = registry.find_file_by_id(eid)
        if path is None:
            continue
        slug = group_fn_entity(path, engagement_root)
        if slug in seen:
            continue
        seen.add(slug)

        eng_entry = eng_reg.find("model-project", slug)
        eng_id = eng_entry.id if eng_entry else ""

        if eng_id and eng_id in ent_by_id:
            ent_e = ent_by_id[eng_id]
            mapping.append(GroupMappingEntry(
                engagement_slug=slug,
                engagement_group_id=eng_id,
                match_status="matched_by_id",
                enterprise_slug=ent_e.slug,
                enterprise_group_id=ent_e.id,
            ))
        elif slug in ent_by_slug:
            ent_e = ent_by_slug[slug]
            mapping.append(GroupMappingEntry(
                engagement_slug=slug,
                engagement_group_id=eng_id,
                match_status="conflict",
                enterprise_slug=slug,
                enterprise_group_id=ent_e.id,
            ))
        else:
            # Default a brand-new enterprise group to an engagement-qualified slug rather
            # than the bare engagement-local slug: two engagements independently naming a
            # group "assurance" must not silently collide/merge in the shared enterprise
            # namespace. UNCATEGORIZED is the absence of grouping, not a theme — leave it
            # unqualified. The promoting user can still override via
            # update_enterprise_groups()'s group_mapping_resolutions to merge into an
            # existing enterprise group when that's genuinely intended.
            default_slug = slug if slug == UNCATEGORIZED else f"{engagement_label}-{slug}"
            mapping.append(GroupMappingEntry(
                engagement_slug=slug,
                engagement_group_id=eng_id,
                match_status="new",
                enterprise_slug=default_slug,
                enterprise_group_id=None,
            ))

    available = [
        {"slug": e.slug, "id": e.id, "name": e.name}
        for e in ent_reg.list_axis("model-project")
    ]
    return mapping, available


# ---------------------------------------------------------------------------
# Execute helpers
# ---------------------------------------------------------------------------


def remap_entity_rel(rel: Path, group_remap: dict[str, str]) -> Path:
    """Rewrite projects/<old_slug>/... to projects/<new_slug>/... if needed."""
    parts = rel.parts
    if len(parts) >= 2 and parts[0] == "projects" and parts[1] in group_remap:
        new_slug = group_remap[parts[1]]
        return Path("projects") / new_slug / Path(*parts[2:])
    return rel


def update_enterprise_groups(
    enterprise_root: Path,
    engagement_root: Path,
    group_mapping: list[GroupMappingEntry],
    group_mapping_resolutions: dict[str, str],
) -> None:
    """Ensure resolved enterprise model-project groups exist in enterprise groups.yaml.

    Only adds missing entries — never modifies or removes existing ones.
    """
    from src.application.group_registry import _new_group_id, load_group_registry, registry_to_yaml  # noqa: PLC0415
    from src.config.repo_paths import ARCH_REPO  # noqa: PLC0415
    from src.domain.repository.groups import GroupEntry  # noqa: PLC0415

    ent_reg = load_group_registry(enterprise_root)
    eng_reg = load_group_registry(engagement_root)

    ent_slugs = {e.slug for e in ent_reg.model_projects}
    new_entries = list(ent_reg.model_projects)
    changed = False

    for entry in group_mapping:
        enterprise_slug = group_mapping_resolutions.get(entry.engagement_slug, entry.enterprise_slug)
        if enterprise_slug in ent_slugs:
            continue
        eng_entry = eng_reg.find("model-project", entry.engagement_slug)
        # Use engagement id for "new" entries so cross-repo identity is preserved
        use_id = (
            entry.engagement_group_id
            if entry.match_status == "new" and entry.engagement_group_id
            else _new_group_id()
        )
        new_entries.append(GroupEntry(
            slug=enterprise_slug,
            id=use_id,
            name=eng_entry.name if eng_entry else enterprise_slug,
            description=eng_entry.description if eng_entry else "",
            order=eng_entry.order if eng_entry else 0,
        ))
        ent_slugs.add(enterprise_slug)
        changed = True

    if changed:
        updated = replace(ent_reg, model_projects=tuple(new_entries))
        arch_dir = enterprise_root / ARCH_REPO
        arch_dir.mkdir(parents=True, exist_ok=True)
        (arch_dir / "groups.yaml").write_text(registry_to_yaml(updated), encoding="utf-8")
