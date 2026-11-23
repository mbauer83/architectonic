"""What an editor means — align these, distribute those, straighten a line, return to automatic — compiled
into the layout patch (`layout_patch`) that states it.

```json
[
  {"intent": "align", "keys": ["APP@1712870400.xVrBYD", "APP@1712870400.q7Lm2c"], "edge": "left"},
  {"intent": "distribute", "keys": ["…", "…", "…"], "axis": "x"},
  {"intent": "straighten", "relations": ["<drawn-relation key>"]},
  {"intent": "return_to_automatic", "keys": ["…"]}
]
```

An intent is applied to the layout the diagram is arranged by — the stored one, or its first layout where
it has none — and the result is stated as a patch: each changed entry with what it becomes and, as
``based_on``, what the stored layout holds for it. So an intent goes through exactly the path a hand-made
patch does, and one that was compiled against a layout someone else has since changed is a conflict, not
a silent overwrite. Intents apply in order; each sees what the ones before it did.

Aligning and distributing move elements only. A box is moved with its members by the canvas, and the
layout does not record membership, so moving a box here would leave its members behind.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal, get_args

from src.domain.diagrams.layout.geometry import Extent
from src.domain.diagrams.layout.layout_block import Layout, MalformedLayout, layout_as_written
from src.domain.diagrams.layout.layout_checks import placed_extent
from src.domain.diagrams.layout.layout_patch import SECTIONS
from src.domain.diagrams.layout.orthogonal import half_up

type Edge = Literal["left", "right", "top", "bottom", "centre_x", "centre_y"]
type Axis = Literal["x", "y"]
EDGES: tuple[str, ...] = get_args(Edge.__value__)
AXES: tuple[str, ...] = get_args(Axis.__value__)


@dataclass(frozen=True)
class Align:
    keys: tuple[str, ...]
    edge: Edge


@dataclass(frozen=True)
class Distribute:
    keys: tuple[str, ...]
    axis: Axis


@dataclass(frozen=True)
class Straighten:
    relations: tuple[str, ...]


@dataclass(frozen=True)
class ReturnToAutomatic:
    """The entries of *keys* go back to the automatic arrangement; with no keys, the whole layout does."""

    keys: tuple[str, ...] = ()


type Intent = Align | Distribute | Straighten | ReturnToAutomatic


def _extents(layout: Layout, keys: Sequence[str], drawn: Mapping[str, Extent]) -> dict[str, Extent]:
    found: dict[str, Extent] = {}
    for key in keys:
        placed = layout.elements.get(key)
        if placed is None:
            what = "a box; boxes move with their members on the canvas" if key in layout.boxes else "not drawn"
            raise MalformedLayout(f"{key} is {what}. Align and distribute move drawn elements.")
        size = drawn.get(key)
        extent = placed_extent(placed, (size.width, size.height) if size is not None else None)
        if extent is None:
            raise MalformedLayout(f"{key} has no known size to align by.")
        found[key] = extent
    return found


def _moved(layout: Layout, moves: Mapping[str, tuple[float, float]]) -> Layout:
    elements = dict(layout.elements)
    for key, (left, top) in moves.items():
        elements[key] = replace(elements[key], x=half_up(left), y=half_up(top))
    return replace(layout, elements=elements)


def _aligned(layout: Layout, intent: Align, drawn: Mapping[str, Extent]) -> Layout:
    extents = _extents(layout, intent.keys, drawn)
    boxes = extents.values()
    left, right = min(e.left for e in boxes), max(e.right for e in boxes)
    top, bottom = min(e.top for e in boxes), max(e.bottom for e in boxes)
    to: dict[str, tuple[float, float]] = {}
    for key, e in extents.items():
        to[key] = {
            "left": (left, e.top), "right": (right - e.width, e.top),
            "centre_x": ((left + right - e.width) / 2, e.top),
            "top": (e.left, top), "bottom": (e.left, bottom - e.height),
            "centre_y": (e.left, (top + bottom - e.height) / 2),
        }[intent.edge]
    return _moved(layout, to)


def _distributed(layout: Layout, intent: Distribute, drawn: Mapping[str, Extent]) -> Layout:
    """Equal gaps between neighbours along *axis*; the first and the last stay where they are."""
    extents = _extents(layout, intent.keys, drawn)
    along_x = intent.axis == "x"
    start, size = ((lambda e: e.left), (lambda e: e.width)) if along_x else ((lambda e: e.top), (lambda e: e.height))
    order = sorted(extents, key=lambda key: (start(extents[key]), key))
    first, last = extents[order[0]], extents[order[-1]]
    gap = (start(last) + size(last) - start(first) - sum(size(extents[k]) for k in order)) / (len(order) - 1)
    to: dict[str, tuple[float, float]] = {}
    at = start(first)
    for key in order:
        e = extents[key]
        to[key] = (at, e.top) if along_x else (e.left, at)
        at += size(e) + gap
    return _moved(layout, to)


def _straightened(layout: Layout, intent: Straighten) -> Layout:
    """A stated route loses its bends and keeps its ports and label; an unstated one is the router's already."""
    relations = dict(layout.relations)
    for key in intent.relations:
        if (route := relations.get(key)) is not None:
            relations[key] = replace(route, via=())
    return replace(layout, relations=relations)


def _returned(layout: Layout, intent: ReturnToAutomatic) -> Layout:
    if not intent.keys:
        return Layout(grid=layout.grid)
    gone = set(intent.keys)
    return replace(
        layout,
        elements={k: v for k, v in layout.elements.items() if k not in gone},
        boxes={k: v for k, v in layout.boxes.items() if k not in gone},
        relations={k: v for k, v in layout.relations.items() if k not in gone},
        z={k: v for k, v in layout.z.items() if k not in gone},
    )


def applied(intent: Intent, layout: Layout, drawn: Mapping[str, Extent]) -> Layout:
    match intent:
        case Align():
            return _aligned(layout, intent, drawn)
        case Distribute():
            return _distributed(layout, intent, drawn)
        case Straighten():
            return _straightened(layout, intent)
        case ReturnToAutomatic():
            return _returned(layout, intent)


def patch_between(before: Layout, after: Layout, *, stored: Layout) -> dict[str, dict[str, object]]:
    """The patch taking *before* to *after*: each changed entry with what it becomes and, as ``based_on``,
    what *stored* holds for it."""
    old_written, new_written, held_written = (layout_as_written(layout) for layout in (before, after, stored))

    def section(name: str) -> dict[str, object]:
        old, new, held = (_entries(written, name) for written in (old_written, new_written, held_written))
        return {
            key: {"value": new.get(key), "based_on": held.get(key)}
            for key in sorted(set(old) | set(new)) if old.get(key) != new.get(key)
        }

    return {name: entries for name in SECTIONS if (entries := section(name))}


def _entries(written: Mapping[str, object], section: str) -> Mapping[str, object]:
    entries = written.get(section)
    return entries if isinstance(entries, Mapping) else {}
