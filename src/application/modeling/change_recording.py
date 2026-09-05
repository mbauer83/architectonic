"""What a further edit does to an enterprise artifact that already carries a change.

One change per artifact, and that is a rule about the whole lifecycle rather than about a list view.
An author who edits a promoted requirement twice has changed it twice; they have not made two
proposals, and a reviewer should not be asked to hold two overlapping opinions about one artifact.

**So a further edit never adds a change. It replaces the one that is there** — and how it replaces it
depends on whether anyone upstream has been shown it yet:

* nothing pending — the edit is recorded as a new change;
* a `draft` — nobody has seen it, so the recorded edit is replaced in place;
* a `submitted` — it has been put to someone. It cannot be edited under them, so it is superseded:
  a new change carries the union of both edits, the old one goes terminal, and its branch is retired
  only once the replacement is established.

**The union, newest winning per field.** The author edited the artifact they were shown, and what
they were shown already carried their earlier change — that is what `proposal_composition` exists
for. So the second edit is the newer opinion about the fields it names, and says nothing about the
fields it does not. Dropping the earlier change's other fields would discard work the author never
retracted.

**The base revision does not move.** It records what the enterprise artifact was when the change was
written against it, and superseding is not an event upstream. Staleness is decided by comparing that
revision against enterprise HEAD, so moving it here would silently mark a stale change current.

**Sequencing is not what this is.** Two changes to one field, ordered, is a different feature — the
plan refuses it outright, on the ground that an implicit last-writer-wins over model content is not a
governance workflow. This never produces two live changes to reconcile.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from src.application.modeling.edit_field_catalogue import ArtifactKind
from src.application.modeling.proposal_edit import ProposalEdit
from src.application.modeling.proposal_standing import PendingProposal

#: The lifecycle states this module distinguishes. A change nobody has been shown may be rewritten;
#: one that has been submitted may not, and is replaced instead.
_DRAFT = "draft"
_SUBMITTED = "submitted"


@dataclass(frozen=True, slots=True)
class RecordNew:
    """Nothing was pending. The edit becomes the artifact's change."""

    edit: ProposalEdit


@dataclass(frozen=True, slots=True)
class ReviseDraft:
    """A draft was pending. Its recorded edit is replaced, and it stays the same change."""

    proposal_id: str
    edit: ProposalEdit


@dataclass(frozen=True, slots=True)
class SupersedeSubmitted:
    """A submitted change was pending. It is replaced rather than edited under its reviewer.

    `superseded_ids` rather than one, because the stored shape still permits several live changes
    against one artifact — a repository written before this rule, or by a future feature that earns
    it. Replacing all of them is the only reading of "one change per artifact" that converges.

    `base_revision` is carried from what was superseded, not recomputed: superseding is not an event
    upstream, and the new change was written against exactly what the old one was.
    """

    superseded_ids: tuple[str, ...]
    base_revision: str
    edit: ProposalEdit


ChangeOutcome = RecordNew | ReviseDraft | SupersedeSubmitted


class UnrecordableChange(ValueError):
    """An edit that cannot become a change, refused where the author is present to correct it."""


def decide(
    *,
    kind: ArtifactKind,
    target_id: str,
    fields: Mapping[str, Any],
    pending: Sequence[PendingProposal],
) -> ChangeOutcome:
    """What recording `fields` against `target_id` does, given what is already pending.

    Pure. The caller supplies what it read and applies what this returns, so the rule can be stated
    against every combination without a repository — which is what a rule about lifecycles needs.
    """
    if not fields:
        raise UnrecordableChange("an edit that changes nothing is not a change")

    live = sorted(pending, key=lambda proposal: proposal.proposal_id)
    if not live:
        return RecordNew(edit=ProposalEdit(kind=kind, artifact_id=target_id, fields=dict(fields)))

    merged = _merged_fields(live, fields)
    edit = ProposalEdit(kind=kind, artifact_id=target_id, fields=merged)

    if all(proposal.state == _DRAFT for proposal in live) and len(live) == 1:
        # Nobody has been shown it. The change keeps its identity, which is what lets a reader's
        # bookmark and a badge's link stay valid across an author's second thought.
        return ReviseDraft(proposal_id=live[0].proposal_id, edit=edit)

    return SupersedeSubmitted(
        superseded_ids=tuple(proposal.proposal_id for proposal in live),
        base_revision=_base_of(live),
        edit=edit,
    )


def _merged_fields(live: Sequence[PendingProposal], fields: Mapping[str, Any]) -> dict[str, Any]:
    """Every field any live change names, then the new edit's, which win where they overlap."""
    merged: dict[str, Any] = {}
    for proposal in live:
        merged.update(proposal.edit.fields)
    merged.update(fields)
    return merged


def _base_of(live: Sequence[PendingProposal]) -> str:
    """The revision the superseded work was written against.

    Where several disagree — only reachable through the stored shape's tolerance of more than one —
    the earliest is taken, because a change that claims a newer base than its oldest content would
    read as current when part of it is not.
    """
    return min(proposal.base_revision for proposal in live)
