"""A write result reports its verification's errors as messages, and nothing else as one."""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.write.artifact_write.types import WriteResult


def _result(verification: dict | None) -> WriteResult:
    return WriteResult(False, Path("x.md"), "ADR@1.a", None, [], verification)


def test_only_errors_are_messages() -> None:
    result = _result({"valid": False, "issues": [
        {"severity": "error", "code": "E1", "message": "refused"},
        {"severity": "warning", "code": "W1", "message": "noted"},
    ]})

    assert result.error_messages == ["refused"]


def test_a_result_without_verification_refused_nothing() -> None:
    assert _result(None).error_messages == [] and _result({"valid": True}).error_messages == []
