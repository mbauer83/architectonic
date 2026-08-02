"""MCP and REST describe a failure with the same word.

The two surfaces cannot share an error *shape*: REST has an HTTP envelope and MCP is JSON-RPC, so
MCP answers in band with ``{"error": {code, path, message}}``. They can share the vocabulary, and
until 0.2.0 they did not — MCP said ``execution-timeout``, ``derivation-limit`` and
``binding-cardinality-violation`` where REST said ``traversal_time_budget_exceeded`` and
``binding_cardinality_violation``, so an agent reading both surfaces saw two names for one thing.

This holds the one that remains: every code ``mcp.execution_failure`` can emit is a member of the
REST surface's closed ``ErrorCode``. A new MCP failure that invents a word fails here rather than
reaching a client, and a code renamed on the REST side fails here rather than silently leaving MCP
behind.
"""

from __future__ import annotations

from typing import get_args

import pytest

from src.application.viewpoints.parameter_binding import ViewpointParameterError
from src.domain.viewpoints.viewpoint_binding_evaluation import BindingCardinalityError
from src.infrastructure.mcp import execution_failure as failures
from src.infrastructure.rest.contracts.errors import ERROR_DETAIL_TYPES, ErrorCode

REST_CODES = frozenset(get_args(ErrorCode))


def _emitted() -> list[dict[str, object]]:
    """One answer from every constructor the module offers."""
    return [
        failures.rejected_parameter(ViewpointParameterError("parameter-type-mismatch", "anchor")),
        failures.rejected_input("query: unknown key(s)"),
        failures.binding_cardinality(BindingCardinalityError("anchor", "exactly one", 3)),
        failures.traversal_budget_exceeded("the traversal exceeded its time budget"),
    ]


def test_the_rest_vocabulary_is_the_one_this_test_compares_against() -> None:
    # A closed union that stopped resolving would make every assertion below vacuous.
    assert REST_CODES, "ErrorCode resolved to nothing"
    assert REST_CODES == frozenset(ERROR_DETAIL_TYPES)


@pytest.mark.parametrize("answer", _emitted())
def test_every_mcp_error_code_is_a_rest_error_code(answer: dict[str, object]) -> None:
    body = answer["error"]
    assert isinstance(body, dict)
    assert body["code"] in REST_CODES, body


@pytest.mark.parametrize("answer", _emitted())
def test_every_mcp_error_carries_a_path_and_a_message(answer: dict[str, object]) -> None:
    """``path`` is what MCP has instead of the envelope's ``details.field_errors[].field``."""
    body = answer["error"]
    assert isinstance(body, dict)
    assert body["path"], body
    assert body["message"], body


def test_a_rejected_parameter_names_the_parameter_in_its_path() -> None:
    answer = failures.rejected_parameter(ViewpointParameterError("missing-parameter", "anchor"))

    assert answer["error"]["path"] == "parameters/anchor"
    # The finer distinction lives in the message, exactly as it does on the REST surface.
    assert "missing-parameter" in answer["error"]["message"]


def test_both_traversal_bounds_answer_the_one_budget_code() -> None:
    """Time and relationship count are one code: the caller's remedy is the same either way."""
    timeout = failures.traversal_budget_exceeded("elapsed time exceeded")
    ceiling = failures.traversal_budget_exceeded("relationship ceiling reached", path="max_hops")

    assert timeout["error"]["code"] == "traversal_time_budget_exceeded"
    assert ceiling["error"]["code"] == "traversal_time_budget_exceeded"
