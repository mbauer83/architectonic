"""What the model would say with a set applied — the reading an applier or a hypothetical read needs."""

from __future__ import annotations

from typing import Any

import pytest

from src.application.change_sets.base import BaseRevision
from src.application.change_sets.composition import compose
from src.application.change_sets.operations import (
    AddConnection,
    MalformedChangeSet,
    RemoveConnection,
    RemoveEntity,
)
from src.application.change_sets.reading import RecordedReading
from src.application.change_sets.standing import standing_of
from src.application.modeling.edit_field_catalogue import CONTENT, KEYED
from tests.support.change_sets import GROUP, change_set, create, edit, edit_connection, joins

_REVISION = BaseRevision("0123456789abcdef")
_A = "ENT@1.a"
_B = "ENT@1.b"
_LINK = joins(_A, _B)
_MODEL = RecordedReading(
    entities={
        _A: {"name": "Billing", "summary": "Takes payments.", "properties": {"tier": "silver", "region": "eu"}},
        _B: {"name": "Ledger"},
    },
    connections={_LINK: {"description": "calls", "metadata": {"protocol": "http"}}},
)


class TestOneSet:
    def test_an_untouched_artifact_reads_as_the_model_has_it(self) -> None:
        composed = compose(change_set(edit(_A, "name", "Invoicing")), _MODEL)
        assert composed.entity(_B) == _MODEL.entity(_B)
        assert composed.connection(_LINK) == _MODEL.connection(_LINK)

    def test_a_whole_field_edit_replaces_the_field_and_keeps_the_rest(self) -> None:
        composed = compose(change_set(edit(_A, "name", "Invoicing")), _MODEL)
        assert composed.entity(_A) == {**_MODEL.entities[_A], "name": "Invoicing"}

    def test_a_keyed_edit_changes_one_key_and_keeps_its_siblings(self) -> None:
        composed = compose(change_set(edit(_A, "properties", "gold", key="tier")), _MODEL)
        assert composed.entity(_A)["properties"] == {"tier": "gold", "region": "eu"}  # type: ignore[index]

    def test_a_keyed_edit_to_none_removes_the_key(self) -> None:
        composed = compose(change_set(edit(_A, "properties", None, key="region")), _MODEL)
        assert composed.entity(_A)["properties"] == {"tier": "silver"}  # type: ignore[index]

    def test_a_keyed_edit_adds_a_key_to_a_field_that_held_nothing(self) -> None:
        composed = compose(change_set(edit(_B, "properties", "x", key="owner")), _MODEL)
        assert composed.entity(_B)["properties"] == {"owner": "x"}  # type: ignore[index]

    def test_the_reading_beneath_is_not_changed(self) -> None:
        before = {key: dict(value) for key, value in _MODEL.entities.items()}
        compose(change_set(edit(_A, "properties", "gold", key="tier"), RemoveEntity(_B, _REVISION)), _MODEL)
        assert _MODEL.entities == before

    def test_a_created_entity_reads_under_its_alias_as_what_the_create_states(self) -> None:
        composed = compose(change_set(create("queue", name="Queue", summary="Buffers.")), _MODEL)
        assert composed.entity("$ref:queue") == {
            "artifact_type": "application-component", "name": "Queue", "group": GROUP,
            "summary": "Buffers.",
        }

    def test_an_added_connection_reads_as_what_the_add_states(self) -> None:
        link = joins(_A, "$ref:queue")
        composed = compose(change_set(create("queue"), AddConnection(link, {"description": "enqueues"})), _MODEL)
        assert composed.connection(link) == {"description": "enqueues"}

    def test_a_connection_edit_is_composed_like_an_entity_edit(self) -> None:
        composed = compose(change_set(edit_connection(_LINK, "metadata", "grpc", key="protocol")), _MODEL)
        assert composed.connection(_LINK) == {"description": "calls", "metadata": {"protocol": "grpc"}}

    def test_a_removed_entity_reads_as_absent(self) -> None:
        assert compose(change_set(RemoveEntity(_B, _REVISION)), _MODEL).entity(_B) is None

    def test_a_removed_entity_takes_its_connections_with_it(self) -> None:
        """Whether or not the set removed them by name: nothing joins what is not there."""
        composed = compose(change_set(RemoveEntity(_B, _REVISION)), _MODEL)
        assert composed.connection(_LINK) is None

    def test_a_removed_connection_reads_as_absent_and_leaves_its_ends(self) -> None:
        composed = compose(change_set(RemoveConnection(_LINK, _REVISION)), _MODEL)
        assert composed.connection(_LINK) is None
        assert composed.entity(_A) is not None

    @pytest.mark.parametrize("field", sorted(CONTENT["entity"]))
    def test_every_field_an_edit_may_name_is_composed(self, field: str) -> None:
        key = "k" if field in KEYED["entity"] else None
        composed = compose(change_set(edit(_A, field, "new", key=key)), _MODEL)
        held: Any = composed.entity(_A)[field]  # type: ignore[index]
        assert (held["k"] if key else held) == "new"


class TestWhatHasNothingToApplyTo:
    def test_an_edit_of_something_gone_is_named_and_changes_nothing(self) -> None:
        orphan = edit("ENT@1.gone", "name", "x")
        composed = compose(change_set(orphan, edit(_A, "name", "Invoicing")), _MODEL)
        assert composed.unapplied == (orphan,)
        assert composed.entity("ENT@1.gone") is None
        assert composed.entity(_A)["name"] == "Invoicing"  # type: ignore[index]

    def test_a_connection_to_something_gone_is_named(self) -> None:
        orphan = AddConnection(joins(_A, "ENT@1.gone"), {})
        composed = compose(change_set(orphan), _MODEL)
        assert composed.unapplied == (orphan,)
        assert composed.connection(orphan.address) is None

    def test_an_edit_of_a_connection_that_is_gone_is_named(self) -> None:
        orphan = edit_connection(joins(_B, _A), "description", "x")
        assert compose(change_set(orphan), _MODEL).unapplied == (orphan,)


class TestASetReadOnTopOfAnother:
    def test_the_lower_set_is_applied_first_and_the_upper_on_top(self) -> None:
        lower = change_set(edit(_A, "name", "Invoicing"), create("queue", name="Queue"))
        upper = change_set(
            edit(_A, "name", "Invoices"),
            edit("$ref:queue", "summary", "Buffers."),
            AddConnection(joins(_A, "$ref:queue"), {}),
        )
        composed = compose(upper, _MODEL, beneath=lower)

        assert composed.entity(_A)["name"] == "Invoices"  # type: ignore[index]
        assert composed.entity("$ref:queue")["summary"] == "Buffers."  # type: ignore[index]
        assert composed.entity("$ref:queue")["name"] == "Queue"  # type: ignore[index]
        assert composed.connection(joins(_A, "$ref:queue")) == {}
        assert composed.unapplied == ()

    def test_an_upper_set_removing_what_the_lower_connected_removes_the_connection_too(self) -> None:
        link = joins(_A, "$ref:queue")
        lower = change_set(create("queue"), AddConnection(link, {}))
        upper = change_set(RemoveEntity("$ref:queue", _REVISION))

        composed = compose(upper, _MODEL, beneath=lower)

        assert composed.entity("$ref:queue") is None
        assert composed.connection(link) is None

    def test_the_lower_set_alone_does_not_show_the_upper_sets_changes(self) -> None:
        lower = change_set(edit(_A, "name", "Invoicing"))
        assert compose(lower, _MODEL).entity(_A)["name"] == "Invoicing"  # type: ignore[index]

    def test_an_upper_set_is_not_composed_without_the_set_it_names_things_from(self) -> None:
        with pytest.raises(MalformedChangeSet, match="neither it nor a set beneath it"):
            compose(change_set(edit("$ref:queue", "name", "x")), _MODEL)

    def test_a_composed_reading_is_a_reading_so_layers_can_be_handed_back_in(self) -> None:
        once = compose(change_set(edit(_A, "name", "Invoicing")), _MODEL)
        twice = compose(change_set(edit(_A, "status", "active")), once)
        assert (twice.entity(_A)["name"], twice.entity(_A)["status"]) == ("Invoicing", "active")  # type: ignore[index]


def test_what_applies_is_already_there_once_composed() -> None:
    """Composition and standing agree: after a set is applied, each of its edits is already there."""
    applied = change_set(
        edit(_A, "name", "Invoicing", was="Billing"),
        edit(_A, "properties", "gold", was="silver", key="tier"),
        edit(_A, "summary", "Sends invoices.", was="Takes payments."),
        edit_connection(_LINK, "metadata", "grpc", was="http", key="protocol"),
    )
    assert {s.standing for s in standing_of(applied, _MODEL)} == {"applies"}
    assert {s.standing for s in standing_of(applied, compose(applied, _MODEL))} == {"already-there"}
