"""Advice is a third severity: never an error, never a warning, tallied on its own.

And the acknowledgement it may carry: stored under `accepted-advice`, read and written by one module,
refused for anything that is not advice.
"""

from __future__ import annotations

from pathlib import Path
from typing import get_args

import pytest

from src.application.verification.artifact_verifier_types import VerificationResult
from src.domain.verification_advice import (
    ADVICE_CODES,
    AcceptedAdvice,
    AdviceAcknowledgementRefused,
    accepted_advice_from_frontmatter,
    accepted_advice_to_frontmatter,
    advice_issue,
    checked_acknowledgements,
    issue_presentation,
    presentation_for,
)
from src.domain.verification_findings import Issue, Severity, SeverityLiteral, count_severities


def _advice(status: str = "draft") -> Issue:
    return advice_issue("A341", "may be a function", location="x.md", artifact_id="PRC@1.a.p", status=status)


def test_the_severity_vocabulary_is_exactly_three() -> None:
    assert set(get_args(SeverityLiteral)) == {"error", "warning", "advice"}
    assert Severity.ADVICE == "advice"


def test_advice_is_neither_an_error_nor_a_warning_and_never_invalidates() -> None:
    result = VerificationResult(Path("x.md"), "entity", [_advice()])

    assert result.valid
    assert result.errors == [] and result.warnings == []
    assert result.advice == result.issues


def test_each_severity_is_counted_on_its_own() -> None:
    issues = [
        Issue(Severity.ERROR, "E340", "m", "l"),
        Issue(Severity.WARNING, "W307", "m", "l"),
        Issue(Severity.WARNING, "W307", "m", "l"),
        _advice(),
    ]
    counts = count_severities(i.severity for i in issues)
    assert (counts.errors, counts.warnings, counts.advice) == (1, 2, 1)
    assert VerificationResult(Path("x"), "entity", issues).counts == counts


@pytest.mark.parametrize(("status", "presentation"), [
    ("draft", "marker"), ("active", "listed"), ("deprecated", "marker"), ("unheard-of", "listed"),
])
def test_prominence_follows_the_element_status(status: str, presentation: str) -> None:
    assert presentation_for(status) == presentation
    assert issue_presentation(_advice(status)) == presentation


def test_an_error_or_a_warning_has_no_advice_presentation() -> None:
    assert issue_presentation(Issue(Severity.ERROR, "E340", "m", "l")) is None
    assert issue_presentation(Issue(Severity.WARNING, "W307", "m", "l")) is None


def test_an_advice_issue_names_its_element_and_status() -> None:
    issue = advice_issue("A341", "m", location="l", artifact_id="PRC@1.a.p", status="active", parts=("a", "b"))
    assert issue.details == {"artifact_id": "PRC@1.a.p", "status": "active", "parts": ["a", "b"]}


def test_an_undeclared_code_cannot_be_raised_as_advice() -> None:
    with pytest.raises(ValueError, match="not a declared advice code"):
        advice_issue("W307", "m", location="l", artifact_id="x", status="draft")


# ── acknowledgement ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("code", ["E340", "W307", "A999", ""])
def test_only_advice_can_be_acknowledged(code: str) -> None:
    with pytest.raises(AdviceAcknowledgementRefused):
        checked_acknowledgements([{"code": code, "reason": "deliberate"}])


def test_acknowledging_a_warning_says_it_is_a_warning() -> None:
    with pytest.raises(AdviceAcknowledgementRefused, match="W307 is a warning: only advice"):
        checked_acknowledgements([{"code": "W307", "reason": "deliberate"}])


@pytest.mark.parametrize("entry", [
    {"code": "A341"}, {"code": "A341", "reason": "  "}, {"code": "A341", "reason": "x" * 281}, "A341", {"reason": "r"},
])
def test_an_acknowledgement_needs_a_short_reason_and_a_shape(entry: object) -> None:
    with pytest.raises(AdviceAcknowledgementRefused):
        checked_acknowledgements([entry])


def test_one_code_is_acknowledged_once() -> None:
    with pytest.raises(AdviceAcknowledgementRefused, match="more than once"):
        checked_acknowledgements([{"code": "A341", "reason": "a"}, {"code": "A341", "reason": "b"}])


def test_a_list_is_required() -> None:
    with pytest.raises(AdviceAcknowledgementRefused):
        checked_acknowledgements({"code": "A341", "reason": "r"})


def test_an_empty_list_clears_every_acknowledgement() -> None:
    assert checked_acknowledgements([]) == ()


def test_every_declared_code_round_trips_as_an_acknowledgement() -> None:
    """Over what the syntax permits: any declared code, through check, write and read."""
    asked = [{"code": code, "reason": f"deliberate {code}"} for code in ADVICE_CODES]
    checked = checked_acknowledgements(asked)
    assert accepted_advice_from_frontmatter(accepted_advice_to_frontmatter(checked)) == checked


def test_the_reader_skips_a_malformed_entry_and_keeps_the_rest() -> None:
    stored = [{"code": "A341", "reason": "kept"}, "junk", {"reason": "no code"}, {"code": 7}]
    assert accepted_advice_from_frontmatter(stored) == (AcceptedAdvice("A341", "kept"),)
    assert accepted_advice_from_frontmatter(None) == ()
