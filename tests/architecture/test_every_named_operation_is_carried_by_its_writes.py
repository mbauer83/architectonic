"""The operation catalog is one vocabulary for REST and MCP: each operation names the writes that carry it.

A policy decides on an operation's name, so the name must mean the same on both surfaces: every carrier
of an operation is a real REST mutation or MCP mutation tool, every operation has a REST carrier whose
intent decides it, and every carrier of one operation is authorized with that same intent. The writes the
candidate pages and the stress workspace make are all in the catalog, so none of their buttons is offered
on a permission nobody answers; and what a request can be read to state is only ever an operation its
carrier carries.
"""

from __future__ import annotations

from typing import get_args

from src.infrastructure.candidate_wire import RecordedEdit
from src.infrastructure.diagram_layout_wire import ArrangeIntent
from src.infrastructure.mcp.artifact_mcp.mutation_registration import MUTATION_TOOL_MANIFEST
from src.infrastructure.operation_catalog import (
    COMPOSE,
    GENERATE,
    INTENT_OPERATIONS,
    OPERATION_CATALOG,
    SECTION_OPERATIONS,
)
from src.infrastructure.rest.route_policy._candidates import CANDIDATE_ROWS
from src.infrastructure.rest.routers.rest_mutation_manifest import REST_MUTATION_MANIFEST
from src.infrastructure.rest.routers.sync._authority import WORKFLOW_ACTIONS
from src.infrastructure.write.artifact_write.canvas_commands import CanvasCommand


def _literal(model: type, field: str = "op") -> str:
    return get_args(model.model_fields[field].annotation)[0]


def test_every_carrier_is_a_rest_mutation_or_an_mcp_mutation_tool() -> None:
    carriers = {carrier for operation in OPERATION_CATALOG.values() for carrier in operation.carriers}
    assert carriers - REST_MUTATION_MANIFEST.keys() - MUTATION_TOOL_MANIFEST.keys() == set()


def test_every_operation_is_decided_by_one_intent_its_carriers_share() -> None:
    for name, operation in OPERATION_CATALOG.items():
        rest = {REST_MUTATION_MANIFEST[c] for c in operation.carriers if c in REST_MUTATION_MANIFEST}
        assert len(rest) == 1, f"{name}: REST carriers decide it by {sorted(rest)}"
        (intent,) = rest
        assert intent in WORKFLOW_ACTIONS, f"{name}: {intent} is not projected to the GUI"
        for tool in operation.carriers & MUTATION_TOOL_MANIFEST.keys():
            assert intent in MUTATION_TOOL_MANIFEST[tool].intents, f"{name}: {tool} is not authorized as {intent}"


def test_every_candidate_and_stress_write_is_a_catalog_operation() -> None:
    writes = {row.operation_id for row in CANDIDATE_ROWS if row.operation_id in REST_MUTATION_MANIFEST}
    assert writes - OPERATION_CATALOG.keys() == set()
    tools = {name for name in MUTATION_TOOL_MANIFEST if name.startswith(("change_set_", "analysis_"))}
    carried = {carrier for operation in OPERATION_CATALOG.values() for carrier in operation.carriers}
    assert tools - carried == set()


def _carried_by(carrier: str) -> set[str]:
    return {name for name, operation in OPERATION_CATALOG.items() if carrier in operation.carriers}


def test_what_a_request_states_is_carried_by_the_write_it_is_sent_to() -> None:
    commands = {
        op for one in get_args(CanvasCommand.__value__) for op in get_args(one.__dataclass_fields__["op"].type)
    }
    replace = {COMPOSE, GENERATE, *commands, *SECTION_OPERATIONS.values()}
    assert replace <= _carried_by("diagrams_replace_diagram")
    assert replace <= _carried_by("artifact_replace_diagram")
    assert set(SECTION_OPERATIONS.values()) <= _carried_by("diagrams_patch_diagram_layout")
    intents = {_literal(one, "intent") for one in get_args(get_args(ArrangeIntent)[0])}
    assert intents == INTENT_OPERATIONS.keys()
    arranged = {name for names in INTENT_OPERATIONS.values() for name in names}
    assert arranged <= _carried_by("diagrams_arrange_diagram_layout") & _carried_by("artifact_arrange_diagram")
    edits = {f"change_set.{_literal(one)}" for one in get_args(get_args(RecordedEdit)[0])}
    assert edits <= _carried_by("changes_record_operation") & _carried_by("change_set_record")
