"""Applying a candidate architecture directly: what would be written, or the sentence that refuses it.

A candidate has one representation, its change set, and one way into the model, the write path.
Applying it writes its own operations onto the model as it stands now. Whether that is allowed is
decided here from facts already computed elsewhere — the candidate's state, the stack beneath it, and
each operation's standing — so nothing about operations is judged a second time:

* a terminal candidate is a record of what happened, and is not applied again;
* a candidate read on top of another needs that one integrated first, or its operations would name
  what the model does not hold;
* a `conflicting` operation has nothing to apply to, and its own reason is the refusal;
* a `drifted` operation would overwrite what someone wrote since, and the candidate is re-based
  first — that is the operation that writes it again against the model as it stands now;
* an `already-there` operation is skipped: the model already says it.

**Pure.** The write itself is the transport's, in one staged transaction; this decides what goes in.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from src.application.change_sets.candidate_architecture import CandidateArchitecture, CandidateState
from src.application.change_sets.candidate_reads import CandidateLookup, live_reading
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.operations import CreateEntity
from src.application.change_sets.stacking import sets_beneath, stack_of
from src.application.change_sets.standing import OperationStanding, standing_of
from src.application.verification.artifact_verifier_registry import ArtifactRegistry

#: Where a candidate is once its operations are in the model.
INTEGRATED: CandidateState = "integrated"

#: The states a candidate stays in for good. Applying one would repeat or contradict what happened.
TERMINAL: frozenset[CandidateState] = frozenset({"integrated", "rejected", "superseded"})


@dataclass(frozen=True, slots=True)
class Application:
    """What applying a candidate would write, and why it would not, if it would not."""

    candidate: CandidateArchitecture
    standing: tuple[OperationStanding, ...]
    #: The operations to write: everything that applies, nothing already there.
    applying: ChangeSet
    #: The creates the model already holds that `applying` may still name by alias — the stack's
    #: beneath it, and the candidate's own that were already there.
    named: ChangeSet
    #: The id each alias in the stack was given in advance, so a reference can be written as an id.
    ids: Mapping[str, str]
    refusal: str | None = None

    @property
    def integrated(self) -> CandidateArchitecture:
        """The candidate as it stands once its operations are in the model."""
        return replace(self.candidate, state=INTEGRATED)


def application_of(
    candidate: CandidateArchitecture, store: CandidateLookup, registry: ArtifactRegistry,
) -> Application:
    """Applying *candidate* to the model as it stands now, judged against the live records."""
    stack = stack_of(candidate, store.find)
    standing = standing_of(candidate.changes, live_reading(stack, registry), beneath=sets_beneath(stack))
    return judged(candidate, stack, standing)


def judged(
    candidate: CandidateArchitecture,
    stack: Sequence[CandidateArchitecture],
    standing: Sequence[OperationStanding],
) -> Application:
    """The application, refused in a sentence where the state, the stack or a standing forbids it."""
    revision = candidate.changes.repository_revision
    applying = tuple(item.operation for item in standing if item.standing != "already-there")
    present = tuple(
        item.operation for item in standing
        if item.standing == "already-there" and isinstance(item.operation, CreateEntity)
    )
    lower = tuple(create for layer in stack[:-1] for create in layer.changes.created.values())
    ids = {
        create.ref: create.artifact_id
        for layer in stack for create in layer.changes.created.values() if create.artifact_id
    }
    return Application(
        candidate=candidate,
        standing=tuple(standing),
        applying=ChangeSet(applying, revision),
        named=ChangeSet((*lower, *present), revision),
        ids=ids,
        refusal=_refusal(candidate, stack, standing),
    )


def _refusal(
    candidate: CandidateArchitecture,
    stack: Sequence[CandidateArchitecture],
    standing: Sequence[OperationStanding],
) -> str | None:
    if candidate.state in TERMINAL:
        return f"{candidate.id} is {candidate.state}, so it is not applied again. Start a new candidate."
    if candidate.target_state is not None:
        return (
            f"{candidate.id} is in the model as a target state, so it is applied by moving that into the "
            "baseline (candidate_move_into_baseline)."
        )
    pending = [layer.id for layer in stack[:-1] if layer.state != INTEGRATED]
    if pending:
        return (
            f"{candidate.id} is read on top of {', '.join(pending)}, which "
            f"{'is' if len(pending) == 1 else 'are'} not integrated. Apply "
            f"{'it' if len(pending) == 1 else 'them'} first."
        )
    if not candidate.changes.operations:
        return f"{candidate.id} has no operations, so there is nothing to apply."
    conflicting = [item.reason for item in standing if item.standing == "conflicting"]
    if conflicting:
        return f"{candidate.id} cannot be applied: {' '.join(conflicting)}"
    drifted = [item.reason for item in standing if item.standing == "drifted"]
    if drifted:
        return (
            f"{candidate.id} cannot be applied until it is re-based: the model changed under "
            f"{_count(len(drifted))} since {'it was' if len(drifted) == 1 else 'they were'} written. "
            f"{' '.join(drifted)}"
        )
    return None


def _count(drifted: int) -> str:
    return "one of its operations" if drifted == 1 else f"{drifted} of its operations"
