"""The intents an arrange request states, read; and what they compile to — the groupings a diagram holds
after them and the layout that matches.

Layout intents (`layout_intents`) change the layout; grouping intents (`grouping_intents`) change the
groupings, which are diagram content, and drop from the layout the box entries that no longer fit — a
removed grouping's, and those of the boxes whose members changed, which are fitted round their members
again when the picture is composed. Intents apply in order, each seeing what the ones before it did.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import TypeIs

from src.domain.diagrams.grouping_intents import (
    CreateGrouping,
    DeleteGrouping,
    GroupingIntent,
    Nest,
    Unnest,
    regrouped,
)
from src.domain.diagrams.layout.geometry import Extent
from src.domain.diagrams.layout.layout_block import Layout, MalformedLayout
from src.domain.diagrams.layout.layout_intents import (
    AXES,
    EDGES,
    Align,
    Distribute,
    Intent,
    ReturnToAutomatic,
    Straighten,
    applied,
)

type ArrangeIntent = Intent | GroupingIntent

_FIELDS: Mapping[str, frozenset[str]] = {
    "align": frozenset({"intent", "keys", "edge"}),
    "distribute": frozenset({"intent", "keys", "axis"}),
    "straighten": frozenset({"intent", "relations"}),
    "return_to_automatic": frozenset({"intent", "keys"}),
    "nest": frozenset({"intent", "keys", "grouping"}),
    "unnest": frozenset({"intent", "keys"}),
    "create_grouping": frozenset({"intent", "label", "keys", "parent"}),
    "delete_grouping": frozenset({"intent", "grouping"}),
}


def _names(item: Mapping[str, object], field: str, where: str, *, least: int = 1) -> tuple[str, ...]:
    raw = item.get(field, [])
    if not isinstance(raw, list) or not all(isinstance(key, str) and key for key in raw):
        raise MalformedLayout(f"{where}.{field} is {raw!r}; expected a list of keys.")
    if len(raw) < least:
        raise MalformedLayout(f"{where}.{field} names {len(raw)}; this intent needs at least {least}.")
    return tuple(dict.fromkeys(raw))


def _choice(item: Mapping[str, object], field: str, allowed: tuple[str, ...], where: str) -> str:
    value = item.get(field)
    if value not in allowed:
        raise MalformedLayout(f"{where}.{field} is {value!r}; expected one of {', '.join(allowed)}.")
    return str(value)


def _text(item: Mapping[str, object], field: str, where: str, *, optional: bool = False) -> str | None:
    value = item.get(field)
    if value is None and optional:
        return None
    if not isinstance(value, str) or not value.strip():
        raise MalformedLayout(f"{where}.{field} is {value!r}; expected a non-empty string.")
    return value.strip()


def _read(kind: str, item: Mapping[str, object], where: str) -> ArrangeIntent:
    match kind:
        case "align":
            edge = _choice(item, "edge", EDGES, where)
            return Align(_names(item, "keys", where, least=2), edge)  # type: ignore[arg-type]
        case "distribute":
            axis = _choice(item, "axis", AXES, where)
            return Distribute(_names(item, "keys", where, least=3), axis)  # type: ignore[arg-type]
        case "straighten":
            return Straighten(_names(item, "relations", where))
        case "return_to_automatic":
            return ReturnToAutomatic(_names(item, "keys", where, least=0))
        case "nest":
            return Nest(_names(item, "keys", where), str(_text(item, "grouping", where)))
        case "unnest":
            return Unnest(_names(item, "keys", where))
        case "create_grouping":
            label, parent = _text(item, "label", where), _text(item, "parent", where, optional=True)
            return CreateGrouping(str(label), _names(item, "keys", where), parent)
        case _:
            return DeleteGrouping(str(_text(item, "grouping", where)))


def read_intents(raw: object) -> tuple[ArrangeIntent, ...]:
    """The intents *raw* states. Refuses, saying what and where, a list that is not one."""
    if not isinstance(raw, list) or not raw:
        raise MalformedLayout(f"Intents are a non-empty list; got {raw!r}.")
    intents: list[ArrangeIntent] = []
    for index, item in enumerate(raw):
        where = f"intents[{index}]"
        if not isinstance(item, Mapping):
            raise MalformedLayout(f"{where} is {item!r}; expected an object with 'intent'.")
        kind = item.get("intent")
        if kind not in _FIELDS:
            raise MalformedLayout(f"{where}.intent is {kind!r}; expected one of {', '.join(_FIELDS)}.")
        if unknown := sorted(set(map(str, item)) - _FIELDS[str(kind)]):
            raise MalformedLayout(f"{where} states {', '.join(unknown)}, which {kind} does not take.")
        intents.append(_read(str(kind), item, where))
    return tuple(intents)


def _regroups(intent: ArrangeIntent) -> TypeIs[GroupingIntent]:
    return isinstance(intent, Nest | Unnest | CreateGrouping | DeleteGrouping)


def arranges(intents: Sequence[ArrangeIntent]) -> bool:
    """Whether any of *intents* states geometry — which a diagram PlantUML arranges is taken over for."""
    return not all(map(_regroups, intents))


@dataclass(frozen=True)
class Arranged:
    """What *intents* compile to: the groupings after them (None where none was stated) and the layout."""

    groupings: list[dict[str, object]] | None
    layout: Layout


def arranged(
    intents: Sequence[ArrangeIntent], *, groupings: Sequence[object], diagram_id: str, layout: Layout,
    drawn: Mapping[str, Extent],
) -> Arranged:
    """*intents* applied in order to the diagram's *groupings* and to *layout*.

    *drawn* is each element's extent as drawn, for the sizes a layout entry does not state; *diagram_id*
    seeds the id of a created grouping. Raises `MalformedLayout` or `MalformedGroupings`, saying why.
    """
    stated: list[dict[str, object]] | None = None
    for intent in intents:
        if _regroups(intent):
            result = regrouped(intent, stated if stated is not None else groupings, diagram_id=diagram_id)
            stated = result.groupings
            gone = result.refit | result.removed
            layout = replace(
                layout,
                boxes={key: box for key, box in layout.boxes.items() if key not in gone},
                z={key: z for key, z in layout.z.items() if key not in result.removed},
            )
        else:
            layout = applied(intent, layout, drawn)
    return Arranged(stated, layout)
