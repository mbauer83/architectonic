"""Which findings keep a document from being written: the one decision every document write asks."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification.artifact_verifier_rules import unresolvable_id_link_issues
from src.application.verification.artifact_verifier_types import Issue, Severity, SeverityLiteral, VerificationResult
from src.infrastructure.write.artifact_write.verify import (
    document_write_allowed,
    refuses_a_document_write,
)

_TABLE_IN_PROGRESS = ("W162", "W163", "W164", "W165", "W166", "W167", "W168")


def _issue(severity: SeverityLiteral, code: str) -> Issue:
    return Issue(severity, code, f"{code} found", "doc.md")


def _verified(*issues: Issue) -> VerificationResult:
    return VerificationResult(path=Path("doc.md"), file_type="document", issues=list(issues))


@pytest.mark.parametrize("code", ["E154", "E162", "E163"])
def test_an_error_refuses(code: str) -> None:
    assert refuses_a_document_write(_issue(Severity.ERROR, code))


def test_an_unresolvable_link_refuses() -> None:
    assert refuses_a_document_write(_issue(Severity.WARNING, "W155"))


def test_a_link_written_with_an_id_that_names_nothing_refuses_and_names_the_link() -> None:
    found = unresolvable_id_link_issues(["REQ@1.gone", "GOL@2.gone"], "doc.md")

    assert [issue.code for issue in found] == ["W155", "W155"]
    assert ["'REQ@1.gone'" in found[0].message, "'GOL@2.gone'" in found[1].message] == [True, True]
    assert not document_write_allowed(_verified(*found))


@pytest.mark.parametrize("code", _TABLE_IN_PROGRESS)
def test_a_table_still_being_filled_in_does_not_refuse(code: str) -> None:
    assert not refuses_a_document_write(_issue(Severity.WARNING, code))


@pytest.mark.parametrize("code", ["W156", "W157", "W150"])
def test_every_other_warning_still_refuses(code: str) -> None:
    assert refuses_a_document_write(_issue(Severity.WARNING, code))


def test_a_document_is_written_only_when_no_finding_refuses() -> None:
    linked, in_progress = _issue(Severity.WARNING, "W155"), _issue(Severity.WARNING, "W165")

    assert not document_write_allowed(_verified(linked, in_progress))
    assert not document_write_allowed(_verified(in_progress, _issue(Severity.ERROR, "E162")))
    assert document_write_allowed(_verified(in_progress)) and document_write_allowed(_verified())
