"""Which icon an element shows on a diagram, and at which level that was decided.

A diagram states icons at two levels in its `diagram-entities`: `display_icons`, per instance (the
entity's id for its base drawing, an occurrence's id for a further one), and `type_icons`, per type or
specialization name — the names `applies-to` and viewpoint rules use. A repository may set a default
per specialization. The most specific statement wins: the instance's own, then a specialization key
(in the order the specializations are applied), then the type key, then the specialization default;
with none, the element keeps its type glyph.

At every level an icon that does not resolve, or does not apply to the element, is passed over and
the next level decides. The write path refuses such an assignment when it is made; this is what keeps
a diagram drawable when one stops applying later, because an element's type or the icon's
restriction changed.

Pure: the caller supplies how a reference resolves to a picture.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from src.domain.icons.icon_ref import (
    IconRef,
    IconStyle,
    IconTarget,
    InvalidIconRefError,
    icon_ref_from,
    library_icon_named,
)
from src.domain.icons.resolved_icon import IconSource, ResolvedIcon
from src.domain.ontology_representation.specializations import SpecializationCatalog

DISPLAY_ICONS_KEY = "display_icons"
TYPE_ICONS_KEY = "type_icons"
#: The icons a diagram holds for itself, `local:<key>` naming one (D11).
LOCAL_ICONS_KEY = "icons"

AssignmentLevel = Literal["instance", "type", "specialization-default"]

_INSTANCE: AssignmentLevel = "instance"
_TYPE: AssignmentLevel = "type"
_SPECIALIZATION_DEFAULT: AssignmentLevel = "specialization-default"


@dataclass(frozen=True, slots=True)
class EffectiveIcon:
    icon: ResolvedIcon
    style: IconStyle
    level: AssignmentLevel
    #: The icon the deciding statement names.
    target: IconTarget


@dataclass(frozen=True, slots=True)
class IconAssignments:
    """What one diagram states, read leniently: an entry that is not a valid reference is left out."""

    by_instance: Mapping[str, IconRef]
    by_name: Mapping[str, IconRef]

    @property
    def targets(self) -> tuple[IconTarget, ...]:
        """Every icon the diagram names, at either level, as often as it names it."""
        return tuple(ref.target for ref in (*self.by_instance.values(), *self.by_name.values()))


def icon_assignments(diagram_entities: Mapping[str, object] | None) -> IconAssignments:
    source = diagram_entities or {}
    return IconAssignments(_refs(source.get(DISPLAY_ICONS_KEY)), _refs(source.get(TYPE_ICONS_KEY)))


def names_most_specific_first(element_type: str, specializations: Sequence[str]) -> tuple[str, ...]:
    """An element's names in the order `effective_icon` consults them: its specializations, then its type."""
    return (*[name for name in specializations if name], element_type)


def effective_icon(
    instance_id: str,
    names: Sequence[str],
    assignments: IconAssignments,
    resolve: IconSource,
    specialization_default: Callable[[str], IconRef | None] = lambda _name: None,
) -> EffectiveIcon | None:
    """The icon an element shows, given its instance id and its names, most specific first.

    *names* is the element's applied specializations in order, then its type.
    """
    element = frozenset(names)
    candidates: list[tuple[IconRef | None, AssignmentLevel]] = [
        (assignments.by_instance.get(instance_id), _INSTANCE),
        *((assignments.by_name.get(name), _TYPE) for name in names),
        *((specialization_default(name), _SPECIALIZATION_DEFAULT) for name in names[:-1]),
    ]
    for ref, level in candidates:
        if ref is None or (icon := resolve(ref.target)) is None or not icon.applies_to.admits(element):
            continue
        return EffectiveIcon(icon, ref.style or icon.default_style, level, ref.target)
    return None


def specialization_defaults(
    entity_type: str, specializations: SpecializationCatalog
) -> Callable[[str], IconRef | None]:
    """The default a repository sets for each specialization of *entity_type*, when it names a library icon."""
    def default(name: str) -> IconRef | None:
        info = specializations.get("entity", entity_type, name)
        target = library_icon_named(info.notation.icon) if info is not None else None
        return IconRef(target) if target is not None else None

    return default


def malformed_icon_entries(diagram_entities: Mapping[str, object] | None) -> list[tuple[str, str, str]]:
    """(statement, key, reason) for every entry `icon_assignments` would leave out, so it can be reported."""
    source = diagram_entities or {}
    problems: list[tuple[str, str, str]] = []
    for statement in (DISPLAY_ICONS_KEY, TYPE_ICONS_KEY):
        raw = source.get(statement)
        if raw is None:
            continue
        if not isinstance(raw, Mapping):
            problems.append((statement, "", "is not a mapping"))
            continue
        for key, value in raw.items():
            try:
                icon_ref_from(value)
            except InvalidIconRefError as exc:
                problems.append((statement, str(key), str(exc)))
    return problems


def with_icon_repointed(
    diagram_entities: Mapping[str, object], old: IconTarget, new: IconTarget
) -> dict[str, object]:
    """*diagram_entities* with every assignment of *old* naming *new* instead, each keeping its style.

    An entry that is not a valid reference is kept as written, for the verifier to report.
    """
    repointed = dict(diagram_entities)
    for statement in (DISPLAY_ICONS_KEY, TYPE_ICONS_KEY):
        raw = diagram_entities.get(statement)
        if isinstance(raw, Mapping):
            repointed[statement] = {
                key: IconRef(new, ref.style).as_stored() if ref is not None and ref.target == old else value
                for key, value in raw.items()
                for ref in [_ref_or_none(value)]
            }
    return repointed


def _ref_or_none(value: object) -> IconRef | None:
    try:
        return icon_ref_from(value)
    except InvalidIconRefError:
        return None


def _refs(raw: object) -> dict[str, IconRef]:
    if not isinstance(raw, Mapping):
        return {}
    return {str(key): ref for key, value in raw.items() if (ref := _ref_or_none(value)) is not None}
