"""Split and merge rearrange operations between change sets, and refuse to cut a dependency."""

from __future__ import annotations

import pytest
from hypothesis import given

from src.application.change_sets.base import BaseRevision
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.operations import (
    AddConnection,
    MalformedChangeSet,
    RemoveConnection,
    RemoveEntity,
)
from src.application.change_sets.partition import merge, split
from tests.support.change_sets import change_set, change_sets, create, edit, joins

_REVISION = BaseRevision("0123456789abcdef")
_A = "ENT@1.a"
_B = "ENT@1.b"


class TestSplit:
    def test_the_named_operations_move_and_the_rest_stay(self) -> None:
        rename, retag = edit(_A, "name", "x"), edit(_B, "status", "active")

        staying, leaving = split(change_set(rename, retag), {retag.claim})

        assert staying.operations == (rename,)
        assert leaving.operations == (retag,)

    def test_both_halves_are_written_against_what_the_original_was(self) -> None:
        original = change_set(edit(_A, "name", "x"), repository_revision="rev-7")
        staying, leaving = split(original, set())
        assert (staying.repository_revision, leaving.repository_revision) == ("rev-7", "rev-7")

    def test_a_create_and_what_uses_it_cannot_be_separated(self) -> None:
        queue, link = create("queue"), AddConnection(joins(_A, "$ref:queue"), {})
        original = change_set(queue, link)

        for moved in ({queue.claim}, {link.claim}):
            with pytest.raises(MalformedChangeSet, match="Move both, or neither"):
                split(original, moved)

    def test_they_may_move_together(self) -> None:
        queue, link, other = create("queue"), AddConnection(joins(_A, "$ref:queue"), {}), edit(_B, "name", "y")
        staying, leaving = split(change_set(queue, link, other), {queue.claim, link.claim})
        assert (len(staying.operations), len(leaving.operations)) == (1, 2)

    def test_an_entity_removal_cannot_leave_its_connection_removals_behind(self) -> None:
        entity, connection = RemoveEntity(_A, _REVISION), RemoveConnection(joins(_A, _B), _REVISION)
        with pytest.raises(MalformedChangeSet, match="Move both, or neither"):
            split(change_set(entity, connection), {entity.claim})

    def test_a_use_of_what_a_lower_set_creates_may_go_to_either_half(self) -> None:
        """That dependency is on another set, and a split of this one does not cut it."""
        link, other = AddConnection(joins(_A, "$ref:queue"), {}), edit(_B, "name", "y")
        _, leaving = split(change_set(link, other), {link.claim})
        assert leaving.operations == (link,)

    def test_an_operation_the_set_does_not_have_cannot_be_moved(self) -> None:
        with pytest.raises(MalformedChangeSet, match="nothing there to move"):
            split(change_set(), {edit(_A, "name", "x").claim})

    @given(change_sets())
    def test_splitting_along_a_cut_no_dependency_crosses_and_merging_gives_the_set_back(
        self, generated: ChangeSet
    ) -> None:
        """Nothing is lost or invented. Entity edits depend on nothing in a generated set."""
        independent = {
            op.claim for op in generated.operations if op.claim.kind == "entity" and op.claim.field
        }
        staying, leaving = split(generated, independent)

        assert merge(staying, leaving) == generated


class TestMerge:
    def test_the_merged_set_holds_the_operations_of_both(self) -> None:
        rename, retag = edit(_A, "name", "x"), edit(_B, "status", "active")
        merged = merge(change_set(rename), change_set(retag))
        assert set(merged.by_claim) == {rename.claim, retag.claim}

    def test_operations_that_converge_are_kept_once(self) -> None:
        merged = merge(change_set(edit(_A, "name", "x")), change_set(edit(_A, "name", "x")))
        assert len(merged.operations) == 1

    def test_operations_that_disagree_are_refused_naming_the_key(self) -> None:
        with pytest.raises(MalformedChangeSet, match="disagree about name of ENT@1.a"):
            merge(change_set(edit(_A, "name", "x")), change_set(edit(_A, "name", "y")))

    def test_the_refusal_says_how_many_more_there_are(self) -> None:
        first = change_set(edit(_A, "name", "x"), edit(_B, "name", "x"))
        second = change_set(edit(_A, "name", "y"), edit(_B, "name", "y"))
        with pytest.raises(MalformedChangeSet, match="and 1 more"):
            merge(first, second)

    def test_a_removal_and_a_use_are_refused(self) -> None:
        with pytest.raises(MalformedChangeSet, match="disagree"):
            merge(change_set(RemoveEntity(_A, _REVISION)), change_set(edit(_A, "name", "y")))

    def test_two_entities_under_one_alias_are_refused(self) -> None:
        with pytest.raises(MalformedChangeSet, match="each create an entity called"):
            merge(change_set(create("queue")), change_set(create("queue")))

    def test_an_alias_is_not_silently_rebound_to_the_other_sets_entity(self) -> None:
        """One names `$ref:queue` from the set beneath it; the other creates its own. Merged, the
        first would come to mean the second's entity."""
        uses_the_lower = change_set(AddConnection(joins(_A, "$ref:queue"), {}))
        creates_its_own = change_set(create("queue"))
        for first, second in ((uses_the_lower, creates_its_own), (creates_its_own, uses_the_lower)):
            with pytest.raises(MalformedChangeSet, match="would mean the new entity"):
                merge(first, second)

    def test_sets_written_against_different_revisions_are_refused(self) -> None:
        with pytest.raises(MalformedChangeSet, match="records one revision"):
            merge(change_set(), change_set(repository_revision="rev-2"))
