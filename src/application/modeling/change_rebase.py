"""Classifying what happens to each proposed change when the enterprise artifact has moved on.

A change is a recorded write call, replayed against whatever its target has become. When the
enterprise repository moves — a reviewer merges something, another engagement promotes — each pending
change is in one of three positions, and telling them apart is what makes a rebase reportable rather
than a wall of conflicts:

* **superseded** — the artifact already says what the change asked. Nothing to replay, and reporting
  it as a conflict would ask an author to resolve their own accepted work. This is why integration
  detection had to exist first.
* **clean** — the change replays and the result still verifies.
* **conflicting** — it cannot be replayed, or what it produces no longer verifies. The verifier's own
  refusal is carried, not paraphrased: it is the message the author will act on, and a second wording
  of it here would be a second vocabulary for the same refusal.

**Semantic replay is why "the file moved in an unrelated section" is not a case.** A change names
fields, so a section it does not name cannot conflict with it — that is the property cycle 2 chose
this representation for, and the test that would have been about textual context is instead about the
one thing that can still go wrong: the *field* moved.

The two capabilities this cannot have — reading the current artifact and attempting the replay — are
injected, so the classification is decidable against records a test builds rather than against a
repository it has to construct and a worktree it has to drive.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal, TypeAlias, get_args

from src.application.modeling.integration_detection import current_values_of, integration_verdict
from src.application.modeling.proposal_edit import ProposalEdit
from src.domain.ontology_representation.artifact_types import DocumentRecord, EntityRecord

#: Where one change stands against a moved enterprise artifact.
RebaseOutcome: TypeAlias = Literal["clean", "superseded", "conflicting"]

#: The closed set, so a summary iterates the outcomes rather than restating them as strings.
REBASE_OUTCOMES: tuple[RebaseOutcome, ...] = get_args(RebaseOutcome)

#: The current enterprise artifact for a change's target, or None where it cannot be read.
TargetReader: TypeAlias = Callable[[str], EntityRecord | DocumentRecord | None]

#: Attempt the edit somewhere disposable. Returns the refusal, or None when it applied and verified.
ReplayAttempt: TypeAlias = Callable[[ProposalEdit], str | None]


@dataclass(frozen=True, slots=True)
class ClassifiedChange:
    """One change's position, and why it is there."""

    proposal_id: str
    target_id: str
    outcome: RebaseOutcome
    #: What an author reads. For a conflict it is the refusal itself, verbatim.
    reason: str


@dataclass(frozen=True, slots=True)
class RehearsedRebase:
    """What a rehearsal concluded about the whole set.

    Kept as one collection with an outcome per change rather than three lists: a caller reporting to
    an author wants them in the order they were submitted, and a caller deciding whether to proceed
    wants a count — and three lists make the first awkward to get right while making the second look
    easier than it is.
    """

    changes: tuple[ClassifiedChange, ...]

    def with_outcome(self, outcome: RebaseOutcome) -> tuple[ClassifiedChange, ...]:
        return tuple(change for change in self.changes if change.outcome == outcome)

    @property
    def can_proceed(self) -> bool:
        """Whether a replacement branch is worth opening.

        No conflicts, and something left to carry. A set that is entirely superseded has nothing to
        put on a new branch — the work is already upstream, and opening one would publish an empty
        change for a reviewer to puzzle over.
        """
        return not self.with_outcome("conflicting") and bool(self.with_outcome("clean"))

    def summary(self) -> str:
        counts = {outcome: len(self.with_outcome(outcome)) for outcome in REBASE_OUTCOMES}
        return f"{counts['clean']} clean, {counts['superseded']} already upstream, {counts['conflicting']} conflicting"


def rehearse_rebase(
    changes: Iterable[tuple[str, ProposalEdit]],
    *,
    target_of: TargetReader,
    replay: ReplayAttempt,
) -> RehearsedRebase:
    """Classify each `(proposal_id, edit)` against the enterprise artifact it targets.

    Order is preserved: replay order is part of the submission's command, and a report that reordered
    it would not describe what a later replay will do.
    """
    return RehearsedRebase(tuple(_classify(pid, edit, target_of, replay) for pid, edit in changes))


def _classify(
    proposal_id: str,
    edit: ProposalEdit,
    target_of: TargetReader,
    replay: ReplayAttempt,
) -> ClassifiedChange:
    target = target_of(edit.artifact_id)
    if target is None:
        return ClassifiedChange(
            proposal_id,
            edit.artifact_id,
            "conflicting",
            f"{edit.artifact_id} is not in the enterprise repository any more, so this change has "
            "nothing to apply to.",
        )

    if integration_verdict(edit, current_values_of(target)).integrated:
        return ClassifiedChange(
            proposal_id,
            edit.artifact_id,
            "superseded",
            f"{edit.artifact_id} already says what this change asked for.",
        )

    refusal = replay(edit)
    if refusal is not None:
        return ClassifiedChange(proposal_id, edit.artifact_id, "conflicting", refusal)
    return ClassifiedChange(
        proposal_id, edit.artifact_id, "clean", f"replays onto {edit.artifact_id} as it stands now."
    )
