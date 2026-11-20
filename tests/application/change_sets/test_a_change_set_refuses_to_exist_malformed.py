"""Every refusal an operation or a set makes at construction, and the equality a set has.

A change set is built where an author is present and read back from a file where nobody is, so each
refusal is a sentence. The assertions match on the part of the sentence that names the fault.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest

from src.application.change_sets.base import BaseRevision, BaseValue
from src.application.change_sets.change_set import FORMAT_VERSION, ChangeSet
from src.application.change_sets.operations import (
    AddConnection,
    ConnectionAddress,
    CreateEntity,
    EditConnection,
    EditEntity,
    MalformedChangeSet,
    RemoveConnection,
    RemoveEntity,
)
from src.application.modeling.edit_field_catalogue import CONTENT, KEYED, PROSE, atomic
from tests.support.change_sets import GROUP, change_set, create, edit, edit_connection, joins

_REVISION = BaseRevision("0123456789abcdef")
_A = "ENT@1.a"
_B = "ENT@1.b"


class TestAnEditAddressesOneNamedThing:
    def test_a_field_outside_the_vocabulary_is_refused_with_what_is_accepted(self) -> None:
        with pytest.raises(MalformedChangeSet, match="not a field of a entity") as refusal:
            EditEntity(_A, "colour", "red", BaseValue(None))
        assert "properties" in str(refusal.value)

    def test_the_subject_cannot_be_set_as_a_field(self) -> None:
        with pytest.raises(MalformedChangeSet, match="not a field"):
            EditEntity(_A, "artifact_id", "ENT@1.z", BaseValue(_A))

    @pytest.mark.parametrize("field", sorted(KEYED["entity"]))
    def test_a_keyed_field_is_never_replaced_whole(self, field: str) -> None:
        with pytest.raises(MalformedChangeSet, match="names the one key"):
            EditEntity(_A, field, {"tier": "gold"}, BaseValue(None))

    def test_a_connections_metadata_is_keyed_too(self) -> None:
        with pytest.raises(MalformedChangeSet, match="names the one key"):
            EditConnection(joins(_A, _B), "metadata", {"x": 1}, BaseValue(None))

    @pytest.mark.parametrize("field", sorted(atomic("entity") | PROSE["entity"]))
    def test_a_field_without_keys_takes_none(self, field: str) -> None:
        with pytest.raises(MalformedChangeSet, match="no keys to address"):
            edit(_A, field, "x", key="3")

    @pytest.mark.parametrize("field", sorted(PROSE["entity"]))
    def test_prose_records_a_revision_not_the_text(self, field: str) -> None:
        with pytest.raises(MalformedChangeSet, match="prose"):
            EditEntity(_A, field, "new text", BaseValue("old text"))

    @pytest.mark.parametrize("field", sorted(CONTENT["entity"] - PROSE["entity"]))
    def test_everything_else_records_the_value(self, field: str) -> None:
        key = "k" if field in KEYED["entity"] else None
        with pytest.raises(MalformedChangeSet, match="records the value"):
            EditEntity(_A, field, "x", _REVISION, key=key)

    def test_an_edit_names_what_it_changes(self) -> None:
        with pytest.raises(MalformedChangeSet, match="names the entity"):
            EditEntity("", "name", "x", BaseValue("y"))

    def test_one_key_of_a_keyed_field_is_an_edit(self) -> None:
        operation = edit(_A, "properties", "gold", was="silver", key="tier")
        assert operation.claim == ("entity", _A, "properties", "tier")


class TestACreateStatesWhatItCreates:
    def test_it_carries_an_alias(self) -> None:
        with pytest.raises(MalformedChangeSet, match="alias"):
            create("")

    @pytest.mark.parametrize("omitted", ["artifact_type", "name", "group"])
    def test_it_states_its_type_its_name_and_its_group(self, omitted: str) -> None:
        stated = {"artifact_type": "node", "name": "Queue", "group": GROUP}
        del stated[omitted]
        with pytest.raises(MalformedChangeSet, match=omitted):
            CreateEntity(ref="queue", fields=stated)

    def test_it_states_nothing_an_entity_does_not_have(self) -> None:
        with pytest.raises(MalformedChangeSet, match="not something a new entity states"):
            create("queue", src_multiplicity="1")

    def test_a_new_connection_states_nothing_a_connection_does_not_have(self) -> None:
        with pytest.raises(MalformedChangeSet, match="not something a new connection states"):
            AddConnection(joins(_A, _B), {"name": "x"})

    def test_a_connection_is_addressed_by_all_three_parts(self) -> None:
        with pytest.raises(MalformedChangeSet, match="all three"):
            ConnectionAddress(_A, "", _B)


class TestARemovalRecordsWhatItRemoves:
    def test_an_entity_removal_needs_a_revision(self) -> None:
        with pytest.raises(MalformedChangeSet, match="revision of the record"):
            RemoveEntity(_A, BaseValue({"name": "a"}))  # type: ignore[arg-type]

    def test_a_connection_removal_needs_a_revision(self) -> None:
        with pytest.raises(MalformedChangeSet, match="revision of the record"):
            RemoveConnection(joins(_A, _B), BaseValue(None))  # type: ignore[arg-type]

    def test_a_removal_names_what_it_removes(self) -> None:
        with pytest.raises(MalformedChangeSet, match="names the entity"):
            RemoveEntity("", _REVISION)


class TestWhatASetWasWrittenUnder:
    def test_it_says_which_revision(self) -> None:
        with pytest.raises(MalformedChangeSet, match="which repository revision"):
            change_set(repository_revision="")

    def test_a_format_this_version_does_not_read_is_refused(self) -> None:
        with pytest.raises(MalformedChangeSet, match="written in format"):
            change_set(format_version=FORMAT_VERSION + 1)

    def test_a_set_with_no_operations_is_a_set(self) -> None:
        assert change_set().operations == ()

    def test_it_carries_nothing_only_a_candidate_architecture_has(self) -> None:
        """The shared value stays shared: a name or a work state here would make every holder —
        a proposed change, an edit session — carry a header it does not have."""
        assert {part.name for part in dataclasses.fields(ChangeSet)} == {
            "operations", "repository_revision", "format_version",
        }


class TestOperationsStandTogether:
    def test_one_operation_per_key(self) -> None:
        with pytest.raises(MalformedChangeSet, match="one operation per key"):
            change_set(edit(_A, "name", "x"), edit(_A, "name", "y"))

    def test_two_keys_of_one_field_are_two_operations(self) -> None:
        both = change_set(
            edit(_A, "properties", "gold", key="tier"), edit(_A, "properties", "eu", key="region")
        )
        assert len(both.operations) == 2

    def test_two_creates_cannot_share_an_alias(self) -> None:
        with pytest.raises(MalformedChangeSet, match="one operation per key"):
            change_set(create("queue"), create("queue", name="Other"))

    def test_adding_and_removing_one_connection_is_two_operations_on_one_key(self) -> None:
        with pytest.raises(MalformedChangeSet, match="one operation per key"):
            change_set(AddConnection(joins(_A, _B), {}), RemoveConnection(joins(_A, _B), _REVISION))

    def test_what_a_set_creates_is_stated_in_the_create(self) -> None:
        with pytest.raises(MalformedChangeSet, match="put the value in the create"):
            change_set(create("queue"), edit("$ref:queue", "name", "Queue 2"))

    def test_a_set_does_not_remove_what_it_creates(self) -> None:
        """Creating and removing one entity are two operations on the entity as a whole."""
        with pytest.raises(MalformedChangeSet, match="one operation per key"):
            change_set(create("queue"), RemoveEntity("$ref:queue", _REVISION))

    def test_inside_the_set_a_created_entity_is_named_by_its_alias(self) -> None:
        chosen = CreateEntity("queue", create("queue").fields, artifact_id="NEW@1.queue")
        with pytest.raises(MalformedChangeSet, match="named by its alias"):
            change_set(chosen, AddConnection(joins(_A, "NEW@1.queue"), {}))

    def test_what_a_set_adds_is_stated_in_the_add(self) -> None:
        with pytest.raises(MalformedChangeSet, match="operation that adds it"):
            change_set(
                AddConnection(joins(_A, _B), {}),
                edit_connection(joins(_A, _B), "src_multiplicity", "1"),
            )

    @pytest.mark.parametrize(
        "use",
        [
            pytest.param(edit(_A, "name", "x"), id="edits-it"),
            pytest.param(AddConnection(joins(_B, _A), {}), id="connects-to-it"),
            pytest.param(edit_connection(joins(_A, _B), "src_multiplicity", "1"), id="edits-its-connection"),
        ],
    )
    def test_a_set_does_not_remove_an_entity_it_also_uses(self, use: Any) -> None:
        with pytest.raises(MalformedChangeSet, match="removal and a use"):
            change_set(RemoveEntity(_A, _REVISION), use)

    def test_a_set_may_remove_an_entity_together_with_its_connections(self) -> None:
        both = change_set(RemoveEntity(_A, _REVISION), RemoveConnection(joins(_A, _B), _REVISION))
        assert len(both.operations) == 2

    def test_a_set_does_not_edit_a_connection_it_removes(self) -> None:
        with pytest.raises(MalformedChangeSet, match="removes the connection"):
            change_set(
                RemoveConnection(joins(_A, _B), _REVISION),
                edit_connection(joins(_A, _B), "metadata", 1, key="x"),
            )

    def test_a_reference_nothing_in_the_set_creates_is_not_the_sets_to_refuse(self) -> None:
        """It may be read on top of a set that creates it; `application_order` settles that."""
        assert len(change_set(AddConnection(joins(_A, "$ref:queue"), {})).operations) == 1


class TestASetHasNoAuthoredOrder:
    def test_two_sets_with_the_same_operations_are_equal_however_they_were_assembled(self) -> None:
        operations = (
            create("queue"), AddConnection(joins(_A, "$ref:queue"), {}), edit(_A, "name", "x"),
            RemoveEntity(_B, _REVISION),
        )
        assert change_set(*operations) == change_set(*reversed(operations))

    def test_a_different_value_is_a_different_set(self) -> None:
        assert change_set(edit(_A, "name", "x")) != change_set(edit(_A, "name", "y"))
