"""Serialization helpers for Issue and VerificationResult to plain dicts."""

from typing import Any

from src.application.verification.artifact_verifier import Issue, VerificationResult


def as_issue_dict(issue: Issue) -> dict[str, Any]:
    d: dict[str, Any] = {
        "severity": issue.severity,
        "code": issue.code,
        "message": issue.message,
        "location": issue.location,
    }
    if issue.details is not None:
        d["details"] = dict(issue.details)
    if issue.actions is not None:
        d["actions"] = [dict(a) for a in issue.actions]
    return d


def as_verification_result_dict(result: VerificationResult) -> dict[str, Any]:
    return {
        "path": str(result.path),
        "file_type": result.file_type,
        "valid": result.valid,
        "issues": [as_issue_dict(i) for i in result.issues],
    }
