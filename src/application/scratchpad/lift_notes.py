"""What a lift would make of one selected note.

Apart from `lift.py`, which plans the lift as a whole: this is the part that reads a note against
the classification levels its meta-ontology declares. Whether a note is complete enough to become
an element is the declaration's to say — every level it marks required has been reached — and never
a fixed "has a type" test, which would be one meta-ontology's ladder written into the preflight.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.application.scratchpad.lift_plan import LiftItem, LiftTarget
from src.domain.ontology_representation.classification_levels import ClassificationLevel
from src.domain.scratchpad import LinkVerdict, Note, may_be_lifted, unreached_required


def note_item(
    note: Note,
    target: LiftTarget,
    verdict: LinkVerdict,
    levels: Sequence[ClassificationLevel],
) -> LiftItem:
    """What would become of one selected note, and which project it lands in.

    A narrowing — the note decided as something its area does not hold — is carried as a warning and
    the note is still created: the type is one the meta-ontology declares.
    """
    warning = verdict.message if verdict.kind == "narrowed" else ""
    if note.model_ref is not None:
        return _skipped(note, target)
    if note.destination == "document":
        if not note.document_type:
            return LiftItem(
                kind="document", id=note.id, outcome="refuse", label=note.title, target=target.group,
                reason="destined for a document but with no document type chosen",
            )
        return LiftItem(
            kind="document", id=note.id, outcome="create", label=note.title, target=target.group,
            artifact_type=note.document_type, summary=note.body, warning=warning,
        )
    if note.destination != "element" or not may_be_lifted(note, levels):
        return LiftItem(
            kind="element", id=note.id, outcome="refuse", label=note.title, target=target.group,
            reason=f"undecided — {_what_it_needs(note, levels)}, or take it out of the selection",
        )
    return LiftItem(
        kind="element", id=note.id, outcome="create", label=note.title, target=target.group,
        artifact_type=note.element_type or "", summary=note.body, warning=warning,
        specializations=(note.specialization,) if note.specialization else (),
    )


def _skipped(note: Note, target: LiftTarget) -> LiftItem:
    reference = note.model_ref
    assert reference is not None  # noqa: S101 — the caller's branch; narrows the type for the reader
    kind = "bound to" if reference.kind == "bound" else "already realized as"
    return LiftItem(
        # Named for what it became: a skipped document reported as an element would be drawn
        # on the lift's diagram as an entity the model does not hold.
        kind="document" if note.destination == "document" else "element",
        id=note.id, outcome="skip", label=note.title, target=target.group,
        artifact_type=note.element_type or note.document_type or "",
        artifact_id=reference.artifact_id,
        reason=f"{kind} {reference.artifact_id} — the model is not the scratchpad's to rewrite",
    )


def _what_it_needs(note: Note, levels: Sequence[ClassificationLevel]) -> str:
    """The next thing to choose, named as the meta-ontology names it.

    The deepest required level still open, because choosing it answers the ones above — or the
    type, where the declaration requires nothing the note lacks and it still has none.
    """
    missing = unreached_required(note, levels) or tuple(
        level for level in levels if level.source == "type"
    )
    return f"choose its {missing[-1].label.lower()}" if missing else "give it a type"
