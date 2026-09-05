"""Showing an author their own pending change, on top of the baseline they cannot write.

An engagement repository reads enterprise artifacts through references. A change to one is recorded
and lives locally until it is accepted upstream — and until this module existed, a read returned the
*baseline*, with a badge naming which fields differed but not what they now said.

**That was the defect, and it is worse than a missing feature.** An author who changes a summary and
then opens the artifact again sees the old summary. Their next edit is written over their own
invisible work, and accepting both in order would silently undo the first. A person cannot control
what they cannot see.

**Only the view composes.** The recorded change keeps the enterprise revision it was written
against, because that is a fact about the enterprise and the enterprise has not moved. Composing the
*base* instead would put a change's base at a state that exists nowhere upstream, and staleness —
which is decided by comparing that base against enterprise HEAD — would stop meaning anything.

**One vocabulary, not two.** A recorded edit's fields are the write call's parameter names, and the
detail read already answers in exactly those names: `read_entity` parses `summary`, `properties` and
`notes` out of the content and returns them beside `name` and `keywords`. So composing is an overlay
keyed on names both sides already use, and no mapping table can drift between them.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.application.modeling.proposal_standing import PendingProposal


def composed_view(baseline: Mapping[str, Any], proposals: Sequence[PendingProposal]) -> dict[str, Any]:
    """`baseline` with every live change's fields laid over it, later proposals winning.

    Ordered by proposal id rather than by whatever order they were gathered in, so two reads of one
    repository agree. With one change per artifact — which is what the product now enforces — the
    order settles nothing; it is here because the stored shape still permits several, and a read that
    depended on gathering order would be wrong in a way nothing would report.

    A field the change names but the baseline does not carry is still laid over: the baseline is the
    read's own payload, and a payload that omits a field it has no value for is the ordinary case.
    """
    composed = dict(baseline)
    for proposal in sorted(proposals, key=lambda p: p.proposal_id):
        composed.update(proposal.edit.fields)
    return composed


def composed_fields(proposals: Sequence[PendingProposal]) -> tuple[str, ...]:
    """Which of the read's fields carry the author's values rather than the baseline's.

    The same set `BaselineStanding.changed_fields` reports, derived here from the same edits, so a
    surface can mark the composed fields without asking a second question and getting a second
    answer.
    """
    return tuple(sorted({field for proposal in proposals for field in proposal.edit.fields}))
