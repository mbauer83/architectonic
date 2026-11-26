"""The local-operator gate is declared on the route-policy row, and the served route enforces it.

The gate lived in two handler bodies, each building its own 403, and the manifest said nothing about it:
a policy built from the manifest would have read `PUT /api/sync/credentials` as a non-mutating write any
caller may make. Now a row states `gate="local_operator"` and its route declares `require_local_operator`;
these hold the two to each other in both directions, through an oracle neither produces — the served
OpenAPI document, where the dependency's one footprint is the operator header it declares.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.infrastructure.backend.arch_backend_app import _build_app
from src.infrastructure.rest.contracts.operator_request import OPERATOR_REQUEST_HEADER
from src.infrastructure.rest.route_policy import ROUTE_POLICY


@pytest.fixture(scope="module")
def operations() -> dict[str, dict[str, Any]]:
    paths = _build_app().openapi().get("paths", {})
    return {
        operation["operationId"]: operation
        for methods in paths.values() for operation in methods.values() if "operationId" in operation
    }


def _asks_for_the_operator_header(operation: dict[str, Any]) -> bool:
    return any(
        parameter.get("in") == "header" and parameter.get("name") == OPERATOR_REQUEST_HEADER
        for parameter in operation.get("parameters", [])
    )


def test_every_gated_row_is_served_behind_the_gate_and_no_other(operations: dict[str, dict[str, Any]]) -> None:
    gated = {row.operation_id for row in ROUTE_POLICY if row.gate == "local_operator"}
    served_behind_it = {name for name, operation in operations.items() if _asks_for_the_operator_header(operation)}

    assert gated == served_behind_it
    assert gated >= {"sync_supply_credentials", "assurance_reload_store"}


def test_a_gated_operation_publishes_the_refusal(operations: dict[str, dict[str, Any]]) -> None:
    for row in ROUTE_POLICY:
        if row.gate == "local_operator":
            assert "403" in operations[row.operation_id]["responses"], row.operation_id


def test_holding_a_credential_is_a_process_write_not_a_non_mutating_one() -> None:
    (row,) = (row for row in ROUTE_POLICY if row.operation_id == "sync_supply_credentials")
    assert row.mutation_domain == "process"
