"""Align and distribute as cases, for `tests/fixtures/layout_geometry/intents.json`.

The server compiles an editor's *align* and *distribute* into a layout patch (`layout_intents`); the
diagram canvas applies the same two intents at once, in TypeScript
(`tools/gui/src/domain/layout/layoutIntents.ts`), so the picture the user arranges is the one the
server would state. Each case is a set of elements where they are and how big they were drawn, an
intent, and where `layout_intents` puts each element's top-left corner.

The cases are chosen so each rule decides something: every edge, a centre that falls on a half (the
rounding), a selection given out of order, two elements starting level (the tie is broken by key), and
elements of different sizes along each axis.
"""

from __future__ import annotations

from collections.abc import Mapping

from src.domain.diagrams.layout.geometry import Extent
from src.domain.diagrams.layout.layout_block import Layout, Placed
from src.domain.diagrams.layout.layout_intents import EDGES, Align, Distribute, Intent, applied

type Box = tuple[int, int, float, float]

#: Each element by its top-left corner and the size it was drawn at.
_SCENES: dict[str, dict[str, Box]] = {
    "three of different sizes": {"a": (10, 0, 100, 40), "b": (200, 50, 61, 30), "c": (500, 90, 80, 47)},
    "two, one above the other": {"p": (40, 300, 120, 60), "q": (10, 20, 75, 33)},
}

_DISTRIBUTIONS: list[tuple[str, dict[str, Box], str]] = [
    ("four across, given out of order", {"d": (700, 5, 90, 40), "a": (0, 0, 100, 40),
                                         "c": (260, 12, 50, 40), "b": (130, 30, 70, 40)}, "x"),
    ("four down, of different heights", {"top": (0, 0, 80, 30), "mid": (20, 100, 80, 75),
                                         "low": (5, 61, 80, 20), "end": (0, 400, 80, 45)}, "y"),
    ("two starting level: the key decides", {"b": (0, 0, 40, 40), "a": (0, 200, 40, 40),
                                              "c": (300, 90, 40, 40)}, "x"),
]


def _layout(scene: Mapping[str, Box]) -> tuple[Layout, dict[str, Extent]]:
    layout = Layout(elements={key: Placed(x, y) for key, (x, y, _w, _h) in scene.items()})
    drawn = {key: Extent(0, 0, w, h) for key, (_x, _y, w, h) in scene.items()}
    return layout, drawn


def _case(name: str, scene: Mapping[str, Box], intent: Intent, written: dict[str, object]) -> dict[str, object]:
    layout, drawn = _layout(scene)
    result = applied(intent, layout, drawn)
    return {
        "name": name,
        "elements": {
            key: {"left": x, "top": y, "right": x + w, "bottom": y + h} for key, (x, y, w, h) in scene.items()
        },
        "intent": written,
        "to": {key: [result.elements[key].x, result.elements[key].y] for key in scene},
    }


def build_intents() -> dict[str, object]:
    cases = [
        _case(f"{name}: {edge}", scene, Align(tuple(scene), edge),  # type: ignore[arg-type]
              {"intent": "align", "edge": edge})
        for name, scene in _SCENES.items() for edge in EDGES
    ]
    cases += [
        _case(name, scene, Distribute(tuple(scene), axis), {"intent": "distribute", "axis": axis})  # type: ignore[arg-type]
        for name, scene, axis in _DISTRIBUTIONS
    ]
    return {"cases": cases}
