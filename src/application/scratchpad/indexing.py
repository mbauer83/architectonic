"""One scratchpad, as records the artifact index can hold: the pad, and the thoughts on it.

Here rather than beside the markdown parsers, because a scratchpad is not one: it is a YAML aggregate,
and what this reads it reads through `from_document` — the one place that knows what a note document
means. It is also the only parser in the system that returns records of *two kinds* for one file,
because a scratchpad is the only artifact whose searchable units live inside another.

Both come from **one** parse. A sibling function reading the same file a second time would be two
readers of one syntax, and would let the pad and its notes disagree about a file that changed between
them.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.application.scratchpad.document import from_document
from src.domain.ontology_representation.artifact_types import (
    ScratchpadNoteRecord,
    ScratchpadRecord,
    scratchpad_note_id,
)
from src.domain.scratchpad.parts import Note
from src.domain.yaml_documents import parse_yaml


def parse_scratchpad(path: Path, *, group: str) -> tuple[ScratchpadRecord | None, list[ScratchpadNoteRecord]]:
    """One scratchpad file as the index holds it: the pad, and the notes still worth returning.

    `None` for the pad where the file cannot be read or is not a valid aggregate — the same silence
    the notes have always answered with. A malformed scratchpad is not indexed and does not stop the
    scan; the product's own verifier is where a broken file is reported, and an index that refuses to
    load is not.

    It goes through the aggregate rather than reading the YAML by hand — `from_document` is the one
    place that knows what a note document means, and `area_of` derives area membership from the
    geometry, which nothing outside the aggregate is entitled to recompute.
    """
    try:
        loaded = parse_yaml(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None, []
    if not isinstance(loaded, dict):
        return None, []
    try:
        scratchpad = from_document(loaded)
    except (ValueError, TypeError, KeyError):
        return None, []
    pad = ScratchpadRecord(
        artifact_id=scratchpad.artifact_id,
        name=scratchpad.name,
        description=scratchpad.description,
        version=scratchpad.version,
        status=scratchpad.status,
        meta_ontology=scratchpad.meta_ontology,
        path=path,
        group=group,
        # Every note's reference, including the notes dropped below. `_still_a_thought` removes a
        # bound note from the *searchable* records because the model now answers for that thought —
        # but a bound note is precisely the one that references something, so reading the references
        # off the note records would find none of them.
        references=frozenset(
            note.model_ref.artifact_id for note in scratchpad.notes if note.model_ref is not None
        ),
    )
    notes = [
        ScratchpadNoteRecord(
            artifact_id=scratchpad_note_id(scratchpad.artifact_id, note.id),
            scratchpad_id=scratchpad.artifact_id,
            scratchpad_name=scratchpad.name,
            note_id=note.id,
            title=note.title,
            body=note.body,
            element_type=note.element_type or "",
            domain=note.domain or "",
            area=scratchpad.area_of(note.id),
            status=scratchpad.status,
            path=path,
            group=group,
        )
        for note in scratchpad.notes
        if _still_a_thought(note)
    ]
    return pad, notes


def _still_a_thought(note: Note) -> bool:
    """Whether this note is the thing search should return, or whether the model now is.

    A note is searchable until it has a model counterpart. Once it holds a `model_ref` the aggregate
    itself calls it an element — `invariants.py` refuses the reference unless the note's destination
    is `element`, "a note holding a model reference is an element" — so the model has a artifact
    standing for the same thought, and returning both offers two results for one thing. The weaker
    one goes: a scratchpad note is a half-formed thought and an entity is a commitment.

    Both kinds, not only `realized`. The flag distinguishes a lift this pad performed from content a
    user attached that already existed, and it earns its keep deciding whether untyping is free — not
    whether the thought is still the model's best answer to a query. A `bound` note whose body holds
    rationale the entity lacks is an argument for lifting that rationale, not for answering twice.

    **The pad is unaffected by this filter**, and that is the point of indexing it separately: a pad
    whose every note has been lifted has no searchable notes and is the only record left that the
    thinking happened.
    """
    return note.model_ref is None
