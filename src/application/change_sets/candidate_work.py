"""What is done with candidate architectures as candidates: compared, split and merged.

Each of these is the change set's function with the questions only a candidate can answer asked
first. Whether operations overlap is decided over change sets; *which* candidate is read on top of
which, and whether a candidate is still its author's to rearrange, are facts about the header. So
this module asks those and hands the operations down — it holds no rule about operations itself.

**Only drafts are rearranged.** A candidate has been offered for integration as it stands, and a
terminal one is a record of what happened. Splitting or merging either would change what was offered
or rewrite what was done.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import replace

from src.application.change_sets import partition
from src.application.change_sets.candidate_architecture import (
    DRAFT,
    CandidateArchitecture,
    MalformedCandidateArchitecture,
)
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.operations import OperationKey
from src.application.change_sets.overlap import Overlap, conflicts, overlaps


def overlaps_between(candidates: Sequence[CandidateArchitecture]) -> tuple[Overlap, ...]:
    """Every overlap between the candidates' change sets, each party named by its candidate's id."""
    sets, stacked_on = _named(candidates)
    return overlaps(sets, stacked_on=stacked_on)


def conflicts_between(candidates: Sequence[CandidateArchitecture]) -> tuple[Overlap, ...]:
    """The overlaps between the candidates that need a decision."""
    sets, stacked_on = _named(candidates)
    return conflicts(sets, stacked_on=stacked_on)


def split(
    candidate: CandidateArchitecture,
    moved: Collection[OperationKey],
    *,
    id: str,  # noqa: A002 — the new candidate's id, named as the value names it
    name: str,
    rationale: str = "",
    description: str = "",
) -> tuple[CandidateArchitecture, CandidateArchitecture]:
    """*candidate* without the operations *moved* names, and a new sibling holding them.

    The sibling keeps the parent and what the original answers and satisfies: it is part of the same
    work until its author says otherwise.
    """
    _must_be_draft(candidate, "split")
    staying, leaving = partition.split(candidate.changes, moved)
    return (
        replace(candidate, changes=staying),
        replace(candidate, id=id, name=name, rationale=rationale, description=description, changes=leaving),
    )


def merge(
    first: CandidateArchitecture,
    second: CandidateArchitecture,
    *,
    id: str,  # noqa: A002 — the merged candidate's id, named as the value names it
    name: str,
    rationale: str = "",
    description: str = "",
) -> CandidateArchitecture:
    """One draft candidate proposing what both did, answering and satisfying what either did."""
    for candidate in (first, second):
        _must_be_draft(candidate, "merged")
    if first.id == second.id:
        raise MalformedCandidateArchitecture(f"'{first.id}' cannot be merged with itself")
    if first.parent_id != second.parent_id:
        raise MalformedCandidateArchitecture(
            f"'{first.id}' and '{second.id}' are read on top of different candidates "
            f"({first.parent_id or 'none'} and {second.parent_id or 'none'}), so one merged "
            "candidate could not be read on top of both. Merge candidates that share a parent."
        )
    return replace(
        first,
        id=id,
        name=name,
        rationale=rationale,
        description=description,
        changes=partition.merge(first.changes, second.changes),
        answers=_union(first.answers, second.answers),
        satisfies=_union(first.satisfies, second.satisfies),
    )


def _named(
    candidates: Sequence[CandidateArchitecture],
) -> tuple[dict[str, ChangeSet], dict[str, str]]:
    """The candidates' change sets by id, and which is read on top of which."""
    sets = {candidate.id: candidate.changes for candidate in candidates}
    if len(sets) != len(candidates):
        raise MalformedCandidateArchitecture(
            "the same candidate architecture was given twice. A candidate cannot overlap itself, "
            "and counting it twice would report every operation it has."
        )
    stacked_on = {c.id: c.parent_id for c in candidates if c.parent_id is not None}
    return sets, stacked_on


def _must_be_draft(candidate: CandidateArchitecture, action: str) -> None:
    if candidate.state != DRAFT:
        raise MalformedCandidateArchitecture(
            f"'{candidate.id}' is {candidate.state}, and only a draft can be {action}: its "
            "operations are no longer its author's to rearrange."
        )


def _union(first: tuple[str, ...], second: tuple[str, ...]) -> tuple[str, ...]:
    """Both, in order, each once."""
    return tuple(dict.fromkeys((*first, *second)))
