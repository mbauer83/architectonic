"""How far a submission of proposed changes has got — a closed union, persisted before the push.

A submission cannot be one transaction. The push updates a remote nobody can roll back, and it
happens before local state is persisted, so a failure between the two leaves a review branch on the
remote that nothing local knows about. Retrying then either opens a second branch or reports a
withdrawal that did not happen.

So the intent is written down **first** and the outcome is *derived* afterwards by comparing the
remote ref against the commit the submission expected. That makes the push idempotent: a retry that
finds the ref already at the expected commit has nothing left to do, and one that finds it at a
different commit is a conflict to report rather than a success to assume.

**Three arms, and fields that accumulate.** `pushed_at` cannot exist before the push and
`submitted_at` cannot exist before the changes are marked, so neither is an optional field waiting to
be filled — each arm carries exactly what is true by the time it exists. Reaching an arm requires
coming from the one before it, which is why the transitions are methods rather than a constructor
anyone can call with any combination.

The intent itself is shared by composition rather than by a base class: all three arms are about the
same submission, and what differs is only how far it went.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal, TypeAlias

#: The discriminator a persisted record carries.
PREPARED: Final[Literal["prepared"]] = "prepared"
PUSHED: Final[Literal["pushed"]] = "pushed"
SUBMITTED: Final[Literal["submitted"]] = "submitted"

PhaseName: TypeAlias = Literal["prepared", "pushed", "submitted"]


class ImpossibleSubmission(ValueError):
    """A submission record that cannot describe a real submission."""


def validate_proposal_ids(proposal_ids: tuple[str, ...]) -> None:
    """What makes a list of change ids submittable at all, whatever is asking.

    Here rather than only inside `SubmissionIntent` because the set is composed long before the
    intent can exist: the intent records the commit the submission expects on the remote, and that
    commit is not made until the changes have been replayed. A caller that could only learn its ids
    were unusable by constructing the intent would learn it after writing to the enterprise
    repository, which is the one place a refusal is expensive.
    """
    if not proposal_ids:
        raise ImpossibleSubmission("a submission carries at least one proposed change")
    if len(set(proposal_ids)) != len(proposal_ids):
        raise ImpossibleSubmission(
            f"a submission names a change twice: {proposal_ids}. Replay follows this order, so a "
            "repeat would apply the same edit twice."
        )


@dataclass(frozen=True, slots=True)
class SubmissionIntent:
    """What a submission set out to do: which changes, on which branch, from which commit.

    `proposal_ids` is **ordered**, and the order is part of the command rather than derived from
    filesystem order, selection order or timestamps. Several changes against one artifact are
    ordinary, so replay order decides the result; inferring it would make the same submission produce
    different content on different machines.
    """

    proposal_ids: tuple[str, ...]
    branch: str
    expected_commit: str

    def __post_init__(self) -> None:
        validate_proposal_ids(self.proposal_ids)
        if not self.branch.strip():
            raise ImpossibleSubmission("a submission names the branch it is pushed to")
        if not self.expected_commit.strip():
            raise ImpossibleSubmission(
                "a submission records the commit it expects on the remote; without one, a retry "
                "cannot tell an already-completed push from a branch someone else moved"
            )

    def to_mapping(self) -> Mapping[str, object]:
        return {
            "proposal_ids": list(self.proposal_ids),
            "branch": self.branch,
            "expected_commit": self.expected_commit,
        }


@dataclass(frozen=True, slots=True)
class PreparedSubmission:
    """Written before the push. Nothing has reached the remote, or nothing is known to have."""

    intent: SubmissionIntent

    phase: Final[PhaseName] = PREPARED

    def pushed(self, *, at: str) -> PushedSubmission:
        return PushedSubmission(intent=self.intent, pushed_at=at)

    def to_mapping(self) -> Mapping[str, object]:
        return {"phase": PREPARED, **self.intent.to_mapping()}


@dataclass(frozen=True, slots=True)
class PushedSubmission:
    """The remote ref has been confirmed at the expected commit. The changes are not yet marked."""

    intent: SubmissionIntent
    pushed_at: str

    phase: Final[PhaseName] = PUSHED

    def submitted(self, *, at: str) -> CompletedSubmission:
        return CompletedSubmission(intent=self.intent, pushed_at=self.pushed_at, submitted_at=at)

    def to_mapping(self) -> Mapping[str, object]:
        return {"phase": PUSHED, "pushed_at": self.pushed_at, **self.intent.to_mapping()}


@dataclass(frozen=True, slots=True)
class CompletedSubmission:
    """The changes are marked submitted. Nothing about this record needs reconciling again."""

    intent: SubmissionIntent
    pushed_at: str
    submitted_at: str

    phase: Final[PhaseName] = SUBMITTED

    def to_mapping(self) -> Mapping[str, object]:
        return {
            "phase": SUBMITTED,
            "pushed_at": self.pushed_at,
            "submitted_at": self.submitted_at,
            **self.intent.to_mapping(),
        }


#: One submission's progress. Matched exhaustively: what reconciliation does on startup depends
#: entirely on which arm it finds, and a fourth would be a phase nobody had decided how to resolve.
SubmissionPhase: TypeAlias = PreparedSubmission | PushedSubmission | CompletedSubmission

#: The arms still awaiting reconciliation. `CompletedSubmission` is finished by definition, so a
#: reconciler that touched one would be re-deciding a settled question against a remote that has
#: since moved on.
UNRESOLVED: tuple[str, ...] = (PREPARED, PUSHED)


def submission_from_mapping(payload: Mapping[str, object]) -> SubmissionPhase:
    """Read back what `to_mapping` wrote, refusing anything the union does not admit.

    Stated over what the encoding permits rather than what the writer emits today. An unrecognised
    phase is refused rather than read as `prepared`, which is the reading that would re-push a
    submission already under review.
    """
    intent = SubmissionIntent(
        proposal_ids=tuple(str(p) for p in _sequence(payload, "proposal_ids")),
        branch=str(payload.get("branch", "")),
        expected_commit=str(payload.get("expected_commit", "")),
    )
    match payload.get("phase"):
        case p if p == PREPARED:
            return PreparedSubmission(intent=intent)
        case p if p == PUSHED:
            return PushedSubmission(intent=intent, pushed_at=_stamp(payload, "pushed_at"))
        case p if p == SUBMITTED:
            return CompletedSubmission(
                intent=intent,
                pushed_at=_stamp(payload, "pushed_at"),
                submitted_at=_stamp(payload, "submitted_at"),
            )
        case other:
            raise ImpossibleSubmission(
                f"{other!r} is not a submission phase; expected one of {PREPARED}, {PUSHED}, {SUBMITTED}"
            )


def _sequence(payload: Mapping[str, object], key: str) -> tuple[object, ...]:
    value = payload.get(key)
    if isinstance(value, str) or not isinstance(value, list | tuple):
        raise ImpossibleSubmission(f"{key} must be an ordered list of change ids, got {value!r}")
    return tuple(value)


def _stamp(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ImpossibleSubmission(
            f"a {payload.get('phase')!r} submission records {key}; without it there is no evidence "
            "of when the step it reports actually happened"
        )
    return value
