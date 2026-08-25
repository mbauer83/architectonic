"""One scratchpad, as records the artifact index can hold.

Here rather than beside the markdown parsers, because a scratchpad is not one: it is a YAML
aggregate, and what this reads it reads through `from_document` — the one place that knows what a
note document means. It is also the only parser in the system that returns *many* records for one
file, because a scratchpad is the only artifact whose searchable units live inside another.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from src.application.scratchpad.document import from_document
from src.domain.ontology_representation.artifact_types import (
    ScratchpadNoteRecord,
    scratchpad_note_id,
)
from src.domain.scratchpad.parts import Note
from src.domain.yaml_documents import parse_yaml


def parse_scratchpad_notes(path: Path, *, group: str) -> list[ScratchpadNoteRecord]:
    """Every note on one scratchpad, as records the index can hold.

    The only parser here that returns *many* records for one file, because a scratchpad is the only
    artifact whose searchable units live inside another artifact: it is loaded, saved and versioned
    whole, but what someone searches for is a thought, and a thought is a note.

    It goes through the aggregate rather than reading the YAML by hand — `from_document` is the one
    place that knows what a note document means, and `area_of` derives area membership from the
    geometry, which nothing outside the aggregate is entitled to recompute.
    """
    try:
        loaded = parse_yaml(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return []
    if not isinstance(loaded, dict):
        return []
    try:
        scratchpad = from_document(loaded)
    except (ValueError, TypeError, KeyError):
        # A malformed scratchpad is not indexed and does not stop the scan. The product's own
        # verifier is where a broken file is reported; an index that refuses to load is not.
        return []
    return [
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
    """
    return note.model_ref is None
