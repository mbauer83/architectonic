"""What must hold of a scratchpad, in three groups.

Separated from the root so each group is one focused function rather than one pass branching over
all of them — which is where `validate` had got to. The root still owns them: it calls these on
every mutation, and nothing else does, so an aggregate that exists is an aggregate that holds.

Each message names the id at fault and says what to do about it. They are the refusal vocabulary a
REST or MCP caller reports verbatim, read by people and by agents alike, so a message that only
says "invalid" would be a message neither can act on.
"""

from __future__ import annotations

from collections.abc import Callable

from src.domain.scratchpad.parts import Area, Group, Link, Note, ScratchpadError


def validated_notes(notes: tuple[Note, ...]) -> set[str]:
    """Every note has a title and a unique id; a model reference implies an element with a type."""
    seen: set[str] = set()
    bound_entities: dict[str, str] = {}
    for note in notes:
        if not note.title.strip():
            raise ScratchpadError(f"note {note.id!r} has no title; a title is the one thing a note must have")
        if note.id in seen:
            raise ScratchpadError(f"duplicate note id {note.id!r}")
        seen.add(note.id)
        _validate_destination(note)
        if note.model_ref is not None:
            _validate_model_ref(note, bound_entities)
    return seen


def _validate_destination(note: Note) -> None:
    """A note goes to an element or to a document, and carries only the type that destination needs.

    Both at once is not a note that has decided two things — it is a note whose *lift* has no single
    answer, since one would create an entity and the other a document from the same title.
    """
    if note.destination == "document" and note.element_type:
        raise ScratchpadError(
            f"note {note.id!r} is destined for a document but carries the element type "
            f"{note.element_type!r}; a note has one destination"
        )
    if note.document_type and note.destination != "document":
        raise ScratchpadError(
            f"note {note.id!r} carries the document type {note.document_type!r} but its destination "
            f"is {note.destination!r}"
        )


def _validate_model_ref(note: Note, bound_entities: dict[str, str]) -> None:
    """A reference reached the `element` destination by one of two routes, and both imply a type:
    a bound note reads it off the entity, a realized one chose it before the lift. Either way, a
    reference without a type describes model content the scratchpad cannot say anything about."""
    reference = note.model_ref
    if reference is None:
        return
    if note.destination != "element":
        raise ScratchpadError(
            f"note {note.id!r} references {reference.artifact_id!r} but its destination is "
            f"{note.destination!r}; a note holding a model reference is an element"
        )
    if not note.element_type:
        raise ScratchpadError(
            f"note {note.id!r} references {reference.artifact_id!r} with no element type; "
            "a bound note takes its type from the entity and a realized one from the lift"
        )
    if reference.kind != "bound":
        return
    # Two notes bound to one entity would render the same element twice and lift as one, so the
    # canvas would show a duplicate it cannot resolve. (Two *scratchpads* binding it is fine and
    # expected — strategy and project work share capabilities.)
    previous = bound_entities.get(reference.artifact_id)
    if previous is not None:
        raise ScratchpadError(
            f"notes {previous!r} and {note.id!r} are both bound to "
            f"{reference.artifact_id!r}; bind it once per scratchpad"
        )
    bound_entities[reference.artifact_id] = note.id


def validated_links(links: tuple[Link, ...], note_ids: set[str]) -> None:
    """A link's endpoints are notes of this scratchpad, and not the same note."""
    seen: set[str] = set()
    for link in links:
        if link.id in seen:
            raise ScratchpadError(f"duplicate link id {link.id!r}")
        seen.add(link.id)
        for role, endpoint in (("source", link.source), ("target", link.target)):
            if endpoint not in note_ids:
                raise ScratchpadError(
                    f"link {link.id!r} has a {role} {endpoint!r} that is not a note in this scratchpad"
                )
        if link.source == link.target:
            raise ScratchpadError(f"link {link.id!r} joins note {link.source!r} to itself")


def validated_groups(
    groups: tuple[Group, ...],
    areas: tuple[Area, ...],
    note_ids: set[str],
    area_of: Callable[[str], str],
) -> None:
    """A group's members lie in one area, and a note belongs to at most one group."""
    area_ids: set[str] = set()
    for area in areas:
        if area.id in area_ids:
            raise ScratchpadError(f"duplicate area id {area.id!r}")
        area_ids.add(area.id)

    claimed: dict[str, str] = {}
    for group in groups:
        if group.id in area_ids:
            raise ScratchpadError(f"group id {group.id!r} collides with an area id")
        for member in group.members:
            if member not in note_ids:
                raise ScratchpadError(f"group {group.id!r} names note {member!r}, which is not in this scratchpad")
            if member in claimed:
                raise ScratchpadError(
                    f"note {member!r} is in group {claimed[member]!r} already; a note belongs to at most one"
                )
            claimed[member] = group.id
        spanned = {area_of(member) for member in group.members}
        if len(spanned) > 1:
            raise ScratchpadError(
                f"group {group.id!r} spans areas {sorted(spanned)}; a group's members lie in one area"
            )
