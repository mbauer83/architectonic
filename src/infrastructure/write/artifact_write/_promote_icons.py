"""Which library icons a promotion carries: those its diagrams show that only the engagement holds.

An icon joins a promotion on its own (D6): it has no connections and its bytes never change, so there
is nothing to decide — a promoted diagram that names an icon the enterprise lacks would not verify
there, and the only sensible resolution is to take the icon along. One the enterprise already holds
under the same id resolves there, so it stays behind.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from src.application.icons.effective_icons import icon_assignments
from src.domain.icons.icon_ref import SharedIcon

if TYPE_CHECKING:
    from src.application.artifacts.repository import ArtifactRepository
    from src.application.verification.artifact_verifier import ArtifactRegistry


def icons_a_promotion_carries(
    diagram_ids: Iterable[str], repo: ArtifactRepository, registry: ArtifactRegistry
) -> list[str]:
    carried: set[str] = set()
    for diagram_id in diagram_ids:
        diagram = repo.get_diagram(diagram_id)
        raw = diagram.extra.get("diagram-entities") if diagram is not None else None
        assignments = icon_assignments(raw if isinstance(raw, dict) else None)
        for ref in [*assignments.by_instance.values(), *assignments.by_name.values()]:
            if not isinstance(ref.target, SharedIcon):
                continue
            icon = repo.get_icon(ref.target.icon_id)
            if icon is not None and registry.scope_for_path(icon.path) == "engagement":
                carried.add(icon.artifact_id)
    return sorted(carried)
