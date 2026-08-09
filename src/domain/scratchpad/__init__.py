"""The scratchpad domain: the aggregate, its invariants, and canvas geometry."""

from src.domain.scratchpad.geometry import GRID, Point, Rect, snap, snap_point, snap_rect
from src.domain.scratchpad.scratchpad import (
    UNFILED,
    Area,
    Destination,
    Group,
    Layout,
    Link,
    ModelRef,
    ModelRefKind,
    Note,
    Scratchpad,
    ScratchpadError,
    ordered_ids,
    scratchpad_from_parts,
)

__all__ = [
    "GRID",
    "UNFILED",
    "Area",
    "Destination",
    "Group",
    "Layout",
    "Link",
    "ModelRef",
    "ModelRefKind",
    "Note",
    "Point",
    "Rect",
    "Scratchpad",
    "ScratchpadError",
    "ordered_ids",
    "scratchpad_from_parts",
    "snap",
    "snap_point",
    "snap_rect",
]
