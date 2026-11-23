"""A candidate is read on top of its parent, which may have one of its own, to any depth.

The owner's answer to question 38: any stacking depth, with a cycle check, and a diff base that
excludes the candidate and its descendants. The stack is read once (`stack_of`) and composed as
layers (`compose(..., beneath=...)`), so every layer may name what any layer under it creates.
"""

from __future__ import annotations

import pytest

from src.application.change_sets.candidate_architecture import (
    CandidateArchitecture,
    MalformedCandidateArchitecture,
)
from src.application.change_sets.composition import compose
from src.application.change_sets.operations import AddConnection
from src.application.change_sets.reading import RecordedReading
from src.application.change_sets.stacking import descendants, sets_beneath, stack_of
from tests.support.change_sets import candidate, create, edit, joins

_A = "ENT@1.a"
_MODEL = RecordedReading(entities={_A: {"name": "Billing", "artifact_type": "application-component"}})


def _finder(*held: CandidateArchitecture):
    by_id = {each.id: each for each in held}
    return by_id.get


class TestTheStack:
    def test_a_candidate_without_a_parent_is_its_own_stack(self) -> None:
        alone = candidate()
        assert stack_of(alone, _finder()) == (alone,)

    def test_a_stack_three_deep_is_read_lowest_first(self) -> None:
        naive = candidate(create("queue"), id="CA-naive")
        adaptation = candidate(edit("$ref:queue", "name", "Queue"), id="CA-adapt", parent_id="CA-naive")
        top = candidate(
            AddConnection(joins(_A, "$ref:queue"), {}), id="CA-top", parent_id="CA-adapt"
        )
        stack = stack_of(top, _finder(naive, adaptation))
        assert [layer.id for layer in stack] == ["CA-naive", "CA-adapt", "CA-top"]

    def test_the_top_may_name_what_any_layer_beneath_creates(self) -> None:
        naive = candidate(create("queue", name="Queue"), id="CA-naive")
        middle = candidate(edit(_A, "name", "Invoicing"), id="CA-mid", parent_id="CA-naive")
        top = candidate(AddConnection(joins(_A, "$ref:queue"), {}), id="CA-top", parent_id="CA-mid")
        stack = stack_of(top, _finder(naive, middle))

        composed = compose(top.changes, _MODEL, beneath=sets_beneath(stack))

        assert composed.connection(joins(_A, "$ref:queue")) == {}
        assert composed.entity(_A)["name"] == "Invoicing"  # type: ignore[index]
        assert composed.unapplied == ()

    def test_a_missing_parent_is_refused_with_what_to_do(self) -> None:
        orphan = candidate(id="CA-1", parent_id="CA-gone")
        with pytest.raises(MalformedCandidateArchitecture, match="'CA-gone', which does not exist"):
            stack_of(orphan, _finder())

    def test_a_circle_is_refused_naming_it(self) -> None:
        first = candidate(id="CA-1", parent_id="CA-2")
        second = candidate(id="CA-2", parent_id="CA-1")
        with pytest.raises(MalformedCandidateArchitecture, match="CA-1 → CA-2 → CA-1"):
            stack_of(first, _finder(first, second))

    def test_an_alias_created_twice_in_one_stack_is_refused(self) -> None:
        lower = candidate(create("queue"), id="CA-1")
        upper = candidate(create("queue"), id="CA-2", parent_id="CA-1")
        with pytest.raises(MalformedCandidateArchitecture, match=r"\$ref:queue is created by more"):
            stack_of(upper, _finder(lower))


class TestDescendants:
    def test_every_candidate_stacked_on_one_at_any_depth(self) -> None:
        held = [
            candidate(id="CA-naive"),
            candidate(id="CA-a", parent_id="CA-naive"),
            candidate(id="CA-b", parent_id="CA-a"),
            candidate(id="CA-other"),
        ]
        assert descendants("CA-naive", held) == {"CA-a", "CA-b"}
        assert descendants("CA-b", held) == frozenset()
