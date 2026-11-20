"""The candidate architecture: the header only content has, around the change set everything shares.

What is tested here is what the header adds — its refusals, its lifecycle, which candidate is read on
top of which, and that the work done with candidates asks the header's questions and then hands the
operations to the change set's own functions.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import yaml
from hypothesis import given

from src.application.change_sets import candidate_recorded_form, candidate_work, recorded_form
from src.application.change_sets.base import BaseRevision
from src.application.change_sets.candidate_architecture import (
    CANDIDATE_STATES,
    CandidateArchitecture,
    MalformedCandidateArchitecture,
    beneath,
)
from src.application.change_sets.composition import compose
from src.application.change_sets.operations import AddConnection, MalformedChangeSet, RemoveEntity
from src.application.change_sets.reading import RecordedReading
from tests.support.change_sets import candidate, candidates, change_set, create, edit, joins

_REVISION = BaseRevision("0123456789abcdef")
_A = "ENT@1.a"
_B = "ENT@1.b"


class TestTheHeader:
    @pytest.mark.parametrize(
        ("header", "fault"),
        [
            pytest.param({"id": ""}, "has an id", id="no-id"),
            pytest.param({"name": ""}, "has no name", id="no-name"),
            pytest.param({"state": "approved"}, "not a state", id="unknown-state"),
            pytest.param({"state": "abandoned"}, "not a state", id="a-coordination-state"),
            pytest.param({"parent_id": "CA-1"}, "itself as its parent", id="own-parent"),
            pytest.param({"answers": ("row-1", "")}, "empty reference", id="empty-reference"),
            pytest.param({"satisfies": ("REQ@1.a", "REQ@1.a")}, "twice", id="repeated-reference"),
        ],
    )
    def test_each_fault_is_refused_by_name(self, header: dict[str, Any], fault: str) -> None:
        with pytest.raises(MalformedCandidateArchitecture, match=fault):
            candidate(**header)

    def test_the_refusal_of_a_state_lists_the_states(self) -> None:
        with pytest.raises(MalformedCandidateArchitecture) as refusal:
            candidate(state="approved")
        assert all(state in str(refusal.value) for state in CANDIDATE_STATES)

    @pytest.mark.parametrize("state", CANDIDATE_STATES)
    def test_every_state_is_one_a_candidate_can_be_in(self, state: str) -> None:
        assert candidate(state=state).state == state

    def test_the_lifecycle_is_the_works(self) -> None:
        assert set(CANDIDATE_STATES) == {"draft", "candidate", "integrated", "rejected", "superseded"}

    def test_a_reference_nothing_creates_is_refused_where_there_is_no_parent(self) -> None:
        with pytest.raises(MalformedCandidateArchitecture, match=r"\$ref:queue, which nothing in it creates"):
            candidate(AddConnection(joins(_A, "$ref:queue"), {}))

    def test_with_a_parent_the_reference_may_be_the_parents(self) -> None:
        child = candidate(AddConnection(joins(_A, "$ref:queue"), {}), parent_id="CA-0")
        assert child.parent_id == "CA-0"

    def test_what_it_proposes_is_a_change_set_usable_without_the_header(self) -> None:
        proposing = candidate(edit(_A, "name", "Invoicing"))
        composed = compose(proposing.changes, RecordedReading(entities={_A: {"name": "Billing"}}))
        assert composed.entity(_A) == {"name": "Invoicing"}


class TestWhichCandidateIsBeneath:
    def test_a_candidate_alone_is_read_on_nothing(self) -> None:
        assert beneath(candidate(), None) is None

    def test_a_child_is_read_on_its_parents_change_set(self) -> None:
        parent = candidate(create("queue"), id="CA-0")
        assert beneath(candidate(parent_id="CA-0"), parent) == parent.changes

    def test_a_child_cannot_be_read_without_its_parent(self) -> None:
        with pytest.raises(MalformedCandidateArchitecture, match="none was given"):
            beneath(candidate(parent_id="CA-0"), None)

    def test_the_parent_must_be_the_one_the_candidate_names(self) -> None:
        with pytest.raises(MalformedCandidateArchitecture, match="'CA-9' was given"):
            beneath(candidate(parent_id="CA-0"), candidate(id="CA-9"))

    def test_a_candidate_without_a_parent_is_not_given_one(self) -> None:
        with pytest.raises(MalformedCandidateArchitecture, match="has no parent"):
            beneath(candidate(), candidate(id="CA-0"))

    def test_three_layers_are_refused_with_what_to_do(self) -> None:
        middle = candidate(id="CA-0", parent_id="CA-root")
        with pytest.raises(MalformedCandidateArchitecture, match="two deep for now"):
            beneath(candidate(parent_id="CA-0"), middle)


class TestOverlapBetweenCandidates:
    def test_parties_are_named_by_candidate_id(self) -> None:
        (found,) = candidate_work.conflicts_between(
            [candidate(edit(_A, "name", "x"), id="CA-1"), candidate(edit(_A, "name", "y"), id="CA-2")]
        )
        assert [party.set_id for party in found.parties] == ["CA-1", "CA-2"]

    def test_a_child_and_its_parent_are_stacked_not_overlapping(self) -> None:
        parent = candidate(edit(_A, "name", "Invoicing"), id="CA-0")
        child = candidate(edit(_A, "name", "Invoices"), id="CA-1", parent_id="CA-0")
        assert candidate_work.overlaps_between([parent, child]) == ()

    def test_two_children_of_one_parent_overlap_on_its_entity(self) -> None:
        parent = candidate(create("queue"), id="CA-0")
        children = [
            candidate(edit("$ref:queue", "name", name), id=f"CA-{n}", parent_id="CA-0")
            for n, name in enumerate(("Queue", "Topic"), start=1)
        ]
        (found,) = candidate_work.conflicts_between([parent, *children])
        assert [party.set_id for party in found.parties] == ["CA-1", "CA-2"]

    def test_a_candidate_given_twice_is_refused(self) -> None:
        same = candidate(edit(_A, "name", "x"))
        with pytest.raises(MalformedCandidateArchitecture, match="given twice"):
            candidate_work.overlaps_between([same, same])


class TestSplittingAndMergingCandidates:
    def test_a_split_makes_a_sibling_of_the_same_work(self) -> None:
        rename, retag = edit(_A, "name", "x"), edit(_B, "status", "active")
        original = candidate(rename, retag, answers=("row-1",), satisfies=("REQ@1.a",), parent_id="CA-0")

        staying, leaving = candidate_work.split(original, {retag.claim}, id="CA-2", name="the status change")

        assert (staying.id, staying.changes.operations) == (original.id, (rename,))
        assert (leaving.id, leaving.name, leaving.changes.operations) == ("CA-2", "the status change", (retag,))
        assert (leaving.parent_id, leaving.answers, leaving.satisfies) == ("CA-0", ("row-1",), ("REQ@1.a",))

    def test_a_split_refuses_what_the_change_set_refuses(self) -> None:
        queue, link = create("queue"), AddConnection(joins(_A, "$ref:queue"), {})
        with pytest.raises(MalformedChangeSet, match="Move both, or neither"):
            candidate_work.split(candidate(queue, link), {queue.claim}, id="CA-2", name="n")

    def test_a_merge_joins_the_operations_and_what_both_answer_each_once(self) -> None:
        rename, retag = edit(_A, "name", "x"), edit(_B, "status", "active")
        first = candidate(rename, id="CA-1", answers=("row-1", "row-2"), satisfies=("REQ@1.a",))
        second = candidate(retag, id="CA-2", answers=("row-2", "row-3"), satisfies=("REQ@1.a",))

        merged = candidate_work.merge(first, second, id="CA-3", name="both")

        assert (merged.id, merged.name, merged.state) == ("CA-3", "both", "draft")
        assert set(merged.changes.by_claim) == {rename.claim, retag.claim}
        assert (merged.answers, merged.satisfies) == (("row-1", "row-2", "row-3"), ("REQ@1.a",))

    def test_a_merge_refuses_what_the_change_set_refuses(self) -> None:
        with pytest.raises(MalformedChangeSet, match="disagree about name"):
            candidate_work.merge(
                candidate(edit(_A, "name", "x"), id="CA-1"), candidate(edit(_A, "name", "y"), id="CA-2"),
                id="CA-3", name="both",
            )

    def test_candidates_on_different_parents_are_not_merged(self) -> None:
        with pytest.raises(MalformedCandidateArchitecture, match="different candidates"):
            candidate_work.merge(candidate(id="CA-1", parent_id="CA-0"), candidate(id="CA-2"), id="CA-3", name="b")

    def test_a_candidate_is_not_merged_into_the_one_it_is_read_on_top_of(self) -> None:
        """That would cut every dependency of the child on its parent at once."""
        with pytest.raises(MalformedCandidateArchitecture, match="different candidates"):
            candidate_work.merge(candidate(id="CA-0"), candidate(id="CA-1", parent_id="CA-0"), id="CA-3", name="b")

    def test_a_candidate_is_not_merged_with_itself(self) -> None:
        with pytest.raises(MalformedCandidateArchitecture, match="with itself"):
            candidate_work.merge(candidate(), candidate(), id="CA-3", name="both")

    @pytest.mark.parametrize("state", [state for state in CANDIDATE_STATES if state != "draft"])
    def test_only_drafts_are_split_or_merged(self, state: str) -> None:
        with pytest.raises(MalformedCandidateArchitecture, match="only a draft"):
            candidate_work.split(candidate(state=state), set(), id="CA-2", name="n")
        with pytest.raises(MalformedCandidateArchitecture, match="only a draft"):
            candidate_work.merge(candidate(id="CA-1"), candidate(id="CA-2", state=state), id="CA-3", name="b")

    def test_a_child_removing_its_parents_entity_is_a_candidate_that_can_exist(self) -> None:
        child = candidate(RemoveEntity("$ref:queue", _REVISION), parent_id="CA-0")
        assert len(child.changes.operations) == 1


class TestTheRecordedForm:
    @given(candidates())
    def test_every_candidate_survives_being_written_down_and_read_back(
        self, generated: CandidateArchitecture
    ) -> None:
        recorded = candidate_recorded_form.to_mapping(generated)
        assert candidate_recorded_form.from_mapping(recorded) == generated
        assert candidate_recorded_form.from_mapping(yaml.safe_load(yaml.safe_dump(recorded))) == generated
        assert candidate_recorded_form.from_mapping(json.loads(json.dumps(recorded))) == generated

    def test_the_change_set_is_recorded_whole_and_separably(self) -> None:
        """A reader that wants only the operations takes `changes` and needs nothing else."""
        proposing = candidate(edit(_A, "name", "x"), parent_id="CA-0")
        recorded = candidate_recorded_form.to_mapping(proposing)
        assert recorded["changes"] == recorded_form.to_mapping(proposing.changes)
        assert recorded_form.from_mapping(recorded["changes"]) == proposing.changes
        assert recorded["parent"] == "CA-0"

    def test_an_absent_parent_and_empty_links_are_left_out(self) -> None:
        assert set(candidate_recorded_form.to_mapping(candidate())) == {"id", "name", "state", "changes"}

    @pytest.mark.parametrize("key", ["id", "name", "state", "changes"])
    def test_a_missing_key_is_named(self, key: str) -> None:
        recorded = candidate_recorded_form.to_mapping(candidate())
        del recorded[key]
        with pytest.raises(MalformedCandidateArchitecture, match=f"missing.*{key}"):
            candidate_recorded_form.from_mapping(recorded)

    def test_a_key_the_form_does_not_define_is_refused_not_ignored(self) -> None:
        recorded = {**candidate_recorded_form.to_mapping(candidate()), "owner": "someone"}
        with pytest.raises(MalformedCandidateArchitecture, match="does not define"):
            candidate_recorded_form.from_mapping(recorded)

    def test_what_the_change_set_refuses_the_reader_refuses(self) -> None:
        recorded = {**candidate_recorded_form.to_mapping(candidate()), "changes": ["not", "a", "set"]}
        with pytest.raises(MalformedChangeSet, match="is a mapping"):
            candidate_recorded_form.from_mapping(recorded)

    def test_what_the_header_refuses_the_reader_refuses(self) -> None:
        recorded = {**candidate_recorded_form.to_mapping(candidate()), "state": "abandoned"}
        with pytest.raises(MalformedCandidateArchitecture, match="not a state"):
            candidate_recorded_form.from_mapping(recorded)


def test_a_change_set_from_the_builder_is_what_a_candidate_holds() -> None:
    changes = change_set(edit(_A, "name", "x"))
    assert candidate(changes=changes).changes is changes
