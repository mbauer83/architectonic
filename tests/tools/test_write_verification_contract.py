"""The verification report's contract, held against the thing that produces it.

`WriteResultResponse.verification` was `dict[str, Any]`, so every mutation the surface serves
published `additionalProperties: true` for it inside a model whose docstring says it is closed. The
open-model fitness function read `model_config` and could not see it.

Closing it needs the same two tests `test_document_reference_contract.py` needs, for the same reason:
a field set pinned to the producer, so the DTO cannot be written from a guess, and the reduced shapes
the write layer emits directly, so an optional field is optional because a producer omits it rather
than because it looked safer that way. The end-to-end half is already covered — the write routes
validate their response against this model, and `test_gui_router_diagram_write_viewpoint.py` and
`test_entity_edit_short_id.py` read `verification.valid` out of a real one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.application.verification._issue_serialization import (
    as_issue_dict,
    as_verification_result_dict,
)
from src.application.verification.artifact_verifier_types import (
    Issue,
    Severity,
    VerificationResult,
)
from src.infrastructure.rest.contracts.verification import (
    VerificationIssueResponse,
    WriteVerificationResponse,
)


def test_the_report_declares_exactly_the_fields_its_serializer_emits() -> None:
    produced = as_verification_result_dict(
        VerificationResult(path=Path("/repo/x.md"), file_type="entity", issues=[])
    )
    assert set(WriteVerificationResponse.model_fields) == set(produced)
    assert WriteVerificationResponse.model_validate(produced).valid is True


def test_the_issue_declares_exactly_the_fields_its_serializer_emits() -> None:
    """``as_issue_dict`` attaches ``details``/``actions`` only when the rule supplied them, so the
    fullest issue is the one that pins the field set."""
    produced = as_issue_dict(
        Issue(
            severity=Severity.ERROR,
            code="E332",
            message="type reference unresolved",
            location="DATATY@1.a.b",
            details={"classifier": "CLF@1.a.c", "candidates": ["x"]},
            actions=({"type": "create_connection", "connection_type": "realization"},),
        )
    )
    assert set(VerificationIssueResponse.model_fields) == set(produced)
    issue = VerificationIssueResponse.model_validate(produced)
    assert issue.details == {"classifier": "CLF@1.a.c", "candidates": ["x"]}
    assert issue.actions == [{"type": "create_connection", "connection_type": "realization"}]


def test_an_issue_without_a_rule_payload_validates() -> None:
    """Most rules attach neither, and the write layer's own literals omit ``location`` as well — an
    issue about the artifact as a whole has nothing to point at."""
    produced = as_issue_dict(
        Issue(severity=Severity.WARNING, code="E100", message="advisory", location="")
    )
    assert "details" not in produced and "actions" not in produced
    assert VerificationIssueResponse.model_validate(produced).details is None
    assert VerificationIssueResponse.model_validate(
        {"severity": "error", "code": "duplicate_artifact", "message": "taken"}
    ).location is None


def test_a_report_for_a_write_that_never_reached_a_file_validates() -> None:
    """``artifact_write/document.py:345`` and ``admin_diagram_ops.py:60`` emit a verdict with no
    ``path`` — there is no file to name for a refused duplicate or a dry run. Optional because a
    producer omits it, which is the only reason a field here may be."""
    assert WriteVerificationResponse.model_validate({"valid": True, "issues": []}).path is None
    assert (
        WriteVerificationResponse.model_validate(
            {"file_type": "diagram", "valid": True, "issues": []}
        ).file_type
        == "diagram"
    )


def test_the_report_and_its_issues_reject_a_field_the_contract_does_not_declare() -> None:
    """The regression. An open blob accepted anything and told a client nothing; a closed one that
    still accepted anything would be the same contract with a better docstring."""
    for payload, model in (
        ({"valid": True, "issues": [], "invented": 1}, WriteVerificationResponse),
        ({"severity": "error", "code": "c", "message": "m", "invented": 1}, VerificationIssueResponse),
    ):
        with pytest.raises(ValidationError):
            model.model_validate(payload)


def test_only_the_rule_owned_levels_of_the_report_are_open() -> None:
    """Openness is per level: the report and the issue are determinate, and ``details``/``actions``
    are written by whichever rule raised the finding — including rules a diagram-type module
    contributes, which is why enumerating them here would be the wrong place to do it."""
    assert WriteVerificationResponse.model_json_schema()["additionalProperties"] is False
    issue_schema = VerificationIssueResponse.model_json_schema()
    assert issue_schema["additionalProperties"] is False
    open_properties = {
        name
        for name, property_schema in issue_schema["properties"].items()
        if "additionalProperties" in str(property_schema)
    }
    assert open_properties == {"details", "actions"}
