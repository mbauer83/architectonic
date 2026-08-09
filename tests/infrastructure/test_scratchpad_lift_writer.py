"""Translating a plan into a batch, and a batch's answer back into a receipt.

The executor holds no decisions — those were all made in the preflight — so what is asserted here
is the translation, which is exactly where a lift could quietly write the wrong thing: an alias that
does not resolve, a group that silently becomes `uncategorized`, or a correlation by position that
drifts when the batch reorders.
"""

from __future__ import annotations

from pathlib import Path

from src.application.scratchpad.lift import LiftItem
from src.infrastructure.scratchpad.bulk_write_lift import (
    BulkWriteLiftWriter,
    _batch_item,
    _receipt,
)


def _element(note_id: str = "n1", **overrides: object) -> LiftItem:
    fields: dict[str, object] = {
        "kind": "element", "id": note_id, "outcome": "create", "label": "Grow into mid-market",
        "artifact_type": "goal", "target": "q3-expansion",
    }
    return LiftItem(**{**fields, **overrides})  # type: ignore[arg-type]


def _connection(**overrides: object) -> LiftItem:
    fields: dict[str, object] = {
        "kind": "connection", "id": "l1", "outcome": "create", "label": "a --realizes--> b",
        "artifact_type": "archimate-realization", "source_ref": "$ref:n1",
        "target_ref": "ENT@9.x.order-management",
    }
    return LiftItem(**{**fields, **overrides})  # type: ignore[arg-type]


class TestOnePlanItemAsOneBatchItem:
    def test_an_element_carries_its_type_name_and_target_project(self) -> None:
        item = _batch_item(_element())

        assert item["op"] == "create_entity"
        assert item["artifact_type"] == "goal"
        assert item["name"] == "Grow into mid-market"
        assert item["group"] == "q3-expansion"
        # The alias is the note's own id, which is what a connection in the same batch addresses.
        assert item["_ref"] == "n1"

    def test_an_empty_body_and_no_specialization_are_omitted_rather_than_sent_empty(self) -> None:
        item = _batch_item(_element(target=""))

        assert "summary" not in item
        assert "specializations" not in item

    def test_a_body_becomes_the_summary_and_a_specialization_is_carried(self) -> None:
        item = _batch_item(_element(summary="Why we are here", specializations=("strategic-goal",)))

        assert item["summary"] == "Why we are here"
        assert item["specializations"] == ["strategic-goal"]

    def test_a_connection_addresses_ends_exactly_as_the_plan_resolved_them(self) -> None:
        item = _batch_item(_connection())

        assert item["op"] == "add_connection"
        assert item["source_entity"] == "$ref:n1"
        assert item["target_entity"] == "ENT@9.x.order-management"
        assert item["connection_type"] == "archimate-realization"


class TestTheBatchAnswerAsAReceipt:
    def test_each_allocated_id_is_correlated_back_to_the_note_that_asked_for_it(self) -> None:
        answer = {
            "committed": True,
            "operation_id": "op-1",
            "items": [
                {"op": "create_entity", "artifact_id": "ENT@5.q.grow"},
                {"op": "add_connection", "artifact_id": "CON@5.r.realizes"},
            ],
        }

        receipt = _receipt(answer, (_element(), _connection()))

        assert receipt.committed
        assert receipt.realized == {"n1": "ENT@5.q.grow", "l1": "CON@5.r.realizes"}
        assert receipt.operation_id == "op-1"

    def test_an_item_that_failed_is_reported_by_label_and_allocates_nothing(self) -> None:
        answer = {
            "committed": False,
            "items": [{"op": "create_entity", "error": "verification failed"}],
        }

        receipt = _receipt(answer, (_element(),))

        assert receipt.realized == {}
        assert receipt.errors == ("Grow into mid-market: verification failed",)


class TestResolvingTheTarget:
    def test_the_root_model_is_a_target_with_no_group_and_nothing_declared(self, tmp_path: Path) -> None:
        target = BulkWriteLiftWriter(tmp_path).resolve_target("")

        assert target.group == "" and not target.exists

    def test_an_unknown_project_is_reported_as_new_rather_than_refused(self, tmp_path: Path) -> None:
        # A lift may create one: "this thinking has become a project" is how a project starts.
        target = BulkWriteLiftWriter(tmp_path).resolve_target("q3-expansion")

        assert target.group == "q3-expansion"
        assert not target.exists


class TestADocumentAndTheReferencesItRecords:
    def test_a_document_carries_its_type_title_and_collection(self) -> None:
        item = _batch_item(LiftItem(
            kind="document", id="d1", outcome="create", label="Q3 vision",
            artifact_type="vision", target="q3-expansion", summary="Where this is going",
        ))

        assert item["op"] == "create_document"
        assert item["doc_type"] == "vision"
        assert item["title"] == "Q3 vision"
        # One target names both the model-project and the document collection: asking twice for one
        # decision a person has already made is how two answers start to disagree.
        assert item["group"] == "q3-expansion"
        assert item["body"] == "Where this is going"

    def test_its_references_travel_with_it_rather_than_as_a_second_write(self) -> None:
        item = _batch_item(LiftItem(
            kind="document", id="d1", outcome="create", label="Q3 vision",
            artifact_type="vision", entity_refs=("$ref:n1", "ENT@9.x.order"),
        ))

        assert item["entity_refs"] == ["$ref:n1", "ENT@9.x.order"]
