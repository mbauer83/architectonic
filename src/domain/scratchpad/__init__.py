"""The scratchpad domain: the aggregate, its invariants, and canvas geometry."""

from src.domain.scratchpad.geometry import GRID, Point, Rect, snap, snap_point, snap_rect
from src.domain.scratchpad.link_verdict import (
    UNVERIFIED,
    Endpoint,
    LinkVerdict,
    TypingOptions,
    VerdictKind,
    verify_link,
)
from src.domain.scratchpad.parts import (
    DESTINATIONS,
    UNFILED,
    Area,
    Destination,
    Group,
    Layout,
    Link,
    ModelRef,
    ModelRefKind,
    Note,
    ScratchpadError,
    parse_destination,
)
from src.domain.scratchpad.scratchpad import Scratchpad, scratchpad_from_parts

__all__ = [
    "GRID",
    "UNVERIFIED",
    "UNFILED",
    "Area",
    "Endpoint",
    "DESTINATIONS",
    "Destination",
    "Group",
    "Layout",
    "Link",
    "LinkVerdict",
    "ModelRef",
    "ModelRefKind",
    "parse_destination",
    "Note",
    "Point",
    "Rect",
    "Scratchpad",
    "ScratchpadError",
    "TypingOptions",
    "VerdictKind",
    "scratchpad_from_parts",
    "snap",
    "snap_point",
    "snap_rect",
    "verify_link",
]
