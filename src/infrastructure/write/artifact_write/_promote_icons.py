"""Which library icons a promotion carries: those its diagrams show that only the engagement holds.

An icon joins a promotion on its own (D6): it has no connections and its bytes never change, so there
is nothing to decide — a promoted diagram that names an icon the enterprise lacks would not verify
there, and the only sensible resolution is to take the icon along. One the enterprise already holds
under the same id resolves there, so it stays behind.

One the enterprise holds under another id, by the same picture, stays behind too: the promoted diagram
is rewritten to name the enterprise's icon, so the enterprise library does not come to offer one
picture twice. The body needs nothing, as its embedded pictures are keyed by digest.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from src.application.icons.effective_icons import with_icon_repointed
from src.application.icons.icon_usage import library_icons_named
from src.domain.icons.icon_ref import icon_target_from

from ._promote_file_ops import rewrite_promoted_frontmatter

if TYPE_CHECKING:
    from src.application.artifacts.repository import ArtifactRepository
    from src.application.verification.artifact_verifier import ArtifactRegistry


@dataclass(frozen=True, slots=True)
class PromotedIcons:
    #: Engagement icons the enterprise lacks, copied along.
    to_add: list[str]
    #: Engagement icon → the enterprise icon with the same picture, which promoted diagrams name instead.
    held_by_picture: dict[str, str]


def icons_a_promotion_carries(
    diagram_ids: Iterable[str], repo: ArtifactRepository, registry: ArtifactRegistry
) -> PromotedIcons:
    enterprise_by_picture = {
        icon.metadata.render_digest: icon.artifact_id
        for icon in repo.list_icons() if registry.scope_for_path(icon.path) == "enterprise"
    }
    carried: set[str] = set()
    held: dict[str, str] = {}
    diagrams = [d for d in map(repo.get_diagram, diagram_ids) if d is not None]
    for icon_id in sorted({icon_id for diagram in diagrams for icon_id in library_icons_named(diagram)}):
        icon = repo.get_icon(icon_id)
        if icon is None or registry.scope_for_path(icon.path) != "engagement":
            continue
        if (same := enterprise_by_picture.get(icon.metadata.render_digest)) is not None:
            held[icon.artifact_id] = same
        else:
            carried.add(icon.artifact_id)
    return PromotedIcons(sorted(carried), dict(sorted(held.items())))


def name_the_enterprise_icons(promoted_diagram: Path, held_by_picture: Mapping[str, str]) -> None:
    """Rewrite a promoted diagram, in place, to name the enterprise icon for each picture it already holds."""
    def repointed(frontmatter: dict[str, object]) -> dict[str, object] | None:
        raw = frontmatter.get("diagram-entities")
        if not isinstance(raw, Mapping):
            return None
        entities: Mapping[str, object] = raw
        for engagement_id, enterprise_id in held_by_picture.items():
            entities = with_icon_repointed(entities, icon_target_from(engagement_id), icon_target_from(enterprise_id))
        return None if entities == raw else {**frontmatter, "diagram-entities": dict(entities)}

    if held_by_picture:
        rewrite_promoted_frontmatter(promoted_diagram, repointed)
