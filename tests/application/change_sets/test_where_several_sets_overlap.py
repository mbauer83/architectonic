"""Overlap between N sets: same key with different values, and remove versus use.

The sets are named by the caller — a change set has no identity of its own — and every party is
reported under that name.
"""

from __future__ import annotations

import pytest

from src.application.change_sets.base import BaseRevision
from src.application.change_sets.operations import (
    AddConnection,
    Operation,
    RemoveConnection,
    RemoveEntity,
)
from src.application.change_sets.overlap import conflicts, overlaps
from tests.support.change_sets import change_set, create, edit, edit_connection, joins

_REVISION = BaseRevision("0123456789abcdef")
_A = "ENT@1.a"
_B = "ENT@1.b"
_LINK = joins(_A, _B)


def _each(**operations: Operation) -> dict:
    """One single-operation set per name."""
    return {name: change_set(operation) for name, operation in operations.items()}


class TestSameKey:
    def test_two_sets_asking_one_key_for_different_values_conflict(self) -> None:
        ours, theirs = edit(_A, "name", "Invoicing"), edit(_A, "name", "Payments")

        (found,) = overlaps(_each(S1=ours, S2=theirs))

        assert found.kind == "same-key"
        assert not found.convergent
        assert [(party.set_id, party.operation) for party in found.parties] == [("S1", ours), ("S2", theirs)]
        assert "name of ENT@1.a" in found.subject

    def test_equal_values_converge_and_are_not_a_conflict(self) -> None:
        sets = _each(S1=edit(_A, "name", "Invoicing"), S2=edit(_A, "name", "Invoicing"))

        (found,) = overlaps(sets)

        assert found.convergent
        assert conflicts(sets) == ()

    def test_convergence_ignores_what_each_was_written_against(self) -> None:
        early = edit(_A, "name", "Invoicing", was="Billing")
        late = edit(_A, "name", "Invoicing", was="Payments")
        assert conflicts(_each(S1=early, S2=late)) == ()

    def test_two_keys_of_one_field_do_not_overlap(self) -> None:
        """The point of addressing a key: two sets may each set a different attribute."""
        sets = _each(
            S1=edit(_A, "properties", "gold", key="tier"), S2=edit(_A, "properties", "eu", key="region")
        )
        assert overlaps(sets) == ()

    def test_one_key_of_one_field_does(self) -> None:
        sets = _each(
            S1=edit(_A, "properties", "gold", key="tier"), S2=edit(_A, "properties", "platinum", key="tier")
        )
        assert len(conflicts(sets)) == 1

    def test_three_sets_on_one_key_are_one_overlap_with_three_parties(self) -> None:
        sets = {f"S{n}": change_set(edit(_A, "name", value)) for n, value in enumerate("xyx")}
        (found,) = overlaps(sets)
        assert [party.set_id for party in found.parties] == ["S0", "S1", "S2"]
        assert not found.convergent

    def test_the_two_sets_need_not_be_adjacent(self) -> None:
        sets = _each(S1=edit(_A, "name", "x"), S2=edit(_B, "name", "y"), S3=edit(_A, "name", "z"))
        assert [p.set_id for p in conflicts(sets)[0].parties] == ["S1", "S3"]

    def test_two_sets_adding_one_connection_converge_only_if_they_state_the_same(self) -> None:
        calls = AddConnection(_LINK, {"description": "calls"})
        assert conflicts(_each(S1=calls, S2=calls)) == ()
        assert len(conflicts(_each(S1=calls, S2=AddConnection(_LINK, {"description": "publishes"})))) == 1

    def test_adding_and_removing_one_connection_conflict(self) -> None:
        sets = _each(S1=AddConnection(_LINK, {}), S2=RemoveConnection(_LINK, _REVISION))
        assert len(conflicts(sets)) == 1

    def test_two_sets_removing_one_entity_converge(self) -> None:
        sets = _each(S1=RemoveEntity(_A, _REVISION), S2=RemoveEntity(_A, _REVISION))
        assert len(overlaps(sets)) == 1
        assert conflicts(sets) == ()


class TestRemoveVersusUse:
    @pytest.mark.parametrize(
        "use",
        [
            pytest.param(edit(_A, "name", "x"), id="edits-it"),
            pytest.param(AddConnection(joins("$ref:queue", _A), {}), id="connects-to-it"),
            pytest.param(edit_connection(_LINK, "description", "x"), id="edits-its-connection"),
        ],
    )
    def test_one_set_removing_what_another_uses_is_reported_with_both(self, use: Operation) -> None:
        removal = RemoveEntity(_A, _REVISION)
        sets = {"S1": change_set(removal), "S2": change_set(create("queue"), use)}

        (found,) = overlaps(sets)

        assert found.kind == "remove-versus-use"
        assert [(p.set_id, p.operation) for p in found.parties] == [("S1", removal), ("S2", use)]
        assert conflicts(sets) == (found,)

    def test_every_user_is_named(self) -> None:
        sets = _each(
            S1=RemoveEntity(_A, _REVISION), S2=edit(_A, "name", "x"), S3=edit(_A, "status", "active")
        )
        (found,) = [o for o in overlaps(sets) if o.kind == "remove-versus-use"]
        assert [p.set_id for p in found.parties] == ["S1", "S2", "S3"]

    def test_removing_a_connection_another_set_edits_is_reported(self) -> None:
        sets = _each(
            S1=RemoveConnection(_LINK, _REVISION),
            S2=edit_connection(_LINK, "metadata", "grpc", key="protocol"),
        )
        assert [o.kind for o in overlaps(sets)] == ["remove-versus-use"]

    def test_removing_an_entity_and_removing_its_connection_agree(self) -> None:
        assert overlaps(_each(S1=RemoveEntity(_A, _REVISION), S2=RemoveConnection(_LINK, _REVISION))) == ()


class TestScope:
    def test_one_alias_in_two_unrelated_sets_names_two_entities(self) -> None:
        assert overlaps(_each(S1=create("queue", name="Queue"), S2=create("queue", name="Topic"))) == ()

    def test_two_sets_editing_the_entity_of_the_set_beneath_both_overlap(self) -> None:
        sets = _each(
            S0=create("queue"),
            S1=edit("$ref:queue", "name", "Queue"),
            S2=edit("$ref:queue", "name", "Topic"),
        )
        (found,) = conflicts(sets, stacked_on={"S1": "S0", "S2": "S0"})
        assert [p.set_id for p in found.parties] == ["S1", "S2"]

    def test_the_same_alias_from_two_different_lower_sets_is_two_entities(self) -> None:
        sets = _each(
            S0=create("queue"), T0=create("queue"),
            S1=edit("$ref:queue", "name", "Queue"), T1=edit("$ref:queue", "name", "Topic"),
        )
        assert overlaps(sets, stacked_on={"S1": "S0", "T1": "T0"}) == ()

    def test_an_upper_set_changing_what_the_lower_changes_is_stacking_not_overlap(self) -> None:
        sets = _each(S0=edit(_A, "name", "Invoicing"), S1=edit(_A, "name", "Invoices"))
        assert overlaps(sets, stacked_on={"S1": "S0"}) == ()
        assert len(overlaps(sets)) == 1

    def test_an_upper_set_removing_what_the_lower_uses_is_stacking_too(self) -> None:
        sets = _each(S0=edit(_A, "name", "Invoicing"), S1=RemoveEntity(_A, _REVISION))
        assert overlaps(sets, stacked_on={"S1": "S0"}) == ()
        assert len(overlaps(sets)) == 1

    def test_the_upper_sets_value_stands_for_its_stack_against_an_unrelated_set(self) -> None:
        sets = _each(
            S0=edit(_A, "name", "Invoicing"), S1=edit(_A, "name", "Invoices"), S2=edit(_A, "name", "Payments")
        )
        (found,) = conflicts(sets, stacked_on={"S1": "S0"})
        assert [p.set_id for p in found.parties] == ["S1", "S2"]


def test_sets_that_touch_different_things_do_not_overlap() -> None:
    assert overlaps(_each(S1=edit(_A, "name", "x"), S2=edit(_B, "name", "y"))) == ()


def test_sibling_adaptations_can_disagree_about_an_alias_created_by_a_grandparent() -> None:
    sets = _each(naive=create("queue"), middle=edit(_A, "name", "Gateway"),
                 left=edit("$ref:queue", "name", "Bounded"), right=edit("$ref:queue", "name", "Unbounded"))
    found, = conflicts(sets, stacked_on={"middle": "naive", "left": "middle", "right": "naive"})
    assert {party.set_id for party in found.parties} == {"left", "right"}
