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

**A candidate may be read on top of a parent**, which may have one of its own, to any depth: the naive
architecture started from an existing candidate, then adaptations of it, then a candidate built on
an adaptation. Which candidates a stack holds, and that it is not a circle, is `stacking`'s.

**Its scope is what it reads live.** `scope` names, by stable id, the model's entities the candidate is drawn over
without changing them: a naive architecture started from the current model within a scope copies
nothing, and the model's later changes show through. A candidate started empty has none.

**What `answers` and `satisfies` hold is opaque here.** They are references whose form is decided by
whoever stores a candidate. The value only keeps them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias, get_args

from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.coherence import dangling
from src.domain.artifact_id import canonical_entity_key

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
    #: The model's entities the candidate is read over without changing them, by id.
    scope: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # The model's entities by their stable id, as operations name them (`operations`).
        object.__setattr__(self, "scope", tuple(canonical_entity_key(ref) for ref in self.scope))
        refusal = _refusal(self)
        if refusal is not None:
            raise MalformedCandidateArchitecture(refusal)


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
    for label, references in (
        ("answers", candidate.answers), ("satisfies", candidate.satisfies), ("reads over", candidate.scope)
    ):
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
