"""Closing the proposed changes a reviewer has already applied.

Runs where the enterprise repository has just moved: at startup, and after the git watcher fetches.
Both are the same question asked of every submitted change — *does the enterprise artifact already
say what this asked for?* — and the answer closes the ones that do.

**Only submitted changes are swept.** A draft has not been sent to anyone, so an artifact that
happens to match it is a coincidence rather than an integration: the author may be mid-edit, and
closing their draft because someone else made the same change would delete work they never
submitted. `integrated` and `abandoned` are terminal and are not revisited.

The sweep reports what it did and what it could not decide. A change that stays open because a field
has no current reading is not a failure, but it is the answer to "why is this still pending", and a
sweep that only counted closures would leave that unanswerable.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from src.application.modeling.integration_detection import (
    IntegrationVerdict,
    current_values_of,
    integration_verdict,
)
from src.application.modeling.proposal_edit import ProposalEdit, UnproposableEdit, from_mapping
from src.application.modeling.proposed_change import (
    PROPOSAL_STATE,
    PROPOSED_CHANGE_TYPE,
    RECORDED_EDIT,
    SUBMITTED_STATE,
)
from src.domain.ontology_representation.artifact_types import DocumentRecord, EntityRecord

#: The one state a sweep may close. See the module docstring: a draft has been sent to nobody.
#: The value has one owner; what this module adds is *which* of the states it acts on.
SWEEPABLE = SUBMITTED_STATE

#: Records the enterprise artifact for a change, or None when it cannot be read.
TargetReader = Callable[[str], EntityRecord | DocumentRecord | None]

#: Records the proposal's state, returning whether the file changed.
StateWriter = Callable[[EntityRecord], bool]


@dataclass(frozen=True, slots=True)
class SweptChange:
    proposal_id: str
    target_id: str
    verdict: IntegrationVerdict
    closed: bool


@dataclass(frozen=True, slots=True)
class SweepReport:
    """What one pass concluded. `left_open` carries the changes that are still pending, with why."""

    closed: tuple[SweptChange, ...]
    left_open: tuple[SweptChange, ...]
    #: The changes returned to `draft` because no branch is published for them to be awaiting review
    #: on. Decided by the adapter, which is the half that knows about branches.
    returned_to_draft: tuple[str, ...] = ()

    @property
    def changed_anything(self) -> bool:
        return bool(self.closed or self.returned_to_draft)

    def summary(self) -> str:
        if not self.closed and not self.left_open:
            return "no submitted changes to reconcile"
        stranded = (
            f"; {len(self.returned_to_draft)} returned to draft" if self.returned_to_draft else ""
        )
        return (
            f"closed {len(self.closed)} integrated change(s); "
            f"{len(self.left_open)} still awaiting review{stranded}"
        )


def sweepable(proposals: Iterable[EntityRecord]) -> tuple[EntityRecord, ...]:
    """The changes a sweep may judge: proposed changes that were actually submitted.

    Separate from the sweep because the infrastructure has to know the answer *before* it can read
    the upstream this decision is made against — resolving that is expensive, and asking it when
    there is nothing to judge would put a checkout in the path of every backend start.
    """
    return tuple(
        proposal
        for proposal in proposals
        if proposal.artifact_type == PROPOSED_CHANGE_TYPE
        and str(proposal.extra.get(PROPOSAL_STATE, "")) == SWEEPABLE
    )


def sweep_integrated_changes(
    proposals: Iterable[EntityRecord],
    *,
    target_of: TargetReader,
    close: StateWriter,
) -> SweepReport:
    """Close every submitted change the enterprise artifact already carries.

    `target_of` and `close` are injected because this decides *which* changes are integrated and the
    infrastructure decides how to read an enterprise repository and how to write a file — the same
    split that lets the decision be tested against records the test builds rather than a repository
    it has to construct on disk.
    """
    closed: list[SweptChange] = []
    left_open: list[SweptChange] = []

    for proposal in sweepable(proposals):
        edit = _recorded_edit(proposal)
        if edit is None:
            continue
        # The *enterprise* artifact, from the recorded edit — which is where it is stated, because
        # that is what a replay addresses. `proposes-change-to` names the local reference standing
        # for it: an engagement deployment holds no enterprise content to point at, so a change
        # naming the promoted artifact names what its own verifier cannot find. Reading the target
        # from there would have this sweep comparing the edit against the *proxy's* values.
        target_id = edit.artifact_id.strip()
        if not target_id:
            continue

        verdict = integration_verdict(edit, current_values_of(target_of(target_id)))
        swept = SweptChange(proposal.artifact_id, target_id, verdict, closed=verdict.integrated)
        if verdict.integrated and close(proposal):
            closed.append(swept)
        else:
            left_open.append(swept)

    return SweepReport(closed=tuple(closed), left_open=tuple(left_open))


def _recorded_edit(proposal: EntityRecord) -> ProposalEdit | None:
    """The edit this change carries, or None where it cannot be read.

    Skipped rather than raised on, matching the read path: the verifier already refuses a malformed
    proposal with a code and a message, and a sweep that failed on one would stop reconciling every
    other change behind it.
    """
    raw = proposal.extra.get(RECORDED_EDIT)
    if not isinstance(raw, Mapping):
        return None
    try:
        return from_mapping(raw)
    except (UnproposableEdit, KeyError, TypeError, ValueError):
        return None
