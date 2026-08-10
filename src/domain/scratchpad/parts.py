"""The things a scratchpad is made of.

Data, and only data: every invariant that relates them lives on the aggregate root, because the
root is the boundary of coherence and a part cannot see its siblings. Separated from the root
because the root grew past the file-size limit — and the seam is honest rather than arbitrary, one
side being values and the other being the rules over them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, get_args

from src.domain.scratchpad.geometry import Point, Rect, snap_point, snap_rect

Destination = Literal["undecided", "element", "document", "none"]

#: The same four, as data. `Literal` is a promise to the type checker and nothing at runtime, so the
#: parse boundary and the invariant both need the members in a form they can test against — and one
#: definition derived from the type is what stops the list and the type drifting apart.
DESTINATIONS: tuple[str, ...] = get_args(Destination)

#: How a note came to hold a reference into the model. Never inferred — see `Scratchpad.invariants`.
ModelRefKind = Literal["realized", "bound"]

#: The area a note that sits inside no frame belongs to. Thinking often starts in the margin, so
#: this is a real state rather than an error, and it permits every type the meta-ontology declares.
UNFILED = "unfiled"


def parse_destination(raw: object) -> Destination:
    """An unrecognised destination reads as `undecided`, the weakest claim.

    Beside the type rather than at the call site, because it *is* the type's runtime half: `Literal`
    is checked by nothing at runtime, so a stored value only becomes a `Destination` by passing
    through here.

    Coercion rather than refusal, because the caller of this is the parser reading a file. A file
    already holding a bad value was written by code that let it through, and refusing it on load
    would leave the document unreadable for good instead of wrong in one field — the read being the
    only route back to a canvas that has one. What a *request* means is a different question, and
    `refuse_unknown_destinations` answers it.

    Until 0.4.1 this was `str(row.get("destination") or "undecided")` under a
    `# type: ignore[arg-type]`, which laundered any value into the field and silenced the one checker
    that would have said so. It then reached a pydantic `Literal` in the response contract, which is
    where it finally failed: 500 on every read of that scratchpad, permanently.
    """
    match str(raw or "undecided"):
        case "element":
            return "element"
        case "document":
            return "document"
        case "none":
            return "none"
        case _:
            return "undecided"


class ScratchpadError(ValueError):
    """A write the aggregate refuses. Carries the vocabulary the caller reports verbatim."""


@dataclass(frozen=True, slots=True)
class ModelRef:
    """A one-way reference from a note to model content that exists.

    One field with a flag rather than two fields, because the storage is identical and the
    difference is entirely in provenance: `realized` was created by a lift this scratchpad
    performed, `bound` was chosen by a user from content that already existed. Conflating them
    would lose which of the two the type came from, and therefore whether untyping is free.
    """

    artifact_id: str
    kind: ModelRefKind


@dataclass(frozen=True, slots=True)
class Note:
    """One thought. The title is the only thing it must have."""

    id: str
    title: str
    body: str = ""
    destination: Destination = "undecided"
    #: The first rung of the meta-ontology's classification ladder, chosen before a type is. Stored
    #: because it is a decision in its own right — "this is motivation work" is worth recording and
    #: worth showing — and because it is what a colour on the canvas is derived from. Once a type is
    #: chosen the type implies it, and the served value is derived from the type instead.
    domain: str | None = None
    element_type: str | None = None
    specialization: str | None = None
    document_type: str | None = None
    model_ref: ModelRef | None = None
    attributes: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Link:
    """A drawn relation between two notes, typed later or never.

    `drawn_direction` keeps the gesture the user made even after the link is typed against a
    relation whose permitted triple runs the other way — the remedy for that is to *reverse* the
    link, which is only offerable if the original direction survived.
    """

    id: str
    source: str
    target: str
    connection_type: str | None = None
    model_ref: ModelRef | None = None


@dataclass(frozen=True, slots=True)
class Area:
    """A labelled frame on the canvas. Its geometry is what makes it a container.

    A frame narrows what may go in it by naming **domains** rather than types. A domain is
    `hierarchy[0]`, which every ontology module already declares, so "Vision & strategy holds
    motivation and strategy work" keeps meaning that when the ontology gains a type — where a frozen
    list of type names would quietly stop offering the new one. `permitted_element_types` remains for
    a frame that wants to be narrower still, and an empty pair means the frame narrows nothing.
    """

    id: str
    label: str
    permitted_domains: tuple[str, ...] = ()
    permitted_element_types: tuple[str, ...] = ()
    permitted_document_types: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Group:
    """A named cluster of notes inside one area — what becomes an authored grouping on lift."""

    id: str
    label: str
    members: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Layout:
    """Every coordinate in the aggregate, held apart from its content on purpose.

    A drag changes a coordinate and nothing else. Interleaved with titles and types, an afternoon
    of tidying would produce a diff no reviewer could read, and reviewing a scratchpad is one of the
    things being git-backed is *for*. Kept apart, a content change and a movement land in different
    parts of the file.
    """

    areas: Mapping[str, Rect] = field(default_factory=dict)
    notes: Mapping[str, Point] = field(default_factory=dict)
    groups: Mapping[str, Rect] = field(default_factory=dict)

    def snapped(self) -> Layout:
        """The same layout on the grid. A one-pixel jitter must not become a commit."""
        return Layout(
            areas={key: snap_rect(rect) for key, rect in self.areas.items()},
            notes={key: snap_point(point) for key, point in self.notes.items()},
            groups={key: snap_rect(rect) for key, rect in self.groups.items()},
        )
