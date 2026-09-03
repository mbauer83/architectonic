"""Deciding whether a proposed change has already been applied upstream, and closing it if so.

A change is submitted as a review branch. When a reviewer accepts it, the enterprise artifact comes
back through the normal sync carrying the change — and the local record that proposed it is now
describing an edit that has happened. Leaving it open means an author sees a pending change against
an artifact that already says what they asked for, and a rebase that reports a conflict against
their own accepted work.

**Decided on parsed fields, per cycle 1's measurement.** The recorded edit names fields; each one is
compared against what the artifact says now. The alternative — replay the edit and diff the rendered
result — fails on its own output, because a replay re-renders the whole artifact and normalises
quoting, key order and whitespace. Both an integrated and an unintegrated change come back
"different", so the diff answers nothing.

**Every recorded field must be readable and equal.** A field with no reading here counts as *not*
integrated, which is the safe direction: a change wrongly left open is one an author can still
submit, while one wrongly closed is one that silently never happens. That is also why a proposal
whose target cannot be found at all is left alone — an unmounted enterprise repository is missing
evidence, not evidence of integration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.application.modeling.edit_field_values import (
    comparable,
    current_document_values,
    current_entity_values,
)
from src.application.modeling.proposal_edit import ProposalEdit
from src.domain.ontology_representation.artifact_types import DocumentRecord, EntityRecord


@dataclass(frozen=True, slots=True)
class IntegrationVerdict:
    """Whether the change is already applied, and which fields decided it.

    `undecidable` names the recorded fields with no current reading. It is not a failure — it is why
    a change stays open, and an operator asking "why is this still pending" needs the answer.
    """

    integrated: bool
    matching: tuple[str, ...]
    differing: tuple[str, ...]
    undecidable: tuple[str, ...]


def integration_verdict(edit: ProposalEdit, current: Mapping[str, Any] | None) -> IntegrationVerdict:
    """Compare a recorded edit against the artifact's current fields.

    `current` is None where the target could not be read at all, which is undecidable for every
    field rather than a difference in any of them.
    """
    if current is None:
        return IntegrationVerdict(False, (), (), tuple(sorted(edit.fields)))

    matching, differing, undecidable = [], [], []
    for field, proposed in sorted(edit.fields.items()):
        if field not in current or current[field] is None:
            undecidable.append(field)
        elif comparable(current[field]) == comparable(proposed):
            matching.append(field)
        else:
            differing.append(field)

    return IntegrationVerdict(
        integrated=bool(matching) and not differing and not undecidable,
        matching=tuple(matching),
        differing=tuple(differing),
        undecidable=tuple(undecidable),
    )


def current_values_of(record: EntityRecord | DocumentRecord | None) -> Mapping[str, Any] | None:
    """The editable fields of whichever kind of artifact this is, or None where there is no reading.

    A diagram gets None: most of its editable fields are nested documents with no single current
    value, so a diagram proposal is never closed automatically. Stated here rather than by omitting
    the arm, so the reason survives the next reader.
    """
    match record:
        case EntityRecord():
            return current_entity_values(record)
        case DocumentRecord():
            return current_document_values(record)
        case _:
            return None
