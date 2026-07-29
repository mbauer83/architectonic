"""Tests for the Issue diagnostic contract (details/actions extension).

Covers: Issue construction with details+actions; round-trip through the
MCP/REST serializer (as_issue_dict / as_verification_result_dict); and the
incremental-cache serialize+deserialize path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.application.verification._verifier_serde import deserialize_result
from src.application.verification.artifact_verifier_incremental import serialize_result
from src.application.verification.artifact_verifier_types import Issue, Severity, VerificationResult
from src.infrastructure.mcp.artifact_mcp.formatting import as_issue_dict, as_verification_result_dict

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _base_issue(severity: str = Severity.ERROR) -> Issue:
    return Issue(severity=severity, code="E999", message="test msg", location="file.md:1")


def _issue_with_details() -> Issue:
    return Issue(
        severity=Severity.ERROR,
        code="E330",
        message="missing backing relation",
        location="diag.puml:10",
        details={"dob_source": "DOB@1.a", "dob_target": "DOB@2.b", "dt_relationship_kind": "association"},
        actions=({"type": "create_connection", "connection_type": "archimate-association"},),
    )


# ---------------------------------------------------------------------------
# Issue construction
# ---------------------------------------------------------------------------


class TestIssueConstruction:
    def test_defaults_are_none(self) -> None:
        issue = _base_issue()
        assert issue.details is None
        assert issue.actions is None

    def test_details_and_actions_set(self) -> None:
        issue = _issue_with_details()
        assert issue.details is not None
        assert issue.details["dob_source"] == "DOB@1.a"
        assert issue.actions is not None
        assert issue.actions[0]["type"] == "create_connection"

    def test_frozen_immutability(self) -> None:
        issue = _base_issue()
        with pytest.raises((AttributeError, TypeError)):
            issue.code = "X"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MCP/REST serializer — as_issue_dict
# ---------------------------------------------------------------------------


class TestAsIssueDict:
    def test_base_issue_no_extra_keys(self) -> None:
        d = as_issue_dict(_base_issue())
        assert set(d.keys()) == {"severity", "code", "message", "location"}

    def test_details_included_when_set(self) -> None:
        d = as_issue_dict(_issue_with_details())
        assert "details" in d
        assert d["details"]["dob_source"] == "DOB@1.a"

    def test_actions_included_when_set(self) -> None:
        d = as_issue_dict(_issue_with_details())
        assert "actions" in d
        assert isinstance(d["actions"], list)
        assert d["actions"][0]["type"] == "create_connection"

    def test_warning_severity_preserved(self) -> None:
        issue = Issue(
            severity=Severity.WARNING, code="W001", message="warn", location="x:1",
            details={"hint": "check this"}
        )
        d = as_issue_dict(issue)
        assert d["severity"] == "warning"
        assert d["details"] == {"hint": "check this"}


class TestAsVerificationResultDict:
    def test_issues_include_details(self) -> None:
        result = VerificationResult(
            path=Path("dummy.puml"), file_type="diagram", issues=[_issue_with_details()]
        )
        d = as_verification_result_dict(result)
        assert d["valid"] is False
        issues = d["issues"]
        assert len(issues) == 1
        assert issues[0]["details"]["dt_relationship_kind"] == "association"
        assert issues[0]["actions"][0]["type"] == "create_connection"


# ---------------------------------------------------------------------------
# Incremental cache round-trip: serialize_result → deserialize_result
# ---------------------------------------------------------------------------


class TestCacheRoundTrip:
    def test_base_issue_round_trips(self, tmp_path: Path) -> None:
        path = tmp_path / "entity.md"
        result = VerificationResult(path=path, file_type="entity", issues=[_base_issue()])
        data = serialize_result(result)
        restored = deserialize_result(path, data)
        assert restored is not None
        assert len(restored.issues) == 1
        issue = restored.issues[0]
        assert issue.code == "E999"
        assert issue.details is None
        assert issue.actions is None

    def test_issue_with_details_round_trips(self, tmp_path: Path) -> None:
        path = tmp_path / "diag.puml"
        result = VerificationResult(path=path, file_type="diagram", issues=[_issue_with_details()])
        data = serialize_result(result)
        restored = deserialize_result(path, data)
        assert restored is not None
        issue = restored.issues[0]
        assert issue.details is not None
        assert issue.details["dob_source"] == "DOB@1.a"
        assert issue.actions is not None
        assert len(issue.actions) == 1
        assert issue.actions[0]["type"] == "create_connection"

    def test_missing_details_key_gives_none(self, tmp_path: Path) -> None:
        path = tmp_path / "e.md"
        data = {
            "file_type": "entity",
            "issues": [{"severity": "error", "code": "E001", "message": "m", "location": "l"}],
        }
        restored = deserialize_result(path, data)
        assert restored is not None
        assert restored.issues[0].details is None
        assert restored.issues[0].actions is None

    def test_malformed_details_ignored(self, tmp_path: Path) -> None:
        path = tmp_path / "e.md"
        data = {
            "file_type": "entity",
            "issues": [
                {
                    "severity": "error",
                    "code": "E001",
                    "message": "m",
                    "location": "l",
                    "details": "not-a-dict",
                    "actions": "also-not-a-list",
                }
            ],
        }
        restored = deserialize_result(path, data)
        assert restored is not None
        assert restored.issues[0].details is None
        assert restored.issues[0].actions is None
