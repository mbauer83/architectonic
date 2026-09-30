"""Who uses a library icon: the diagrams whose statements name it, and the specializations defaulting to it.

The answer a deletion is refused by, and the list a replacement re-points. A diagram counts wherever it
names the icon — for an instance or for a type — whether or not that element is still drawn: the
statement is what would break.

`uses_outside` asks each of those uses whether a changed `applies-to` would still admit it (D12): asking
the use, not comparing name sets, is what sees that an icon for a type covers its specializations.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass

from src.application.icons.effective_icons import (
    DISPLAY_ICONS_KEY,
    TYPE_ICONS_KEY,
    IconAssignments,
    icon_assignments,
)
from src.domain.artifact_id import stable_id
from src.domain.icons.applicability import Applicability
from src.domain.icons.icon_ref import IconRef, IconTarget, SharedIcon, library_icon_named
from src.domain.ontology_representation.artifact_types import DiagramRecord, EntityRecord
from src.domain.ontology_representation.specializations import SpecializationCatalog


@dataclass(frozen=True, slots=True)
class IconUsers:
    diagrams: tuple[str, ...]
    specializations: tuple[str, ...]
    #: The same diagrams as `diagrams`, with the names a reader knows them by.
    named_diagrams: tuple[UsingDiagram, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not (self.diagrams or self.specializations)

    def described(self) -> str:
        parts = [f"diagrams {', '.join(self.diagrams)}"] if self.diagrams else []
        parts += [f"specialization defaults {', '.join(self.specializations)}"] if self.specializations else []
        return "; ".join(parts)


@dataclass(frozen=True, slots=True)
class UsingDiagram:
    artifact_id: str
    name: str


@dataclass(frozen=True, slots=True)
class LibraryUsage:
    """Every use of the library in a repository, read in one pass over its diagrams.

    `users_of` is who a deletion is refused by and a replacement re-points; `shown_for` is what other
    diagrams already show an element with, so a logo chosen for it once is offered first after. An
    element is keyed by its rename-stable id, as a diagram names a model entity; an occurrence names
    its own id and is not an element here.
    """

    _diagrams: Mapping[str, tuple[UsingDiagram, ...]]
    _defaults: Mapping[str, tuple[str, ...]]
    _by_element: Mapping[str, frozenset[str]]

    def users_of(self, icon_id: str) -> IconUsers:
        wanted = stable_id(icon_id)
        using = self._diagrams.get(wanted, ())
        return IconUsers(tuple(d.artifact_id for d in using), self._defaults.get(wanted, ()), using)

    def shown_for(self, element_id: str) -> frozenset[str]:
        """The rename-stable ids of the library icons diagrams state for *element_id* itself."""
        return self._by_element.get(stable_id(element_id), frozenset())


def library_usage(diagrams: Iterable[DiagramRecord], specializations: SpecializationCatalog) -> LibraryUsage:
    using: dict[str, list[UsingDiagram]] = {}
    by_element: dict[str, set[str]] = {}
    for diagram in sorted(diagrams, key=lambda d: d.artifact_id):
        assignments = _assignments(diagram)
        for icon_id in sorted(_shared_ids(assignments.targets)):
            using.setdefault(icon_id, []).append(UsingDiagram(diagram.artifact_id, diagram.name))
        for key, ref in assignments.by_instance.items():
            if isinstance(ref.target, SharedIcon):
                by_element.setdefault(stable_id(key), set()).add(ref.target.icon_id)
    defaults: dict[str, list[str]] = {}
    for spec in sorted(specializations.entries, key=lambda s: s.slug):
        if (named := library_icon_named(spec.notation.icon)) is not None:
            defaults.setdefault(named.icon_id, []).append(spec.slug)
    return LibraryUsage(
        {icon: tuple(ds) for icon, ds in using.items()},
        {icon: tuple(slugs) for icon, slugs in defaults.items()},
        {element: frozenset(icons) for element, icons in by_element.items()},
    )


def icon_users(icon_id: str, diagrams: Iterable[DiagramRecord], specializations: SpecializationCatalog) -> IconUsers:
    return library_usage(diagrams, specializations).users_of(icon_id)


def library_icons_named(diagram: DiagramRecord) -> frozenset[str]:
    """The rename-stable ids of the library icons *diagram* names, at either level."""
    return _shared_ids(_assignments(diagram).targets)


def _assignments(diagram: DiagramRecord) -> IconAssignments:
    raw = diagram.extra.get("diagram-entities")
    return icon_assignments(raw if isinstance(raw, dict) else None)


def _shared_ids(targets: Iterable[IconTarget]) -> frozenset[str]:
    return frozenset(target.icon_id for target in targets if isinstance(target, SharedIcon))


def uses_outside(
    icon_id: str,
    applies_to: Applicability,
    diagrams: Iterable[DiagramRecord],
    specializations: SpecializationCatalog,
    entity_of: Callable[[str], EntityRecord | None],
) -> list[str]:
    """Every use of the icon *applies_to* would not admit, each named so it can be re-pointed or cleared."""
    wanted = stable_id(icon_id)
    lost = [use for diagram in diagrams for use in _diagram_uses_outside(diagram, wanted, applies_to, entity_of)]
    return lost + [
        f"specialization default {spec.slug}" for spec in specializations.entries
        if (named := library_icon_named(spec.notation.icon)) is not None and named.icon_id == wanted
        and not applies_to.admits(frozenset({spec.slug, spec.parent_type}))
    ]


def instance_names(
    instance_id: str, diagram_entities: Mapping[str, object], entity_of: Callable[[str], EntityRecord | None]
) -> frozenset[str] | None:
    """An instance's type and specialization names, where it can be classified without its notation.

    A model entity is classified through the model, and a node the diagram hosts by the
    `diagram-entities` list its type keys. Any other instance (an occurrence) is not classified.
    """
    if (entity := entity_of(instance_id)) is not None:
        return entity.type_and_specializations
    hosted = hosted_type_of(instance_id, diagram_entities)
    return frozenset({hosted}) if hosted is not None else None


def hosted_type_of(instance_id: str, diagram_entities: Mapping[str, object]) -> str | None:
    """The type of a node the diagram hosts itself: the `diagram-entities` list it is in."""
    return next((
        str(type_name) for type_name, nodes in diagram_entities.items()
        if isinstance(nodes, list) and any(isinstance(n, Mapping) and n.get("id") == instance_id for n in nodes)
    ), None)


def _diagram_uses_outside(
    diagram: DiagramRecord, wanted: str, applies_to: Applicability, entity_of: Callable[[str], EntityRecord | None]
) -> Iterator[str]:
    raw = diagram.extra.get("diagram-entities")
    entities: Mapping[str, object] = raw if isinstance(raw, Mapping) else {}
    assignments = icon_assignments(entities)
    for key, ref in assignments.by_instance.items():
        names = instance_names(key, entities, entity_of)
        if _names(ref, wanted) and names is not None and not applies_to.admits(names):
            yield f"{diagram.artifact_id} {DISPLAY_ICONS_KEY} {key}"
    for name, ref in assignments.by_name.items():
        if _names(ref, wanted) and not applies_to.admits(frozenset({name})):
            yield f"{diagram.artifact_id} {TYPE_ICONS_KEY} {name}"


def _names(ref: IconRef, wanted: str) -> bool:
    return isinstance(ref.target, SharedIcon) and ref.target.icon_id == wanted
