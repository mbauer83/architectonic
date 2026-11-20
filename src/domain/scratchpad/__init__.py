"""The scratchpad domain: the aggregate, its invariants, and canvas geometry."""

from src.domain.scratchpad.classification import (
    LevelOption,
    TypingOptions,
    attribute_level_of,
    may_be_lifted,
    reached_levels,
    unreached_required,
    value_at,
)
from src.domain.scratchpad.geometry import GRID, Point, Rect, snap, snap_point, snap_rect
from src.domain.scratchpad.link_verdict import (
    UNVERIFIED,
    Endpoint,
    LinkVerdict,
    VerdictKind,
    verify_link,
)
from src.domain.scratchpad.note_verdict import NoteFinding, area_narrowing, note_verdict
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
from src.domain.scratchpad.transitions import refuse_forbidden_transitions

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
    "LevelOption",
    "attribute_level_of",
    "may_be_lifted",
    "reached_levels",
    "unreached_required",
    "value_at",
    "Link",
    "LinkVerdict",
    "ModelRef",
    "ModelRefKind",
    "parse_destination",
    "Note",
    "NoteFinding",
    "area_narrowing",
    "note_verdict",
    "Point",
    "Rect",
    "Scratchpad",
    "ScratchpadError",
    "TypingOptions",
    "VerdictKind",
    "refuse_forbidden_transitions",
    "scratchpad_from_parts",
    "snap",
    "snap_point",
    "snap_rect",
    "verify_link",
]
