"""A diagram's stated layout: the ``layout`` block of its frontmatter as a value, read and written here only.

Geometry and nothing else. What the diagram holds and means stays in the keys it already has; this
block says where each instance sits and how large it is, how boxes are sized, which side and point
each drawn relation attaches at and where it bends, where its label sits, and how things stack.

```yaml
layout:
  grid: 10
  elements:              # by instance id: an entity id, or an occurrence id
    APP@1712870400.xVrBYD: {x: 320, y: 200}            # w and h only when resized
  boxes:                 # a grouping by its id; a box no entry states by its rule
    g-7Fq2aB: {x: 600, y: 40, w: 420, h: 260}
    rule:domain=business: {x: 40, y: 300, w: 900, h: 220}
  relations:             # by drawn-relation key
    APP@1.a---APP@2.b@@archimate-serving:
      from: {side: right, at: 0.5}
      to: {side: left, at: 0.45}
      via: [[480, 210], [480, 330]]
      label: {at: 0.31, dx: 6, dy: 59}
  z: {g-7Fq2aB: 1, APP@1712870400.xVrBYD: -1}
```

Positions and sizes are integers; a port is a side and a fraction along it, so a resize keeps an
attachment meaningful. A block that is not this does not become a value: `read_layout` refuses it
with a sentence saying what and where. Keys are held in canonical spelling — an entity by its stable
id, a relation as `relation_key` spells it — so a renamed element does not orphan its geometry.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum

from src.domain.artifact_id import canonical_entity_key
from src.domain.diagrams.authored_groupings import MalformedGroupings, is_rule_key, read_rule_key
from src.domain.diagrams.relation_key import MalformedRelationKey, read_relation_key

LAYOUT_KEY = "layout"


class MalformedLayout(ValueError):
    """A ``layout`` block that cannot be read, with what is wrong and where in a sentence."""


class Side(StrEnum):
    TOP = "top"
    RIGHT = "right"
    BOTTOM = "bottom"
    LEFT = "left"


@dataclass(frozen=True)
class Placed:
    """Where a shape's top-left corner sits, and its size where one is stated."""

    x: int
    y: int
    w: int | None = None
    h: int | None = None


@dataclass(frozen=True)
class Port:
    """Where a relation attaches: a side of its element, and how far along it from the top or left."""

    side: Side
    at: float


@dataclass(frozen=True)
class LabelAnchor:
    """Where a relation's label sits: a fraction along its route, and an offset from that point."""

    at: float
    dx: int = 0
    dy: int = 0


@dataclass(frozen=True)
class Route:
    """How one drawn relation runs. Anything left unstated is the router's to decide."""

    source: Port | None = None
    target: Port | None = None
    via: tuple[tuple[int, int], ...] = ()
    label: LabelAnchor | None = None


@dataclass(frozen=True)
class Layout:
    """Everything a diagram states about its geometry, each part by the identity the diagram uses."""

    grid: int | None = None
    elements: Mapping[str, Placed] = field(default_factory=dict)
    boxes: Mapping[str, Placed] = field(default_factory=dict)
    relations: Mapping[str, Route] = field(default_factory=dict)
    z: Mapping[str, int] = field(default_factory=dict)

    def states_nothing(self) -> bool:
        return not (self.elements or self.boxes or self.relations or self.z)

    def without(
        self, *, elements: frozenset[str] = frozenset(), boxes: frozenset[str] = frozenset(),
        relations: frozenset[str] = frozenset(),
    ) -> Layout:
        """This layout with the named entries gone, from the sections they sit in and from the stacking."""
        return replace(
            self,
            elements={key: value for key, value in self.elements.items() if key not in elements},
            boxes={key: value for key, value in self.boxes.items() if key not in boxes},
            relations={key: value for key, value in self.relations.items() if key not in relations},
            z={key: value for key, value in self.z.items() if key not in elements | boxes},
        )


def _whole(value: object, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MalformedLayout(f"{where} is {value!r}; a position or size is a whole number.")
    return value


def _fraction(value: object, where: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not 0 <= value <= 1:
        raise MalformedLayout(f"{where} is {value!r}; it is a fraction from 0 to 1.")
    return float(value)


def _mapping(value: object, where: str, allowed: frozenset[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise MalformedLayout(f"{where} is {value!r}; expected a mapping.")
    unknown = sorted(str(key) for key in value if key not in allowed)
    if unknown:
        raise MalformedLayout(
            f"{where} states {', '.join(unknown)}; it holds only {', '.join(sorted(allowed))}."
        )
    return value


def _section(value: object, where: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) and key.strip() for key in value):
        raise MalformedLayout(f"{where} is a mapping from an identity to what is stated about it.")
    return value


def _placed(value: object, where: str) -> Placed:
    stated = _mapping(value, where, frozenset({"x", "y", "w", "h"}))
    if "x" not in stated or "y" not in stated:
        raise MalformedLayout(f"{where} states no position; it needs both x and y.")
    if ("w" in stated) != ("h" in stated):
        raise MalformedLayout(f"{where} states one of w and h; a size is both or neither.")
    size = [_whole(stated[key], f"{where}.{key}") for key in ("w", "h") if key in stated]
    if any(extent <= 0 for extent in size):
        raise MalformedLayout(f"{where} states a size that is not positive.")
    return Placed(_whole(stated["x"], f"{where}.x"), _whole(stated["y"], f"{where}.y"), *size)


def _port(value: object, where: str) -> Port:
    stated = _mapping(value, where, frozenset({"side", "at"}))
    side = stated.get("side")
    if side not in tuple(Side):
        raise MalformedLayout(f"{where}.side is {side!r}; a side is one of top, right, bottom, left.")
    return Port(Side(str(side)), _fraction(stated.get("at", 0.5), f"{where}.at"))


def _bend(value: object, where: str) -> tuple[int, int]:
    if not isinstance(value, list | tuple) or len(value) != 2:
        raise MalformedLayout(f"{where} is {value!r}; a bend is a point [x, y].")
    return _whole(value[0], f"{where}[0]"), _whole(value[1], f"{where}[1]")


def _route(value: object, where: str) -> Route:
    stated = _mapping(value, where, frozenset({"from", "to", "via", "label"}))
    via = stated.get("via", [])
    if not isinstance(via, list | tuple):
        raise MalformedLayout(f"{where}.via is {via!r}; it is a list of points [x, y].")
    label = None
    if "label" in stated:
        anchor = _mapping(stated["label"], f"{where}.label", frozenset({"at", "dx", "dy"}))
        label = LabelAnchor(
            _fraction(anchor.get("at", 0.5), f"{where}.label.at"),
            _whole(anchor.get("dx", 0), f"{where}.label.dx"),
            _whole(anchor.get("dy", 0), f"{where}.label.dy"),
        )
    return Route(
        source=_port(stated["from"], f"{where}.from") if "from" in stated else None,
        target=_port(stated["to"], f"{where}.to") if "to" in stated else None,
        via=tuple(_bend(point, f"{where}.via[{index}]") for index, point in enumerate(via)),
        label=label,
    )


def _box_key(key: str) -> str:
    return read_rule_key(key).text if is_rule_key(key) else key.strip()


def _stacked_key(key: str) -> str:
    return _box_key(key) if is_rule_key(key) else canonical_entity_key(key)


def _keyed[Stated](
    raw: object, where: str, key_of: Callable[[str], str], stated_of: Callable[[object, str], Stated]
) -> dict[str, Stated]:
    result: dict[str, Stated] = {}
    for written, value in _section(raw, where).items():
        try:
            key = key_of(written)
        except (MalformedGroupings, MalformedRelationKey) as refusal:
            raise MalformedLayout(f"{where}: {refusal}") from refusal
        if key in result:
            raise MalformedLayout(f"{where} states '{key}' twice, under two spellings.")
        result[key] = stated_of(value, f"{where}.{written}")
    return result


def read_layout(raw: object) -> Layout:
    """The layout a parsed ``layout`` block states. Refuses, with a sentence, a block that is not one."""
    stated = _mapping(raw, LAYOUT_KEY, frozenset({"grid", "elements", "boxes", "relations", "z"}))
    grid = _whole(stated["grid"], "layout.grid") if "grid" in stated else None
    if grid is not None and grid < 1:
        raise MalformedLayout(f"layout.grid is {grid}; a grid is at least 1.")
    return Layout(
        grid=grid,
        elements=_keyed(stated.get("elements", {}), "layout.elements", canonical_entity_key, _placed),
        boxes=_keyed(stated.get("boxes", {}), "layout.boxes", _box_key, _placed),
        relations=_keyed(
            stated.get("relations", {}), "layout.relations", lambda key: read_relation_key(key).text, _route
        ),
        z=_keyed(stated.get("z", {}), "layout.z", _stacked_key, _whole),
    )


def _placed_as_written(placed: Placed) -> dict[str, int]:
    written = {"x": placed.x, "y": placed.y}
    if placed.w is not None and placed.h is not None:
        written.update(w=placed.w, h=placed.h)
    return written


def _number(fraction: float) -> int | float:
    return int(fraction) if fraction == int(fraction) else fraction


def _route_as_written(route: Route) -> dict[str, object]:
    written: dict[str, object] = {}
    for key, port in (("from", route.source), ("to", route.target)):
        if port is not None:
            written[key] = {"side": port.side.value, "at": _number(port.at)}
    if route.via:
        written["via"] = [[x, y] for x, y in route.via]
    if route.label is not None:
        written["label"] = {"at": _number(route.label.at), "dx": route.label.dx, "dy": route.label.dy}
    return written


def layout_as_written(layout: Layout) -> dict[str, object]:
    """The mapping a frontmatter holds for *layout*: sections in one order, the empty ones left out."""
    written: dict[str, object] = {}
    if layout.grid is not None:
        written["grid"] = layout.grid
    if layout.elements:
        written["elements"] = {key: _placed_as_written(placed) for key, placed in layout.elements.items()}
    if layout.boxes:
        written["boxes"] = {key: _placed_as_written(placed) for key, placed in layout.boxes.items()}
    if layout.relations:
        written["relations"] = {key: _route_as_written(route) for key, route in layout.relations.items()}
    if layout.z:
        written["z"] = dict(layout.z)
    return written
