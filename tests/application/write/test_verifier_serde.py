"""Tests for _verifier_serde.py.

Covers: deserialize_result (all return paths), results_from_state, merge_results.
"""

from __future__ import annotations

from pathlib import Path

from src.application.verification._verifier_serde import (
    deserialize_result,
    merge_results,
    results_from_state,
)
from src.application.verification.artifact_verifier_incremental import FileInventory
from src.application.verification.artifact_verifier_types import (
    IncrementalState,
    Severity,
    VerificationResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_inventory(paths: list[Path]) -> FileInventory:
    inv = FileInventory(repo_path=Path("/repo"), include_diagrams=True)
    inv.rel_to_path = {p.name: p for p in paths}
    inv.path_to_rel = {p: p.name for p in paths}
    inv.ordered_paths = [p.name for p in paths]
    return inv


def _state(results: dict[str, dict]) -> IncrementalState:
    return IncrementalState(
        schema_version=1,
        engine_signature="sig",
        include_diagrams=True,
        git_head="abc123",
        snapshots={},
        results=results,
    )


def _valid_result_dict(file_type: str = "entity") -> dict:
    return {
        "file_type": file_type,
        "issues": [
            {"severity": "error", "code": "E001", "message": "bad", "location": "line 1"},
        ],
    }


# ---------------------------------------------------------------------------
# deserialize_result
# ---------------------------------------------------------------------------


class TestDeserializeResult:
    def test_valid_entity_result(self, tmp_path: Path) -> None:
        path = tmp_path / "entity.md"
        result = deserialize_result(path, _valid_result_dict("entity"))
        assert result is not None
        assert result.file_type == "entity"
        assert len(result.issues) == 1
        assert result.issues[0].code == "E001"

    def test_valid_connection_result(self, tmp_path: Path) -> None:
        path = tmp_path / "conn.md"
        result = deserialize_result(path, _valid_result_dict("connection"))
        assert result is not None
        assert result.file_type == "connection"

    def test_valid_diagram_result(self, tmp_path: Path) -> None:
        path = tmp_path / "diag.puml"
        result = deserialize_result(path, _valid_result_dict("diagram"))
        assert result is not None
        assert result.file_type == "diagram"

    def test_unknown_file_type_returns_none(self, tmp_path: Path) -> None:
        path = tmp_path / "file.md"
        result = deserialize_result(path, {"file_type": "unknown", "issues": []})
        assert result is None

    def test_missing_file_type_returns_none(self, tmp_path: Path) -> None:
        result = deserialize_result(tmp_path / "x.md", {"issues": []})
        assert result is None

    def test_issues_not_list_returns_none(self, tmp_path: Path) -> None:
        result = deserialize_result(
            tmp_path / "x.md", {"file_type": "entity", "issues": "not-a-list"}
        )
        assert result is None

    def test_issue_not_dict_returns_none(self, tmp_path: Path) -> None:
        result = deserialize_result(
            tmp_path / "x.md", {"file_type": "entity", "issues": ["bad-item"]}
        )
        assert result is None

    def test_invalid_severity_returns_none(self, tmp_path: Path) -> None:
        result = deserialize_result(
            tmp_path / "x.md",
            {
                "file_type": "entity",
                "issues": [{"severity": "critical", "code": "X", "message": "m", "location": "l"}],
            },
        )
        assert result is None

    def test_non_string_code_returns_none(self, tmp_path: Path) -> None:
        result = deserialize_result(
            tmp_path / "x.md",
            {
                "file_type": "entity",
                "issues": [{"severity": "error", "code": 42, "message": "m", "location": "l"}],
            },
        )
        assert result is None

    def test_empty_issues_list(self, tmp_path: Path) -> None:
        result = deserialize_result(tmp_path / "x.md", {"file_type": "entity", "issues": []})
        assert result is not None
        assert result.issues == []
        assert result.valid is True

    def test_warning_severity_accepted(self, tmp_path: Path) -> None:
        result = deserialize_result(
            tmp_path / "x.md",
            {
                "file_type": "entity",
                "issues": [{"severity": "warning", "code": "W001", "message": "warn", "location": "l1"}],
            },
        )
        assert result is not None
        assert result.issues[0].severity == Severity.WARNING


# ---------------------------------------------------------------------------
# results_from_state
# ---------------------------------------------------------------------------


class TestResultsFromState:
    def test_returns_deserialized_results(self, tmp_path: Path) -> None:
        p = tmp_path / "e.md"
        inv = _empty_inventory([p])
        state = _state({p.name: _valid_result_dict("entity")})
        results = results_from_state(state, inv)
        assert results is not None
        assert len(results) == 1
        assert results[0].path == p

    def test_returns_none_when_result_missing(self, tmp_path: Path) -> None:
        p = tmp_path / "e.md"
        inv = _empty_inventory([p])
        state = _state({})  # no entry for p
        results = results_from_state(state, inv)
        assert results is None

    def test_returns_none_when_result_not_dict(self, tmp_path: Path) -> None:
        p = tmp_path / "e.md"
        inv = _empty_inventory([p])
        state = _state({p.name: "not-a-dict"})  # type: ignore[dict-item]
        results = results_from_state(state, inv)
        assert results is None

    def test_returns_none_when_deserialization_fails(self, tmp_path: Path) -> None:
        p = tmp_path / "e.md"
        inv = _empty_inventory([p])
        state = _state({p.name: {"file_type": "unknown", "issues": []}})
        results = results_from_state(state, inv)
        assert results is None

    def test_empty_inventory_returns_empty_list(self) -> None:
        inv = _empty_inventory([])
        state = _state({})
        results = results_from_state(state, inv)
        assert results == []


# ---------------------------------------------------------------------------
# merge_results
# ---------------------------------------------------------------------------


class TestMergeResults:
    def test_fresh_result_takes_priority(self, tmp_path: Path) -> None:
        p = tmp_path / "e.md"
        inv = _empty_inventory([p])
        state = _state({p.name: _valid_result_dict("entity")})
        fresh = VerificationResult(path=p, file_type="entity", issues=[])
        merged = merge_results(state, inv, [fresh])
        assert merged == [fresh]

    def test_falls_back_to_cached_when_no_fresh(self, tmp_path: Path) -> None:
        p = tmp_path / "e.md"
        inv = _empty_inventory([p])
        state = _state({p.name: _valid_result_dict("entity")})
        merged = merge_results(state, inv, [])
        assert len(merged) == 1
        assert merged[0].path == p

    def test_returns_fresh_when_cached_missing(self, tmp_path: Path) -> None:
        p = tmp_path / "e.md"
        inv = _empty_inventory([p])
        state = _state({})  # no cached entry
        fresh = VerificationResult(path=p, file_type="entity", issues=[])
        merged = merge_results(state, inv, [fresh])
        # fresh result is returned since we can't fall back to cache
        assert fresh in merged

    def test_returns_fresh_when_cached_not_dict(self, tmp_path: Path) -> None:
        p = tmp_path / "e.md"
        inv = _empty_inventory([p])
        state = _state({p.name: "bad"})  # type: ignore[dict-item]
        fresh = VerificationResult(path=p, file_type="entity", issues=[])
        merged = merge_results(state, inv, [fresh])
        assert merged == [fresh]

    def test_returns_fresh_when_deserialization_fails(self, tmp_path: Path) -> None:
        p = tmp_path / "e.md"
        inv = _empty_inventory([p])
        state = _state({p.name: {"file_type": "bad", "issues": []}})
        fresh = VerificationResult(path=p, file_type="entity", issues=[])
        merged = merge_results(state, inv, [fresh])
        assert merged == [fresh]
