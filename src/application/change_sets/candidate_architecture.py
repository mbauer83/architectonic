"""The candidate architecture: an authored, named candidate change to the architecture.

Content, where a change set is mechanism. A person or an agent writes one deliberately, as part of
the work: it has a name a reader can tell from its siblings, a rationale, the end states it answers
and the requirements it satisfies, and a place in the work — drafted, offered, integrated, rejected
or superseded. An adaptation in a stress analysis is one.

**It holds a change set; it is not one.** What it proposes is `changes`, the same operation value a
diagram edit session and a proposed change use. Everything that reads operations — standing,
composition, overlap, order — takes the change set, so none of it needs a name or a work state to
run, and nothing here is restated there.

**This lifecycle is the work's, not the mechanism's.** `rejected` is a considered alternative that
lost and is kept as one. A proposed change's coordination states (`proposed_change`) are a different
vocabulary about a different thing and are not touched.

**Stacking is depth two.** A candidate may be read on top of one parent — the naive architecture,
then an adaptation of it. A parent that itself has a parent is refused: three layers is a history,
and a history needs decisions about rebasing the middle that have not been made.

**What `answers` and `satisfies` hold is opaque here.** They are references whose form is decided by
whoever stores a candidate. The value only keeps them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias, get_args

from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.coherence import dangling

#: Where a candidate is in the work. `draft` is the only state in which its operations may change;
#: `candidate` offers it for integration; the other three are terminal.
CandidateState: TypeAlias = Literal["draft", "candidate", "integrated", "rejected", "superseded"]

#: The closed set, so a refusal lists the states rather than restating them as strings.
CANDIDATE_STATES: tuple[CandidateState, ...] = get_args(CandidateState)

#: The state a candidate is written in, and the only one whose operations are its author's to change.
DRAFT: CandidateState = "draft"


class MalformedCandidateArchitecture(ValueError):
    """A candidate architecture that cannot exist as stated. The message says why."""


@dataclass(frozen=True, slots=True)
class CandidateArchitecture:
    """A header, and the change set it proposes. Refuses to exist malformed."""

    id: str
    name: str
    rationale: str
    state: CandidateState
    changes: ChangeSet
    parent_id: str | None = None
    #: What the candidate answers and what it satisfies, as references whose form the store decides.
    answers: tuple[str, ...] = ()
    satisfies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        refusal = _refusal(self)
        if refusal is not None:
            raise MalformedCandidateArchitecture(refusal)


def beneath(
    candidate: CandidateArchitecture, parent: CandidateArchitecture | None
) -> ChangeSet | None:
    """The change set *candidate* is read on top of: its parent's, or None where it has no parent.

    Refuses a parent that is not the one the candidate names, a candidate whose parent was not
    supplied, and a stack deeper than two.
    """
    if candidate.parent_id is None:
        if parent is not None:
            raise MalformedCandidateArchitecture(
                f"'{candidate.id}' has no parent, and '{parent.id}' was given as one"
            )
        return None
    if parent is None or parent.id != candidate.parent_id:
        given = "none was given" if parent is None else f"'{parent.id}' was given"
        raise MalformedCandidateArchitecture(
            f"'{candidate.id}' is read on top of '{candidate.parent_id}', and {given}. A candidate "
            "cannot be read without the one beneath it."
        )
    if parent.parent_id is not None:
        raise MalformedCandidateArchitecture(
            f"'{candidate.id}' is stacked on '{parent.id}', which is itself stacked on "
            f"'{parent.parent_id}'. Candidates stack two deep for now: integrate or merge the lower "
            "two first."
        )
    return parent.changes


def _refusal(candidate: CandidateArchitecture) -> str | None:
    if not candidate.id:
        return "a candidate architecture has an id"
    if not candidate.name:
        return (
            f"candidate architecture '{candidate.id}' has no name. It is named so a reader can tell "
            "it from its siblings."
        )
    if candidate.state not in CANDIDATE_STATES:
        return (
            f"{candidate.state!r} is not a state a candidate architecture can be in. "
            f"The states are {', '.join(CANDIDATE_STATES)}."
        )
    if candidate.parent_id == candidate.id:
        return f"candidate architecture '{candidate.id}' names itself as its parent"
    for label, references in (("answers", candidate.answers), ("satisfies", candidate.satisfies)):
        if any(not reference for reference in references):
            return f"candidate architecture '{candidate.id}' has an empty reference among what it {label}"
        if len(set(references)) != len(references):
            return f"candidate architecture '{candidate.id}' names the same thing twice among what it {label}"
    if candidate.parent_id is None:
        unresolved = dangling(candidate.changes.operations, frozenset())
        if unresolved:
            return (
                f"candidate architecture '{candidate.id}' names {', '.join(unresolved)}, which "
                "nothing in it creates, and it has no parent that could. Add the create, or name "
                "the entity by its id."
            )
    return None
