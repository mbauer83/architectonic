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
from src.infrastructure.mcp.assurance_mcp import _refusals as refusals
from src.infrastructure.mcp.refusal_details import FieldRejection
from src.infrastructure.rest.contracts.errors import ERROR_DETAIL_TYPES, ErrorCode

REST_CODES = frozenset(get_args(ErrorCode))


def _emitted() -> list[dict[str, object]]:
    """One answer from every constructor either module offers.

    Both, because the assurance surface used to have its own error shape and its own words for
    refusals the architecture surface already had names for. It now builds through the same
    `failure()`, so the same assertions cover it — which is the point of having merged them.
    """
    return [
        failures.rejected_parameter(
            ViewpointParameterError("type-mismatch", "anchor", "expected entity-id, got boolean")
        ),
        failures.rejected_input("query: unknown key(s)"),
        failures.binding_cardinality(BindingCardinalityError("anchor", "exactly one", 3)),
        failures.traversal_budget_exceeded("the traversal exceeded its time budget"),
        refusals.store_locked(),
        refusals.not_found("ASR@1", path="node_id"),
        refusals.not_found("ANL@1", path="analysis_id"),
        refusals.rejected_field("name", "An analysis requires a non-empty name."),
        refusals.rejected_fields(
            [FieldRejection(field="severity", message="not on the scale")], path="factor"
        ),
        refusals.legacy_invalid("ASR@1", "assign_provenance"),
        refusals.duplicate_edge("EDG@1", "ASR@1", "ASR@2", "leads-to"),
        refusals.illegal_connection_type("loss", "hazard", "acts-on", ["leads-to"]),
        refusals.illegal_connection_type("loss", "hazard", "acts-on", []),
        refusals.entity_in_use("ASR@1", ["ANL@1", "ANL@2"]),
        refusals.not_a_failure_mode("ASR@1"),
        refusals.provenance_immutable("ASR@1", "ANL@1"),
        refusals.signal_mutation_denied("signals_not_colocated", "Signals live elsewhere."),
        refusals.classification_ceiling_exceeded("ASR@1", "TLP:RED", "TLP:AMBER"),
        refusals.aggregate_invariant("missing_name", "An analysis requires a non-empty name."),
        refusals.aggregate_invariant(
            "analysis_not_empty", "It still authors 3 nodes.", subject="ANL@1", count=3
        ),
        refusals.bind_invalid("invalid_binding_status", "The node is already bound."),
        refusals.bind_invalid("unknown_arch_type", "No such architecture type."),
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


@pytest.mark.parametrize("answer", _emitted())
def test_every_mcp_error_nests_its_code_rather_than_answering_flat(
    answer: dict[str, object],
) -> None:
    """One shape, so a client does not have to know which mount answered it.

    The assurance tools answered ``{"error": "not_found", "node_id": …}`` — the code where the
    object goes, and the data spread across sibling keys. A client branching on ``error.code``
    read `None` and fell through to the success path; the coverage walk had to carry a third
    branch to notice a refusal at all, and for a while did not, so assurance refusals counted as
    passes. A flat answer is a test failure here rather than a client's surprise.
    """
    body = answer["error"]
    assert isinstance(body, dict), f"answered flat: {answer}"
    assert set(body) <= {"code", "path", "message", "details"}, body
    assert isinstance(body["message"], str)


def test_details_are_absent_rather_than_empty_when_a_code_declares_none() -> None:
    """Mirrors REST, where a code with nothing structured to add maps to ``None``, not ``{}``."""
    assert "details" not in failures.rejected_input("query: unknown key(s)")["error"]
    assert "details" not in refusals.store_locked()["error"]
    assert refusals.entity_in_use("ASR@1", ["ANL@1"])["error"]["details"] == {
        "node_id": "ASR@1",
        "referencing_analysis_ids": ["ANL@1"],
    }


def test_the_four_words_only_the_assurance_surface_knew_are_gone() -> None:
    """`invalid_value`, `invalid_request` and `invalid_factor_assessment` were all field rejections.

    Three private words for the one thing the closed vocabulary calls ``validation_error``. The
    fourth, ``classification_ceiling_exceeded``, was a real distinction and became a member instead
    — withholding a node from a session is not the same fact as refusing to publish an argument.
    """
    retired = {"invalid_value", "invalid_request", "invalid_factor_assessment"}
    assert retired.isdisjoint(REST_CODES)

    for answer in _emitted():
        assert answer["error"]["code"] not in retired, answer

    assert refusals.rejected_field("field", "message")["error"]["code"] == "validation_error"
    assert "classification_ceiling_exceeded" in REST_CODES


def test_a_rejected_parameter_names_the_parameter_in_its_path() -> None:
    answer = failures.rejected_parameter(
        ViewpointParameterError("missing", "anchor", "a required parameter with no default was not supplied")
    )

    assert answer["error"]["path"] == "parameters/anchor"
    # The message is a sentence about the expectation the value failed, not a code word. It used to
    # carry `missing-parameter` — the hyphenated code this release retired — which put the retired
    # vocabulary back on the wire in prose while `code` already said `validation_error`.
    assert answer["error"]["message"] == "anchor: a required parameter with no default was not supplied"
    assert "missing-parameter" not in answer["error"]["message"]


def test_both_traversal_bounds_answer_the_one_budget_code() -> None:
    """Time and relationship count are one code: the caller's remedy is the same either way."""
    timeout = failures.traversal_budget_exceeded("elapsed time exceeded")
    ceiling = failures.traversal_budget_exceeded("relationship ceiling reached", path="max_hops")

    assert timeout["error"]["code"] == "traversal_time_budget_exceeded"
    assert ceiling["error"]["code"] == "traversal_time_budget_exceeded"
