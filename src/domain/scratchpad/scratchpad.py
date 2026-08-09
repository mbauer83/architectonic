"""The scratchpad aggregate: a canvas of notes and the links between them.

A scratchpad is where thinking starts, *before* anything is typed. Its whole reason for existing is
that the typed model asks a contributor to name an element type before they have decided anything,
and that question is the wall this removes — so the invariants below are deliberately permissive
about content and strict only about coherence.

**The scratchpad is the aggregate root.** Notes, links, areas and groups have no life outside one,
and every write goes through the root. That is what lets a note be created from nothing but a title:
its id is unique within its scratchpad and meaningless outside, so no global namespace has to accept
it. It is also why this module holds no I/O and loads no catalogs — the invariants here are true of
the aggregate alone, and verification against an ontology is a separate concern that arrives with
typing (slice 3).

Area membership is **spatial and derived**, never stored: the note inside the Portfolio frame *is*
portfolio work. Storing it separately would let the two disagree — a note visibly inside one frame
that the system files under another — and the visible thing has to win, because it is the only one
the person moving it can see.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Literal

from src.domain.scratchpad.geometry import Point, Rect, snap_point, snap_rect

#: What a note has decided to become. `undecided` is the state a note is born in and a legitimate
#: resting place: not every thought becomes model content, and forcing the choice is the wall.
Destination = Literal["undecided", "element", "document", "none"]

#: How a note came to hold a reference into the model. Never inferred — see `Scratchpad.invariants`.
ModelRefKind = Literal["realized", "bound"]

#: The area a note that sits inside no frame belongs to. Thinking often starts in the margin, so
#: this is a real state rather than an error, and it permits every type the meta-ontology declares.
UNFILED = "unfiled"


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
    """A labelled frame on the canvas. Its geometry is what makes it a container."""

    id: str
    label: str
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


@dataclass(frozen=True, slots=True)
class Scratchpad:
    """The aggregate root. Every invariant below is enforced here and nowhere else."""

    artifact_id: str
    name: str
    description: str = ""
    version: str = "0.1.0"
    status: str = "draft"
    meta_ontology: str = "archimate-4"
    attributes: Mapping[str, object] = field(default_factory=dict)
    areas: tuple[Area, ...] = ()
    notes: tuple[Note, ...] = ()
    links: tuple[Link, ...] = ()
    groups: tuple[Group, ...] = ()
    layout: Layout = field(default_factory=Layout)

    # ── Lookups ──────────────────────────────────────────────────────────────

    def note(self, note_id: str) -> Note | None:
        return next((note for note in self.notes if note.id == note_id), None)

    def area(self, area_id: str) -> Area | None:
        return next((area for area in self.areas if area.id == area_id), None)

    def area_of(self, note_id: str) -> str:
        """Which frame contains this note — derived from geometry, never stored.

        Frames may overlap, and the **smallest** containing one wins. That is what a person means
        when they drop a note into a small frame sitting on a large one, and — unlike "the last
        declared", which this first did — it depends on nothing but the geometry. Declaration order
        cannot be the tie-breaker here: the file is written in stable id order so that a no-op save
        produces no diff, so an aggregate's area order does not survive a round trip, and a note
        would change frames merely by being saved. Equal areas tie-break on id, for the same
        reason: it is the one ordering both the file and the aggregate agree on.
        """
        position = self.layout.notes.get(note_id)
        if position is None:
            return UNFILED
        containing = [
            (rect.width * rect.height, area.id)
            for area in self.areas
            if (rect := self.layout.areas.get(area.id)) is not None and rect.contains(position)
        ]
        return min(containing)[1] if containing else UNFILED

    def notes_in(self, area_id: str) -> tuple[Note, ...]:
        return tuple(note for note in self.notes if self.area_of(note.id) == area_id)

    # ── Invariants ───────────────────────────────────────────────────────────

    def validate(self) -> None:
        """Raise `ScratchpadError` on the first violation, naming what to do about it.

        Called by every mutation below rather than by the caller, so an aggregate that exists is an
        aggregate that holds. The messages are the refusal vocabulary a REST or MCP caller reports
        verbatim — they are read by people and by agents, so each says which id is at fault.
        """
        seen_notes: set[str] = set()
        for note in self.notes:
            if not note.title.strip():
                raise ScratchpadError(f"note {note.id!r} has no title; a title is the one thing a note must have")
            if note.id in seen_notes:
                raise ScratchpadError(f"duplicate note id {note.id!r}")
            seen_notes.add(note.id)

        seen_links: set[str] = set()
        for link in self.links:
            if link.id in seen_links:
                raise ScratchpadError(f"duplicate link id {link.id!r}")
            seen_links.add(link.id)
            for role, endpoint in (("source", link.source), ("target", link.target)):
                if endpoint not in seen_notes:
                    raise ScratchpadError(
                        f"link {link.id!r} has a {role} {endpoint!r} that is not a note in this scratchpad"
                    )
            if link.source == link.target:
                raise ScratchpadError(f"link {link.id!r} joins note {link.source!r} to itself")

        seen_areas: set[str] = set()
        for area in self.areas:
            if area.id in seen_areas:
                raise ScratchpadError(f"duplicate area id {area.id!r}")
            seen_areas.add(area.id)

        claimed: dict[str, str] = {}
        for group in self.groups:
            if group.id in seen_areas:
                raise ScratchpadError(f"group id {group.id!r} collides with an area id")
            for member in group.members:
                if member not in seen_notes:
                    raise ScratchpadError(f"group {group.id!r} names note {member!r}, which is not in this scratchpad")
                if member in claimed:
                    raise ScratchpadError(
                        f"note {member!r} is in group {claimed[member]!r} already; a note belongs to at most one"
                    )
                claimed[member] = group.id
            areas_spanned = {self.area_of(member) for member in group.members}
            if len(areas_spanned) > 1:
                raise ScratchpadError(
                    f"group {group.id!r} spans areas {sorted(areas_spanned)}; a group's members lie in one area"
                )

    # ── Mutations ────────────────────────────────────────────────────────────
    #
    # Each returns a new aggregate. Immutability is what makes the browser's command stack — and
    # therefore undo — a matter of keeping previous values rather than of computing inverses.

    def with_note(self, note: Note, at: Point | None = None) -> Scratchpad:
        """Add or replace a note, optionally placing it."""
        others = tuple(existing for existing in self.notes if existing.id != note.id)
        layout = self.layout
        if at is not None:
            layout = replace(layout, notes={**layout.notes, note.id: snap_point(at)})
        return self._validated(replace(self, notes=(*others, note), layout=layout))

    def without_note(self, note_id: str) -> Scratchpad:
        """Remove a note and every link touching it.

        The model is **not** touched, even for a realized or bound note: what a scratchpad put into
        the model is not the scratchpad's to retract. Removing the note removes the thinking, and
        the entity outlives it exactly as an entity created any other way would.
        """
        if self.note(note_id) is None:
            raise ScratchpadError(f"no note {note_id!r} in this scratchpad")
        return self._validated(replace(
            self,
            notes=tuple(note for note in self.notes if note.id != note_id),
            links=tuple(link for link in self.links if note_id not in (link.source, link.target)),
            groups=tuple(replace(group, members=tuple(m for m in group.members if m != note_id))
                         for group in self.groups),
            layout=replace(self.layout, notes={k: v for k, v in self.layout.notes.items() if k != note_id}),
        ))

    def with_link(self, link: Link) -> Scratchpad:
        others = tuple(existing for existing in self.links if existing.id != link.id)
        return self._validated(replace(self, links=(*others, link)))

    def without_link(self, link_id: str) -> Scratchpad:
        if not any(link.id == link_id for link in self.links):
            raise ScratchpadError(f"no link {link_id!r} in this scratchpad")
        return self._validated(replace(self, links=tuple(link for link in self.links if link.id != link_id)))

    def moved(self, note_id: str, to: Point) -> Scratchpad:
        """Place a note. This is what changes its area, because area membership is where it is."""
        if self.note(note_id) is None:
            raise ScratchpadError(f"no note {note_id!r} in this scratchpad")
        return self._validated(replace(
            self, layout=replace(self.layout, notes={**self.layout.notes, note_id: snap_point(to)})
        ))

    def with_meta_ontology(self, meta_ontology: str) -> Scratchpad:
        """Change the meta-ontology — refused while anything is typed.

        Existing types would silently become invalid against a vocabulary that never declared them.
        The state is reachable rather than a trap: forget realizations, unbind bindings, untype the
        rest (slice 3), and this opens again.
        """
        typed = [note.id for note in self.notes if note.element_type or note.document_type]
        if typed and meta_ontology != self.meta_ontology:
            raise ScratchpadError(
                f"cannot change meta-ontology while notes are typed: {sorted(typed)}. "
                "Untype them first — a realized note must be forgotten and a bound note unbound."
            )
        return self._validated(replace(self, meta_ontology=meta_ontology))

    def _validated(self, candidate: Scratchpad) -> Scratchpad:
        candidate.validate()
        return candidate


def scratchpad_from_parts(
    *,
    artifact_id: str,
    name: str,
    areas: Iterable[Area] = (),
    notes: Iterable[Note] = (),
    links: Iterable[Link] = (),
    groups: Iterable[Group] = (),
    layout: Layout | None = None,
    **rest: object,
) -> Scratchpad:
    """Build and validate in one step, so no unchecked aggregate is ever handed out."""
    scratchpad = Scratchpad(
        artifact_id=artifact_id,
        name=name,
        areas=tuple(areas),
        notes=tuple(notes),
        links=tuple(links),
        groups=tuple(groups),
        layout=(layout or Layout()).snapped(),
        **rest,  # type: ignore[arg-type]
    )
    scratchpad.validate()
    return scratchpad

