"""What a note may stop being, and what a whole-document write may therefore change.

Every refusal a transition carries is stated here once, as a guard over the note it is asked of. The
aggregate's mutations call these before changing anything; `refuse_forbidden_transitions`, beside
the aggregate, calls the same ones over the difference between a stored scratchpad and a submitted
one. That second caller is
the reason the guards are apart from the mutations: both surfaces write a whole document, so a rule
held only inside a mutation was a rule no write ever ran — a replace could retype a note
that had already become model content, and nothing compared the two states to notice.

A guard looks at one note and nothing else. What must hold *between* notes is `invariants`, and it
is checked of the submitted state as a whole; running the mutations themselves over the stored
aggregate instead would validate every intermediate state, and refuse a write for a collision that
only exists halfway through it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from src.domain.scratchpad.classification import classification_of, is_classified
from src.domain.scratchpad.parts import ModelRef, Note, ScratchpadError


def _release_verb(reference: ModelRef) -> str:
    return "unbind it" if reference.kind == "bound" else "forget the realization"


def refuse_retyping(note: Note) -> None:
    """A bound note's type is the entity's, and a realized one's is what the lift created.

    Retyping either would make the note describe something the model does not contain.
    """
    if note.model_ref is not None:
        raise ScratchpadError(
            f"note {note.id!r} takes its type from {note.model_ref.artifact_id!r}; "
            f"{_release_verb(note.model_ref)} first"
        )


def refuse_documenting(note: Note) -> None:
    """A note that is already something in the model is not sent elsewhere: a destination is not a
    rename."""
    if note.model_ref is not None:
        raise ScratchpadError(
            f"note {note.id!r} is tied to {note.model_ref.artifact_id!r}; "
            f"{_release_verb(note.model_ref)} before sending it to a document"
        )


def refuse_untyping(note: Note) -> None:
    """Untyping is free only while nothing in the model depends on the type."""
    if note.model_ref is not None:
        raise ScratchpadError(
            f"note {note.id!r} is tied to {note.model_ref.artifact_id!r}; "
            f"{_release_verb(note.model_ref)} before untyping"
        )


def refuse_forgetting(note: Note) -> None:
    if note.model_ref is None or note.model_ref.kind != "realized":
        raise ScratchpadError(
            f"note {note.id!r} is not realized; there is no realization to forget"
        )


def refuse_binding(note: Note) -> None:
    """A realized note is what a lift made it; pointing it elsewhere would misdescribe that."""
    if note.model_ref is not None and note.model_ref.kind == "realized":
        raise ScratchpadError(
            f"note {note.id!r} was realized as {note.model_ref.artifact_id!r}; forget the "
            "realization before binding it to something else"
        )


def refuse_unbinding(note: Note) -> None:
    if note.model_ref is None:
        raise ScratchpadError(f"note {note.id!r} is not bound to anything")
    if note.model_ref.kind == "realized":
        raise ScratchpadError(
            f"note {note.id!r} is realized as {note.model_ref.artifact_id!r}, not bound; "
            "forget the realization instead — unbinding would misdescribe what happened"
        )


def refuse_changing_meta_ontology(notes: Sequence[Note], *, current: str, proposed: str) -> None:
    """Existing types would silently become invalid against a vocabulary that never declared them.

    The state is reachable rather than a trap: forget realizations, unbind bindings, untype the
    rest, and this opens again.
    """
    typed = sorted(note.id for note in notes if is_classified(note) or note.document_type)
    if typed and proposed != current:
        raise ScratchpadError(
            f"cannot change meta-ontology while notes are typed: {typed}. "
            "Untype them first — a realized note must be forgotten and a bound note unbound."
        )


def refuse_forbidden_note_transitions(stored: Sequence[Note], submitted: Sequence[Note]) -> None:
    """Refuse a set of notes that moves the stored ones somewhere their own transitions would not.

    Each note both sets hold is read as the transition it amounts to, and the guard for that
    transition is asked. A note only one set holds is a creation or a removal, and neither is
    guarded.
    """
    proposed = {note.id: note for note in submitted}
    for before in stored:
        after = proposed.get(before.id)
        if after is not None:
            _refuse_note_transition(before, after)


def _refuse_note_transition(before: Note, after: Note) -> None:
    if before.model_ref == after.model_ref:
        _refuse_reclassification(before, after)
        return
    if after.model_ref is None:
        # The note stops claiming model content — by the act its reference calls for — and is then
        # free to be whatever the same write makes of it.
        (refuse_unbinding if _is_bound(before) else refuse_forgetting)(before)
        _refuse_reclassification(replace(before, model_ref=None), after)
        return
    # The note points somewhere it did not. Its type arrives with the reference, so there is no
    # separate retyping to ask about.
    refuse_binding(before)


def _is_bound(note: Note) -> bool:
    return note.model_ref is not None and note.model_ref.kind == "bound"


def _refuse_reclassification(before: Note, after: Note) -> None:
    """Ask the guard for whichever change of destination or type the two notes differ by."""
    if _decision(before) == _decision(after):
        return
    if after.destination == "document":
        refuse_documenting(before)
    elif is_classified(after):
        refuse_retyping(before)
    else:
        refuse_untyping(before)


def _decision(note: Note) -> tuple[object, ...]:
    return (note.destination, *classification_of(note), note.document_type)
