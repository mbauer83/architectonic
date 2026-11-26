"""The geometry rules of a layout as cases: what goes in, and what the Python domain answers.

`tests/fixtures/layout_geometry/*.json` is the contract between the two implementations of those
rules — `src/domain/diagrams/layout` and `tools/gui/src/domain/layout`. This module states the cases
and computes their answers with the Python implementation; pytest holds the files to what is built
here, and vitest holds the TypeScript implementation to the files. A change to either side that the
other does not make fails one of the two.

Rewrite the files after a deliberate change to the rules with::

    uv run python -m tests.support.layout_geometry_fixtures

A route is written as the layout block writes one (`from`, `to`, `via`, `label`); an extent as its
four edges; a point as `[x, y]`.
"""

from __future__ import annotations

import json
import random
from collections.abc import Mapping, Sequence
from pathlib import Path

from src.domain.diagrams.layout.attachment import (
    breaches_of,
    elements_crossed,
    ends_conflict,
    keep_attached,
    reattached,
)
from src.domain.diagrams.layout.geometry import Extent, Point
from src.domain.diagrams.layout.layout_block import LabelAnchor, Port, Route, Side
from src.domain.diagrams.layout.orthogonal import course_of, fraction_along, point_along, stated_course
from src.domain.diagrams.layout.routing.router import as_route, rerouted, route_all
from src.domain.diagrams.layout.routing.scene import Connector, RoutingScene
from tests.support.box_fixtures import build_boxes
from tests.support.layout_intent_fixtures import build_intents
from tests.support.line_drawing_fixtures import build_line_drawing
from tests.support.readability_fixtures import build_readability
from tests.support.routing_fixtures import build_routing

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "layout_geometry"

#: How many moves the walk makes. The plan asks for at least this many.
WALK_MOVES = 400
_WALK_SEED = 20261111

JsonRoute = dict[str, object]


def extent_as_json(extent: Extent) -> dict[str, float]:
    return {"left": extent.left, "top": extent.top, "right": extent.right, "bottom": extent.bottom}


def extent_from_json(raw: Mapping[str, float]) -> Extent:
    return Extent(raw["left"], raw["top"], raw["right"], raw["bottom"])


def route_as_json(route: Route) -> JsonRoute:
    written: JsonRoute = {}
    if route.source is not None:
        written["from"] = {"side": route.source.side.value, "at": route.source.at}
    if route.target is not None:
        written["to"] = {"side": route.target.side.value, "at": route.target.at}
    if route.via:
        written["via"] = [[x, y] for x, y in route.via]
    if route.label is not None:
        written["label"] = {"at": route.label.at, "dx": route.label.dx, "dy": route.label.dy}
    return written


def route_from_json(raw: Mapping[str, object]) -> Route:
    def port(key: str) -> Port | None:
        stated = raw.get(key)
        return Port(Side(stated["side"]), float(stated["at"])) if isinstance(stated, Mapping) else None

    label = raw.get("label")
    via = raw.get("via")
    return Route(
        source=port("from"), target=port("to"),
        via=tuple((int(x), int(y)) for x, y in via) if isinstance(via, list) else (),
        label=LabelAnchor(label["at"], label["dx"], label["dy"]) if isinstance(label, Mapping) else None,
    )


def _points(course: Sequence[Point]) -> list[list[float]]:
    return [[point.x, point.y] for point in course]


_A = Extent(0, 0, 100, 60)
_RIGHT_OF_A = Extent(300, 0, 400, 60)
_BELOW_RIGHT = Extent(300, 200, 420, 260)
_BELOW_A = Extent(10, 200, 110, 260)

_COURSES: tuple[tuple[str, Extent | None, Extent | None, Route], ...] = (
    ("facing ports in line run straight", _A, _RIGHT_OF_A, Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5))),
    ("facing ports out of line make a Z through the middle", _A, _BELOW_RIGHT,
     Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5))),
    ("a side and a top make an L", _A, _BELOW_RIGHT, Route(Port(Side.RIGHT, 0.5), Port(Side.TOP, 0.25))),
    ("upright ports out of line make a Z through the middle", _A, _BELOW_RIGHT,
     Route(Port(Side.BOTTOM, 0.5), Port(Side.TOP, 0.5))),
    ("a bottom and a left make an L", _A, _BELOW_RIGHT, Route(Port(Side.BOTTOM, 0.3), Port(Side.LEFT, 0.5))),
    ("bends on the ports' lines are kept as stated", _A, _BELOW_RIGHT,
     Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5), ((160, 30), (160, 230)))),
    ("a bend off the port's line is reached by an elbow", _A, _BELOW_RIGHT,
     Route(Port(Side.RIGHT, 0.5), Port(Side.TOP, 0.5), ((180, 120),))),
    ("a bend in the middle of a straight run turns nothing and is dropped", _A, _RIGHT_OF_A,
     Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5), ((200, 30),))),
    ("a bend half a pixel off its line is on it", _A, _BELOW_RIGHT,
     Route(Port(Side.RIGHT, 0.505), Port(Side.TOP, 0.5), ((360, 30),))),
    ("leaving upright through two bends", _A, _BELOW_A,
     Route(Port(Side.TOP, 0.5), Port(Side.LEFT, 0.5), ((50, -40), (-40, -40), (-40, 230)))),
    ("only the source end stated: the course stops at its last bend", _A, _BELOW_RIGHT,
     Route(Port(Side.RIGHT, 0.5), None, ((160, 45),))),
    ("only the target end stated: the course starts at its first bend", _A, _BELOW_RIGHT,
     Route(None, Port(Side.TOP, 0.5), ((200, 100),))),
    ("neither end stated: the bends alone", None, None, Route(via=((10, 10), (10, 50)))),
    ("an element of unknown extent is the router's end", None, _BELOW_RIGHT,
     Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5), ((200, 230),))),
)

_ALONG: tuple[tuple[float, ...], ...] = ((0.0,), (0.25,), (0.5,), (0.31,), (1.0,))
_NEAREST: tuple[tuple[float, float], ...] = ((130, 10), (160, 140), (250, 240), (-50, -50), (500, 500))

_BREACHES: tuple[tuple[str, Extent | None, Extent | None, Route], ...] = (
    ("sound: straight between facing sides", _A, _RIGHT_OF_A, Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5))),
    ("I1 at the source: the first bend one short of a stub", _A, _BELOW_RIGHT,
     Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5), ((111, 30), (111, 230)))),
    ("I1 at the source: leaving along the border", _A, _BELOW_RIGHT,
     Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5), ((100, 120),))),
    ("I1 at the target: arriving from behind", _A, _RIGHT_OF_A,
     Route(Port(Side.RIGHT, 0.5), Port(Side.RIGHT, 0.5))),
    ("I2: doubling back through the source", _A, _BELOW_RIGHT,
     Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5), ((160, 30), (160, 100), (50, 100), (50, 10)))),
    ("I2: running on through the target", _A, _RIGHT_OF_A,
     Route(Port(Side.RIGHT, 0.5), None, ((450, 30),))),
    ("an unstated end is not judged for how it leaves", _A, _RIGHT_OF_A, Route(via=((200, 30),))),
    ("an element of unknown extent is not judged", None, _RIGHT_OF_A,
     Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5))),
)

_OTHERS = {"a": _A, "b": _BELOW_RIGHT, "c": Extent(150, 90, 250, 150), "whole": Extent(-20, -20, 130, 90)}
_CROSSED: tuple[tuple[str, Route], ...] = (
    ("the Z runs through the third element", Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5))),
    ("bends take it round the third element",
     Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5), ((270, 30), (270, 230)))),
    ("the element an end is drawn inside is not another element",
     Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5), ((270, 30), (270, 230)))),
)

_CONFLICTS: tuple[tuple[str, Extent, Extent], ...] = (
    ("apart", _A, _RIGHT_OF_A),
    ("overlapping", _A, Extent(60, 20, 160, 80)),
    ("touching", _A, Extent(100, 0, 200, 60)),
    ("closer than a stub", _A, Extent(111, 0, 211, 60)),
    ("exactly a stub apart", _A, Extent(112, 0, 212, 60)),
    ("diagonal and close on one axis only", _A, Extent(105, 200, 205, 260)),
)

_KEPT = Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5), ((160, 30), (160, 230)), LabelAnchor(0.4, 6, -8))
_REPAIRS: tuple[tuple[str, Route, Extent, Extent], ...] = (
    ("I3: the source moved down, its bend follows and the shape is kept", _KEPT, Extent(0, 40, 100, 100), _BELOW_RIGHT),
    ("I3: the target moved right, its bend follows", _KEPT, _A, Extent(380, 180, 500, 240)),
    ("I3: the source resized, the port and its bend move with the side", _KEPT, Extent(0, 0, 140, 120), _BELOW_RIGHT),
    ("I4: the source moved past its bend, the end turns to the side its route lies beyond",
     _KEPT, Extent(200, 0, 300, 60), _BELOW_RIGHT),
    ("I4: the target moved left of the route, the end turns", _KEPT, _A, Extent(20, 200, 140, 260)),
    ("I4: no side faces the route and the bend goes",
     Route(Port(Side.RIGHT, 0.5), Port(Side.LEFT, 0.5), ((130, 30), (130, 230))), Extent(60, 0, 160, 60), _BELOW_RIGHT),
    ("I4: both ends turn to face each other",
     Route(Port(Side.BOTTOM, 0.5), Port(Side.TOP, 0.5)), _A, Extent(160, 20, 260, 80)),
    ("I4: nothing settles and the arrow is formed afresh, straight where its ends face each other",
     _KEPT, Extent(250, 200, 350, 260), Extent(140, 330, 260, 390)),
    ("I4: formed afresh as a Z where its ends sit diagonal with room between",
     _KEPT, Extent(-80, 290, 20, 350), Extent(40, 200, 160, 260)),
    ("I4: both ends turn where its ends sit diagonal and close",
     _KEPT, Extent(160, 150, 260, 210), Extent(40, 225, 150, 285)),
    ("a route the router decides is left alone", Route(via=((160, 30),)), Extent(0, 40, 100, 100), _BELOW_RIGHT),
    ("a sound route is left exactly as it was", _KEPT, _A, _BELOW_RIGHT),
)


def build_courses() -> dict[str, object]:
    cases = []
    for name, source, target, route in _COURSES:
        course = stated_course(route, source, target)
        cases.append({
            "name": name,
            "source": extent_as_json(source) if source else None,
            "target": extent_as_json(target) if target else None,
            "route": route_as_json(route), "course": _points(course),
        })
    walked = stated_course(_KEPT, _A, _BELOW_RIGHT)
    return {
        "courses": cases,
        "along": {
            "course": _points(walked),
            "points": [{"at": at, "point": _points([point_along(walked, at)])[0]} for (at,) in _ALONG],
            "fractions": [
                {"point": [x, y], "fraction": fraction_along(walked, Point(x, y))} for x, y in _NEAREST
            ],
        },
    }


def build_breaches() -> dict[str, object]:
    crossed = []
    for name, route in _CROSSED:
        inside = name.startswith("the element an end")
        extents = _OTHERS if inside else {key: extent for key, extent in _OTHERS.items() if key != "whole"}
        course = course_of(route, extents["a"], extents["b"])
        assert course is not None
        crossed.append({
            "name": name, "extents": {key: extent_as_json(extent) for key, extent in extents.items()},
            "ends": ["a", "b"], "route": route_as_json(route),
            "crossed": list(elements_crossed(course, extents, ("a", "b"))),
        })
    return {
        "breaches": [
            {
                "name": name,
                "source": extent_as_json(source) if source else None,
                "target": extent_as_json(target) if target else None,
                "route": route_as_json(route),
                "breaches": [breach.value for breach in breaches_of(route, source, target)],
            }
            for name, source, target, route in _BREACHES
        ],
        "crossed": crossed,
        "conflicts": [
            {"name": name, "source": extent_as_json(source), "target": extent_as_json(target),
             "conflict": ends_conflict(source, target)}
            for name, source, target in _CONFLICTS
        ],
    }


def build_repairs() -> dict[str, object]:
    return {
        "repairs": [
            {
                "name": name, "route": route_as_json(route),
                "source": extent_as_json(source), "target": extent_as_json(target),
                "reattached": route_as_json(reattached(route, source, target)),
            }
            for name, route, source, target in _REPAIRS
        ]
    }


def walk_scene() -> tuple[dict[str, Extent], dict[str, tuple[str, str]]]:
    """Ten elements in rows — one of them a junction's dot — and thirteen relations between them."""
    sizes = ((120, 50), (160, 60), (90, 40), (20, 20), (140, 52), (120, 50), (100, 44), (160, 60), (120, 50), (90, 40))
    extents = {
        f"e{index}": Extent(40 + (index % 4) * 260, 40 + (index // 4) * 190,
                            40 + (index % 4) * 260 + width, 40 + (index // 4) * 190 + height)
        for index, (width, height) in enumerate(sizes)
    }
    pairs = ((0, 1), (1, 2), (0, 4), (4, 5), (5, 6), (1, 5), (2, 3), (3, 7), (4, 8), (8, 9), (5, 9), (0, 5), (6, 7))
    return extents, {f"r{index}": (f"e{a}", f"e{b}") for index, (a, b) in enumerate(pairs)}


def _keeping_ports(key: str, ends: tuple[str, str], route: Route) -> Connector:
    return Connector(key, *ends, source_port=route.source, target_port=route.target)


def build_walk() -> dict[str, object]:
    """Four hundred random moves, each with what keeping arrows attached answers and what the router then decides.

    The canvas keeps arrows attached while an element moves and takes the server's route when it is
    dropped, so each step records both: what `keep_attached` leaves, and the routes the router found
    again for the arrows that came to cross an element — which a replay adopts before the next step.
    """
    extents, ends = walk_scene()
    first = route_all(RoutingScene(elements=extents), [Connector(key, *pair) for key, pair in ends.items()])
    routes = {key: as_route(routed) for key, routed in first.routes.items()}
    start = {
        "extents": {key: extent_as_json(extent) for key, extent in extents.items()},
        "ends": {key: list(pair) for key, pair in ends.items()},
        "routes": {key: route_as_json(route) for key, route in routes.items()},
    }
    chance = random.Random(_WALK_SEED)
    steps = []
    for _ in range(WALK_MOVES):
        moved = chance.choice(sorted(extents))
        before = extents[moved]
        left = before.left + chance.randrange(-300, 301)
        top = before.top + chance.randrange(-200, 201)
        extents[moved] = Extent(left, top, left + before.width, top + before.height)
        kept = keep_attached(routes, ends=ends, extents=extents, changed=[moved])
        changed = {key: route for key, route in kept.routes.items() if route != routes[key]}
        routes = dict(kept.routes)
        found = {
            key: again for key in kept.crossing
            if (again := rerouted(RoutingScene(elements=extents), _keeping_ports(key, ends[key], routes[key])))
            is not None
        }
        routes.update(found)
        steps.append({
            "move": moved, "to": [left, top],
            "routes": {key: route_as_json(route) for key, route in changed.items()},
            "crossing": {key: list(crossed) for key, crossed in kept.crossing.items()},
            "conflicts": list(kept.conflicts),
            "rerouted": {key: route_as_json(route) for key, route in found.items()},
        })
    return {**start, "steps": steps}


BUILDERS = {
    "courses.json": build_courses,
    "breaches.json": build_breaches,
    "repairs.json": build_repairs,
    "walk.json": build_walk,
    "readability.json": build_readability,
    "routing.json": build_routing,
    "line_drawing.json": build_line_drawing,
    "intents.json": build_intents,
    "boxes.json": build_boxes,
}


def as_text(content: object) -> str:
    return json.dumps(content, indent=1, ensure_ascii=False) + "\n"


if __name__ == "__main__":
    FIXTURES.mkdir(parents=True, exist_ok=True)
    for name, build in BUILDERS.items():
        (FIXTURES / name).write_text(as_text(build()), encoding="utf-8")
        print(f"wrote {FIXTURES / name}")
