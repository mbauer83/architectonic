"""What a write states, read as the named operations a policy decides on (`stated_operations`).

A canvas save is one request carrying several operations; each is read from the request alone, so the
server can decide on every one of them without asking the client what it meant.
"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter

from src.application.operation_catalog import COMPOSE, GENERATE, PLACE, RESTACK, ROUTE
from src.infrastructure.candidate_wire import RecordedEdit
from src.infrastructure.diagram_composition import DiagramReplacement
from src.infrastructure.diagram_layout_wire import ArrangeIntent, LayoutPatch
from src.infrastructure.stated_operations import arrangement_operations, recorded_operations, replacement_operations

_BASE = {"diagram_type": "archimate-layered", "name": "Order handling", "entity_ids": [], "connection_ids": []}
_ENTRY = {"value": {"x": 1, "y": 2}}


def _replacement(**stated: Any) -> DiagramReplacement:
    return DiagramReplacement.model_validate({**_BASE, **stated})


def test_a_replacement_composes_whatever_else_it_does() -> None:
    assert replacement_operations(_replacement()) == {COMPOSE}


def test_each_model_command_of_a_save_is_its_own_operation() -> None:
    commands = [
        {"op": "model.element.rename", "artifact_id": "APP@1.a", "name": "A"},
        {"op": "model.relation.edit", "artifact_id": "APP@1.a---APP@2.b@@archimate-serving", "description": "d"},
    ]
    assert replacement_operations(_replacement(commands=commands)) == {
        COMPOSE, "model.element.rename", "model.relation.edit",
    }


def test_a_layout_patch_is_read_by_the_sections_it_changes() -> None:
    patch = {
        "elements": {"APP@1.a": _ENTRY}, "relations": {"r": {"value": {"via": []}}}, "z": {"APP@1.a": {"value": 2}},
    }
    assert replacement_operations(_replacement(layout_patch=patch)) == {COMPOSE, PLACE, ROUTE, RESTACK}
    assert arrangement_operations(LayoutPatch.model_validate({"boxes": {"g-1": None}}), None) == {PLACE}


def test_a_whole_layout_and_giving_a_hand_written_body_up_are_operations_too() -> None:
    assert replacement_operations(_replacement(layout={})) == {COMPOSE, PLACE}
    assert replacement_operations(_replacement(layout={"z": {}})) == {COMPOSE, RESTACK}
    assert replacement_operations(_replacement(manual_layout=False)) == {COMPOSE, GENERATE}
    assert replacement_operations(_replacement(manual_layout=True)) == {COMPOSE}


def test_an_intent_is_read_as_what_it_changes() -> None:
    intents = TypeAdapter(list[ArrangeIntent]).validate_python([
        {"intent": "straighten", "relations": ["r"]}, {"intent": "unnest", "keys": ["APP@1.a"]},
    ])
    assert arrangement_operations(None, intents) == {ROUTE, COMPOSE}


def test_each_kind_of_recorded_edit_is_its_own_operation() -> None:
    edits = TypeAdapter(list[RecordedEdit]).validate_python([
        {"op": "edit_entity", "artifact_id": "APP@1.a", "field": "name", "value": "A"},
        {"op": "remove_entity", "artifact_id": "APP@2.b"},
        {"op": "edit_entity", "artifact_id": "APP@2.b", "field": "summary", "value": "s"},
    ])
    assert recorded_operations(edits) == {"change_set.edit_entity", "change_set.remove_entity"}
