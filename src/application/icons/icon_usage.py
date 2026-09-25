"""Who uses a library icon: the diagrams whose statements name it, and the specializations defaulting to it.

The answer a deletion is refused by, and the list a replacement re-points. A diagram counts wherever it
names the icon — for an instance or for a type — whether or not that element is still drawn: the
statement is what would break.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.application.icons.effective_icons import icon_assignments
from src.domain.artifact_id import stable_id
from src.domain.icons.icon_ref import SharedIcon, library_icon_named
from src.domain.ontology_representation.artifact_types import DiagramRecord
from src.domain.ontology_representation.specializations import SpecializationCatalog


@dataclass(frozen=True, slots=True)
class IconUsers:
    diagrams: tuple[str, ...]
    specializations: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        return not (self.diagrams or self.specializations)

    def described(self) -> str:
        parts = [f"diagrams {', '.join(self.diagrams)}"] if self.diagrams else []
        parts += [f"specialization defaults {', '.join(self.specializations)}"] if self.specializations else []
        return "; ".join(parts)


def icon_users(icon_id: str, diagrams: Iterable[DiagramRecord], specializations: SpecializationCatalog) -> IconUsers:
    wanted = stable_id(icon_id)
    using_diagrams = sorted(d.artifact_id for d in diagrams if wanted in _library_icons_named(d))
    defaulting = sorted(
        spec.slug for spec in specializations.entries
        if (named := library_icon_named(spec.notation.icon)) is not None and named.icon_id == wanted
    )
    return IconUsers(tuple(using_diagrams), tuple(defaulting))


def _library_icons_named(diagram: DiagramRecord) -> frozenset[str]:
    raw = diagram.extra.get("diagram-entities")
    assignments = icon_assignments(raw if isinstance(raw, dict) else None)
    refs = [*assignments.by_instance.values(), *assignments.by_name.values()]
    return frozenset(ref.target.icon_id for ref in refs if isinstance(ref.target, SharedIcon))
