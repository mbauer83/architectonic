"""Every mutation outcome the use cases can return has an MCP answer.

``_envelope`` promises, in its own docstring, that "a new outcome then reaches every tool at once,
instead of falling through to the success branch in whichever tool was missed". It could not keep
that promise while its parameter was typed ``Any`` and its branches were an ``isinstance`` chain:
nothing checked the chain against the union, so a member could be — and was — absent from it.

``MutationEntityInUse`` was that member. It has been part of ``MutationResult`` and handled by the
REST adapter since node deletion learned to refuse, and ``_envelope`` never mentioned it, so
deleting a node another analysis referenced fell past every branch into ``_ok`` and raised
``AttributeError: 'MutationEntityInUse' object has no attribute 'payload'`` in front of the caller.
The REST surface answered the refusal properly for the same delete; only MCP crashed.

These are the outcomes, one by one. The type checker is the primary guard now — the parameter is
the union and the branches are a ``match``, so a new member fails ``zuban`` before it fails a
caller — and this holds the behaviour the types alone cannot state: that each outcome maps to the
*right* code, with the data a caller acts on.
"""

from __future__ import annotations

import pytest

from src.application.assurance import mutations
from src.infrastructure.mcp.assurance_mcp._write_envelopes import _envelope
from src.infrastructure.mcp.assurance_mcp.context import AssuranceContext


@pytest.fixture()
def ctx() -> AssuranceContext:
    return AssuranceContext()


def _error(answer: dict[str, object]) -> dict[str, object]:
    body = answer["error"]
    assert isinstance(body, dict), f"answered flat, or not a refusal at all: {answer}"
    return body


def test_a_node_another_analysis_references_is_refused_rather_than_crashing(
    ctx: AssuranceContext,
) -> None:
    """The regression. This raised AttributeError before the outcome had a branch."""
    outcome = mutations.MutationEntityInUse(
        node_id="HAZ@1", referencing_analysis_ids=("ANL@1", "ANL@2")
    )

    body = _error(_envelope(outcome, ctx))

    assert body["code"] == "entity_in_use"
    assert body["path"] == "node_id"
    # The borrowers travel with the refusal: "in use" without them is a dead end, because removing
    # those references is the caller's next step and searching for them re-derives what we knew.
    assert body["details"] == {
        "node_id": "HAZ@1",
        "referencing_analysis_ids": ["ANL@1", "ANL@2"],
    }
    assert "2 other analyses" in str(body["message"])


def test_the_singular_reference_reads_as_one_analysis(ctx: AssuranceContext) -> None:
    outcome = mutations.MutationEntityInUse(node_id="HAZ@1", referencing_analysis_ids=("ANL@1",))

    assert "1 other analysis" in str(_error(_envelope(outcome, ctx))["message"])


@pytest.mark.parametrize(
    ("outcome", "code"),
    [
        (mutations.MutationLocked(), "assurance_store_locked"),
        (mutations.MutationNotFound("HAZ@9"), "not_found"),
        (mutations.MutationLegacyInvalid(node_id="HAZ@1"), "node_legacy_invalid"),
        (
            mutations.MutationRejected(field="node_type", value="wrong", message="unknown type"),
            "validation_error",
        ),
        (
            mutations.MutationEntityInUse(node_id="HAZ@1", referencing_analysis_ids=("ANL@1",)),
            "entity_in_use",
        ),
        (
            mutations.MutationDuplicateEdge(
                edge_id="EDG@1", source_id="HAZ@1", target_id="LOS@1", conn_type="leads-to"
            ),
            "duplicate_edge",
        ),
        (
            mutations.MutationIllegalPair(
                source_type="loss", target_type="hazard", conn_type="acts-on", legal_types=()
            ),
            "illegal_connection_type",
        ),
    ],
)
def test_every_refusal_answers_its_own_code(
    outcome: mutations.EdgeMutationResult, code: str, ctx: AssuranceContext
) -> None:
    assert _error(_envelope(outcome, ctx))["code"] == code


def test_a_success_is_not_dressed_as_a_refusal(ctx: AssuranceContext) -> None:
    answer = _envelope(mutations.MutationOk(payload={"node_id": "HAZ@1"}, findings=[]), ctx)

    assert answer == {"node_id": "HAZ@1"}


def test_verification_findings_ride_along_with_a_success(ctx: AssuranceContext) -> None:
    """Writes are never blocked by the verifier, so its findings travel inside the success."""
    answer = _envelope(
        mutations.MutationOk(payload={"node_id": "HAZ@1"}, findings=[{"code": "A001"}]), ctx
    )

    assert answer["verification_findings"] == [{"code": "A001"}]
