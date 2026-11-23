"""Standing: applies, already there, drifted or conflicting — against records, not a repository."""

from __future__ import annotations

from typing import Any

import pytest

from src.application.change_sets.base import BaseRevision, record_revision
from src.application.change_sets.change_set import ChangeSet
from src.application.change_sets.operations import (
    AddConnection,
    CreateEntity,
    Operation,
    RemoveConnection,
    RemoveEntity,
)
from src.application.change_sets.reading import RecordedReading
from src.application.change_sets.standing import STANDINGS, Standing, standing_of
from src.application.modeling.edit_field_catalogue import CONTENT, KEYED
from tests.support.change_sets import change_set, create, edit, edit_connection, joins

_A = "ENT@1.a"
_B = "ENT@1.b"
_ENTITY: dict[str, Any] = {
    "name": "Billing", "summary": "Takes payments.", "status": "active",
    "properties": {"tier": "silver"}, "keywords": ("money",),
}
_LINK = joins(_A, _B)
_CONNECTION: dict[str, Any] = {"description": "calls", "metadata": {"protocol": "http"}}
_MODEL = RecordedReading(entities={_A: _ENTITY, _B: {"name": "Ledger"}}, connections={_LINK: _CONNECTION})


def _one(operation: Operation, model: RecordedReading = _MODEL, **kwargs: Any) -> tuple[Standing, str]:
    (found,) = standing_of(change_set(operation), model, **kwargs)
    assert found.operation == operation
    return found.standing, found.reason


def _with(entity: dict[str, Any]) -> RecordedReading:
    return RecordedReading(entities={**_MODEL.entities, _A: entity}, connections=_MODEL.connections)


class TestAnEdit:
    def test_applies_where_the_model_is_as_it_was_read(self) -> None:
        assert _one(edit(_A, "name", "Invoicing", was="Billing"))[0] == "applies"

    def test_is_already_there_where_the_model_says_what_it_asks(self) -> None:
        assert _one(edit(_A, "name", "Billing", was="Payments"))[0] == "already-there"

    def test_has_drifted_where_someone_else_changed_the_value(self) -> None:
        standing, reason = _one(edit(_A, "name", "Invoicing", was="Payments"))
        assert standing == "drifted"
        assert "name of ENT@1.a" in reason

    def test_conflicts_where_its_target_is_gone(self) -> None:
        standing, reason = _one(edit("ENT@1.gone", "name", "x", was="y"))
        assert standing == "conflicting"
        assert "not in the model any more" in reason

    def test_a_field_with_no_reading_is_not_evidence_of_drift(self) -> None:
        """`attribute_types` is not in this reading at all: unreadable is not "changed"."""
        assert _one(edit(_A, "attribute_types", "string", was="number", key="tier"))[0] == "applies"

    @pytest.mark.parametrize(
        ("was", "to", "standing"),
        [
            pytest.param("silver", "gold", "applies", id="unmoved"),
            pytest.param("bronze", "silver", "already-there", id="already-set"),
            pytest.param("bronze", "gold", "drifted", id="moved"),
        ],
    )
    def test_a_key_is_judged_on_its_own_value(self, was: str, to: str, standing: Standing) -> None:
        assert _one(edit(_A, "properties", to, was=was, key="tier"))[0] == standing

    def test_a_sibling_key_changing_does_not_drift_this_one(self) -> None:
        """The reason an edit addresses a key: another attribute moving is not this one moving."""
        moved_elsewhere = _with({**_ENTITY, "properties": {"tier": "silver", "region": "eu"}})
        operation = edit(_A, "properties", "gold", was="silver", key="tier")
        assert _one(operation, moved_elsewhere)[0] == "applies"

    def test_a_key_that_was_absent_and_still_is_applies(self) -> None:
        assert _one(edit(_A, "properties", "eu", was=None, key="region"))[0] == "applies"

    def test_a_key_that_appeared_meanwhile_has_drifted(self) -> None:
        appeared = _with({**_ENTITY, "properties": {"tier": "silver", "region": "us"}})
        assert _one(edit(_A, "properties", "eu", was=None, key="region"), appeared)[0] == "drifted"

    def test_removing_a_key_that_is_gone_is_already_there(self) -> None:
        assert _one(edit(_A, "properties", None, was="x", key="region"))[0] == "already-there"

    @pytest.mark.parametrize(
        ("was", "to", "standing"),
        [
            pytest.param("Takes payments.", "Takes card payments.", "applies", id="unmoved"),
            pytest.param("Takes payments.\n", "Takes card payments.", "applies", id="whitespace-only"),
            pytest.param("An older text.", "Takes payments.", "already-there", id="already-says-it"),
            pytest.param("An older text.", "Takes card payments.", "drifted", id="moved"),
        ],
    )
    def test_prose_is_judged_by_its_revision(self, was: str, to: str, standing: Standing) -> None:
        assert _one(edit(_A, "summary", to, was=was))[0] == standing

    def test_a_connection_edit_is_judged_the_same_way(self) -> None:
        assert _one(edit_connection(_LINK, "metadata", "grpc", was="http", key="protocol"))[0] == "applies"
        assert _one(edit_connection(_LINK, "metadata", "grpc", was="amqp", key="protocol"))[0] == "drifted"
        assert _one(edit_connection(_LINK, "description", "calls", was="x"))[0] == "already-there"

    def test_a_connection_edit_conflicts_where_the_connection_is_gone(self) -> None:
        standing, _ = _one(edit_connection(joins(_B, _A), "description", "x", was="y"))
        assert standing == "conflicting"

    @pytest.mark.parametrize("field", sorted(CONTENT["entity"]))
    def test_every_field_an_edit_may_name_has_a_standing(self, field: str) -> None:
        """Over the whole vocabulary: no field is judged by falling through."""
        key = "k" if field in KEYED["entity"] else None
        held: Any = {"k": "old"} if key else "old"
        operation = edit(_A, field, "new", was="old", key=key)
        assert _one(operation, _with({field: held}))[0] == "applies"
        moved: Any = {"k": "theirs"} if key else "theirs"
        assert _one(operation, _with({field: moved}))[0] == "drifted"


class TestARemoval:
    def test_applies_where_the_record_is_as_it_was_read(self) -> None:
        assert _one(RemoveEntity(_A, BaseRevision(record_revision(_ENTITY))))[0] == "applies"

    def test_has_drifted_where_the_record_changed(self) -> None:
        was = BaseRevision(record_revision({**_ENTITY, "name": "Payments"}))
        standing, reason = _one(RemoveEntity(_A, was))
        assert standing == "drifted"
        assert "discard" in reason

    def test_is_already_there_where_the_record_is_gone(self) -> None:
        assert _one(RemoveEntity("ENT@1.gone", BaseRevision("0" * 16)))[0] == "already-there"

    def test_a_connection_removal_is_judged_the_same_way(self) -> None:
        assert _one(RemoveConnection(_LINK, BaseRevision(record_revision(_CONNECTION))))[0] == "applies"
        assert _one(RemoveConnection(_LINK, BaseRevision("0" * 16)))[0] == "drifted"
        assert _one(RemoveConnection(joins(_B, _A), BaseRevision("0" * 16)))[0] == "already-there"

    def test_two_readings_of_one_record_have_one_revision(self) -> None:
        listed = {"keywords": ["money"], "properties": {"b": 1, "a": 2}}
        tupled = {"properties": {"a": 2, "b": 1}, "keywords": ("money",)}
        assert record_revision(listed) == record_revision(tupled)


class TestACreate:
    def test_applies(self) -> None:
        assert _one(create("queue"))[0] == "applies"

    def test_with_a_chosen_id_is_already_there_where_that_entity_says_the_same(self) -> None:
        chosen = CreateEntity("billing", {**create("billing").fields, "name": "Billing"}, artifact_id=_A)
        assert _one(chosen)[0] == "already-there"

    def test_with_a_chosen_id_conflicts_where_that_entity_says_something_else(self) -> None:
        chosen = CreateEntity("billing", create("billing", name="Invoicing").fields, artifact_id=_A)
        standing, reason = _one(chosen)
        assert standing == "conflicting"
        assert "name" in reason

    def test_a_new_connection_applies_between_entities_that_exist(self) -> None:
        assert _one(AddConnection(joins(_B, _A), {}))[0] == "applies"

    def test_a_new_connection_conflicts_where_an_endpoint_is_missing(self) -> None:
        standing, reason = _one(AddConnection(joins(_A, "ENT@1.gone"), {}))
        assert standing == "conflicting"
        assert "ENT@1.gone" in reason

    def test_a_new_connection_may_join_what_its_own_set_creates(self) -> None:
        link = AddConnection(joins(_A, "$ref:queue"), {})
        found = {s.operation.claim: s.standing for s in standing_of(change_set(create("queue"), link), _MODEL)}
        assert found[link.claim] == "applies"

    def test_a_connection_that_exists_and_agrees_is_already_there(self) -> None:
        assert _one(AddConnection(_LINK, {"description": "calls"}))[0] == "already-there"

    def test_a_connection_that_exists_and_differs_conflicts(self) -> None:
        assert _one(AddConnection(_LINK, {"description": "publishes to"}))[0] == "conflicting"


class TestVerificationIsInjected:
    def test_a_refusal_makes_an_applying_operation_conflict_verbatim(self) -> None:
        refusal = "E114: a serving relation may not target a business actor."
        standing, reason = _one(AddConnection(joins(_B, _A), {}), would_refuse=lambda _: refusal)
        assert (standing, reason) == ("conflicting", refusal)

    def test_it_is_asked_only_about_what_would_otherwise_apply(self) -> None:
        """A drifted edit is reported as drifted: the model moving is not the set being invalid."""
        asked: list[Operation] = []

        def would_refuse(operation: Operation) -> str | None:
            asked.append(operation)
            return "refused"

        drifted = edit(_A, "name", "Invoicing", was="Payments")
        applying = edit(_B, "name", "Books", was="Ledger")
        judged = standing_of(change_set(drifted, applying), _MODEL, would_refuse=would_refuse)
        found = {s.operation.claim: s.standing for s in judged}

        assert found == {drifted.claim: "drifted", applying.claim: "conflicting"}
        assert asked == [applying]


class TestASetReadOnTopOfAnother:
    def _layers(self) -> tuple[ChangeSet, ChangeSet, Operation, Operation]:
        lower = change_set(create("queue", name="Queue"), edit(_A, "name", "Invoicing", was="Billing"))
        link = AddConnection(joins(_A, "$ref:queue"), {})
        rename = edit(_A, "name", "Invoices", was="Invoicing")
        return lower, change_set(link, rename), link, rename

    def test_is_judged_against_the_model_with_the_lower_set_applied(self) -> None:
        lower, upper, link, rename = self._layers()
        found = {s.operation.claim: s.standing for s in standing_of(upper, _MODEL, beneath=(lower,))}
        assert found == {link.claim: "applies", rename.claim: "applies"}

    def test_cannot_be_judged_without_it(self) -> None:
        _, upper, _, _ = self._layers()
        with pytest.raises(ValueError, match="neither it nor a set beneath it"):
            standing_of(upper, _MODEL)


def test_the_standings_are_the_four_the_plan_names() -> None:
    assert set(STANDINGS) == {"applies", "already-there", "drifted", "conflicting"}


def test_every_operation_of_a_set_is_given_a_standing() -> None:
    operations = (create("queue"), edit(_A, "name", "x", was="Billing"), RemoveEntity(_B, BaseRevision("0" * 16)))
    found = standing_of(change_set(*operations), _MODEL)
    assert sorted(s.operation.claim for s in found) == sorted(op.claim for op in operations)
