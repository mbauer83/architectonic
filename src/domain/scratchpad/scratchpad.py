"""The scratchpad aggregate root: the invariants, and every write that must hold them.

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

from src.domain.scratchpad.geometry import Point, snap_point
from src.domain.scratchpad.invariants import (
    validated_groups,
    validated_links,
    validated_notes,
)
from src.domain.scratchpad.parts import (
    UNFILED,
    Area,
    Group,
    Layout,
    Link,
    ModelRef,
    Note,
    ScratchpadError,
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

        Split by concern rather than written as one pass: the three groups share only the set of
        note ids, and one function branching over all of them was past the point where a reader
        could hold it.
        """
        note_ids = validated_notes(self.notes)
        validated_links(self.links, note_ids)
        validated_groups(self.groups, self.areas, note_ids, self.area_of)

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

    def typed(
        self, note_id: str, *, element_type: str, specialization: str | None = None
    ) -> Scratchpad:
        """Narrow a note to an element type, and optionally one level further.

        Refused on a note that already holds a model reference: a bound note's type is the
        entity's, and a realized one's is what the lift created. Retyping either would make the
        note describe something the model does not contain.
        """
        note = self.note(note_id)
        if note is None:
            raise ScratchpadError(f"no note {note_id!r} in this scratchpad")
        if note.model_ref is not None:
            verb = "unbind it" if note.model_ref.kind == "bound" else "forget the realization"
            raise ScratchpadError(
                f"note {note_id!r} takes its type from {note.model_ref.artifact_id!r}; {verb} first"
            )
        return self.with_note(replace(
            note, destination="element", element_type=element_type, specialization=specialization
        ))

    def untyped(self, note_id: str) -> Scratchpad:
        """Take a note's type away, returning it to undecided.

        **Free while the note is neither realized nor bound**, and every link touching it reverts
        to unverified — nothing downstream exists yet, so nothing needs warning. This is what keeps
        the frozen meta-ontology from being a trap: forget the realizations, unbind the bindings,
        untype the rest, and the scratchpad can change vocabulary again.
        """
        note = self.note(note_id)
        if note is None:
            raise ScratchpadError(f"no note {note_id!r} in this scratchpad")
        if note.model_ref is not None:
            verb = "unbind it" if note.model_ref.kind == "bound" else "forget the realization"
            raise ScratchpadError(
                f"note {note_id!r} is tied to {note.model_ref.artifact_id!r}; {verb} before untyping"
            )
        # Links touching it lose their type too: a typed link between an untyped end and anything
        # is a claim the aggregate can no longer support.
        return self._validated(replace(
            replace(self, notes=tuple(
                replace(existing, destination="undecided", element_type=None, specialization=None)
                if existing.id == note_id else existing
                for existing in self.notes
            )),
            links=tuple(
                replace(link, connection_type=None) if note_id in (link.source, link.target) else link
                for link in self.links
            ),
        ))

    def forgotten(self, note_id: str) -> Scratchpad:
        """Drop a realization, leaving the entity exactly where it is.

        Invariant 6 says the scratchpad may not retract model content, so this is the *only* thing
        a note can do about a lift it no longer wants to claim: stop claiming it. The entity
        outlives the note, as an entity created any other way would.
        """
        note = self.note(note_id)
        if note is None:
            raise ScratchpadError(f"no note {note_id!r} in this scratchpad")
        if note.model_ref is None or note.model_ref.kind != "realized":
            raise ScratchpadError(
                f"note {note_id!r} is not realized; there is no realization to forget"
            )
        return self.with_note(replace(note, model_ref=None))

    def bound(self, note_id: str, *, artifact_id: str, element_type: str) -> Scratchpad:
        """Tie a note to model content that already exists.

        Binding is what makes a scratchpad useful against a repository that is not empty: the
        common move is thinking about work that touches things that exist, and without it a lift
        would mint a duplicate with nothing to stop it. The type comes from the entity rather than
        from the note — the entity is the authority on what it is.
        """
        note = self.note(note_id)
        if note is None:
            raise ScratchpadError(f"no note {note_id!r} in this scratchpad")
        if note.model_ref is not None and note.model_ref.kind == "realized":
            raise ScratchpadError(
                f"note {note_id!r} was realized as {note.model_ref.artifact_id!r}; forget the "
                "realization before binding it to something else"
            )
        return self.with_note(replace(
            note,
            destination="element",
            element_type=element_type,
            model_ref=ModelRef(artifact_id=artifact_id, kind="bound"),
        ))

    def unbound(self, note_id: str) -> Scratchpad:
        """Release a binding. Free, because nothing downstream depends on it.

        The entity is untouched — the scratchpad never retracts model content — and the note keeps
        its title while losing the type it was only borrowing. A *realized* note is refused here:
        dropping that reference is `forget`, a different act with a different consequence.
        """
        note = self.note(note_id)
        if note is None:
            raise ScratchpadError(f"no note {note_id!r} in this scratchpad")
        if note.model_ref is None:
            raise ScratchpadError(f"note {note_id!r} is not bound to anything")
        if note.model_ref.kind == "realized":
            raise ScratchpadError(
                f"note {note_id!r} is realized as {note.model_ref.artifact_id!r}, not bound; "
                "forget the realization instead — unbinding would misdescribe what happened"
            )
        return self.with_note(replace(
            note, destination="undecided", element_type=None, specialization=None, model_ref=None
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
