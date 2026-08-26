"""A scratchpad whose notes point at a given artifact.

Its own module for the reason `diagram_reference` has one: both `contracts.entities` and the scratchpad
contracts could want it, and `contracts.diagrams` already imports from `contracts.entities`, so a shape
declared in either and imported by the other closes a cycle. A file per shared shape keeps the direction
question from arising at all.

Thinner than a diagram reference, deliberately. A pad has no type to weigh — there is one kind of
scratchpad — so a name to choose by and its status are the whole of what a reader needs.
"""

from __future__ import annotations

from src.infrastructure.rest.contracts.wire_nulls import NullsOmitted


class ScratchpadReference(NullsOmitted):
    """One scratchpad whose notes reference the artifact asked about.

    A *pad*, not a note, and that is the shape of the answer rather than a simplification: a note
    holding a model reference stops being a searchable record — the model answers for that thought
    instead — so the pad is both what survives indexing and what a reader navigates to.
    """

    artifact_id: str
    name: str
    status: str

    # `NullsOmitted` rather than `Closed`, which `test_wire_null_policy` requires of a DTO every one of
    # whose routes omits nulls — the entity context is its only producer. `DiagramReference` is `Closed`
    # because it is also served by `/api/diagram-refs`, which does not.
