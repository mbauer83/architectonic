"""Fitness functions over the response and error contracts in the generated OpenAPI document.

The document is the oracle here: it is generated from the handlers' declared models, so it says
what the surface actually promises rather than what anyone intended. The manifest says what it
*should* promise, and ``UNTYPED_RESPONSE_OPERATIONS`` is the difference — a shrink-only list that
is empty when the contract is complete.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.infrastructure.backend.arch_backend_app import _build_app
from src.infrastructure.rest.route_policy import (
    BY_KEY,
    BY_OPERATION,
    UNTYPED_RESPONSE_OPERATIONS,
    RouteRow,
)
from tests.support.response_contract_audit import contract_violation, error_envelope_violations


@pytest.fixture(scope="module")
def document() -> dict[str, Any]:
    return _build_app().openapi()


def _row_for(method: str, path: str) -> RouteRow | None:
    """The manifest row for a served address, or None.

    No legacy fallback: every served address has a row now, and one that does not is a defect the
    inventory assertion below reports rather than something a ledger explains away.
    """
    return BY_KEY.get((method.upper(), path))


def _operations(document: dict[str, Any]) -> list[tuple[RouteRow, dict[str, Any]]]:
    pairs = []
    for path, methods in document.get("paths", {}).items():
        for method, operation in methods.items():
            row = _row_for(method, path)
            assert row is not None, f"{method.upper()} {path} has no route-policy row"
            pairs.append((row, operation))
    return pairs


def test_every_declared_error_status_returns_the_shared_envelope(document: dict[str, Any]) -> None:
    """A published error schema that says ``{"detail": "<string>"}`` while the handler returns an
    object is worse than no schema: a generated client decodes it and fails on real traffic."""
    violations = {
        row.operation_id: statuses
        for row, operation in _operations(document)
        if (statuses := error_envelope_violations(operation))
    }
    assert violations == {}, f"error statuses not documented as the envelope: {violations}"


def test_no_operation_documents_fastapis_default_validation_error(document: dict[str, Any]) -> None:
    """``HTTPValidationError`` is the shape FastAPI would return if the validation handler were
    not installed. Its presence in the document means some operation still advertises it."""
    assert "HTTPValidationError" not in (document.get("components", {}).get("schemas") or {})


def test_operation_ids_come_from_the_manifest(document: dict[str, Any]) -> None:
    """Generation keys its output by operation id, so the id is part of the published contract —
    it must not be FastAPI's function-name-plus-path default, which changes on every rename.

    Every row now, with no exception. Four completeness endpoints used to be collapsing into one
    operation and none could claim the canonical id while all four were mounted; the collapse is
    done."""
    for row, operation in _operations(document):
        assert operation.get("operationId") == row.operation_id


def test_operation_ids_are_unique(document: dict[str, Any]) -> None:
    """OpenAPI requires it, and ``openapi-typescript`` keys its output by it."""
    ids = [operation.get("operationId") for _row, operation in _operations(document)]
    assert len(ids) == len(set(ids))


def test_response_contracts_match_the_manifest_outside_the_pending_list(
    document: dict[str, Any],
) -> None:
    violations = {
        row.operation_id: reason
        for row, operation in _operations(document)
        if row.operation_id not in UNTYPED_RESPONSE_OPERATIONS
        and (reason := contract_violation(row, operation, document.get("components", {}).get("schemas") or {}))
    }
    assert violations == {}, f"declared contract not met: {violations}"


def test_the_pending_response_contract_list_shrinks_only(document: dict[str, Any]) -> None:
    """An operation that now meets its contract has to leave the list in the same commit, or the
    list stops measuring what is left and starts hiding a regression."""
    satisfied = {
        row.operation_id
        for row, operation in _operations(document)
        if row.operation_id in UNTYPED_RESPONSE_OPERATIONS
        and contract_violation(row, operation, document.get("components", {}).get("schemas") or {}) is None
    }
    assert satisfied == set(), (
        f"these now meet their contract and must leave UNTYPED_RESPONSE_OPERATIONS: {sorted(satisfied)}"
    )


def test_the_pending_list_names_only_declared_operations() -> None:
    unknown = UNTYPED_RESPONSE_OPERATIONS - set(BY_OPERATION)
    assert unknown == set(), f"pending list names undeclared operations: {sorted(unknown)}"


def test_no_component_name_carries_a_source_module_path(document: dict[str, Any]) -> None:
    """A published component is named for what it is, never for where its class happens to live.

    FastAPI disambiguates two same-named models by qualifying the component with the Python module
    path, so `CreateGroupBody` in two routers published
    `src__infrastructure__rest__routers__groups__CreateGroupBody` — a name no client can refer to and
    one that changes whenever the package layout does. It changed during this release's regrouping,
    which is the only reason anyone looked. The fix is a distinct class name; the check is that the
    document never leaks the layout again.
    """
    schemas = (document.get("components") or {}).get("schemas") or {}
    leaked = sorted(name for name in schemas if name.startswith("src__") or "__" in name)
    assert leaked == [], (
        "These published components are named after their Python module path. Give the colliding "
        f"models distinct names instead: {leaked}"
    )
