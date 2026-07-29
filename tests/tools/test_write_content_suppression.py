"""Tests for write response content suppression.

After the _out() change, file content is included in results only when dry_run=True
(or when explicitly overridden with include_content=True). Live writes return only
artifact_id, path, and verification — no full file dump.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.write._common import _out

# ---------------------------------------------------------------------------
# Fake result dataclass for _out() unit tests
# ---------------------------------------------------------------------------


@dataclass
class _FakeResult:
    wrote: bool = True
    path: Path = Path("/tmp/fake.md")
    artifact_id: str = "APP@1.x.y"
    content: str | None = "file content here"
    warnings: list = field(default_factory=list)
    verification: dict | None = None


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


# ---------------------------------------------------------------------------
# _out() unit tests
# ---------------------------------------------------------------------------


class TestOutHelper:
    def test_dry_run_includes_content(self):
        result = _out(_FakeResult(), dry_run=True)
        assert "content" in result
        assert result["content"] == "file content here"

    def test_live_write_suppresses_content(self):
        result = _out(_FakeResult(), dry_run=False)
        assert "content" not in result

    def test_explicit_include_content_true_overrides_dry_run_false(self):
        result = _out(_FakeResult(), dry_run=False, include_content=True)
        assert "content" in result

    def test_explicit_include_content_false_suppresses_on_dry_run(self):
        result = _out(_FakeResult(), dry_run=True, include_content=False)
        assert "content" not in result

    def test_none_content_never_included_regardless_of_dry_run(self):
        r = _FakeResult(content=None)
        assert "content" not in _out(r, dry_run=True)
        assert "content" not in _out(r, dry_run=False)

    def test_always_includes_artifact_id_path_wrote(self):
        for dry in (True, False):
            result = _out(_FakeResult(), dry_run=dry)
            assert "artifact_id" in result
            assert "path" in result
            assert "wrote" in result

    def test_warnings_included_when_present(self):
        r = _FakeResult(warnings=["watch out"])
        result = _out(r, dry_run=False)
        assert result["warnings"] == ["watch out"]

    def test_warnings_absent_when_empty(self):
        result = _out(_FakeResult(warnings=[]), dry_run=False)
        assert "warnings" not in result


# ---------------------------------------------------------------------------
# Integration: artifact_create_entity
# ---------------------------------------------------------------------------


class TestCreateEntityContentSuppression:
    def test_dry_run_includes_content(self, repo: Path) -> None:
        result = mcp.artifact_create_entity(
            artifact_type="requirement",
            name="DryRunContent",
            dry_run=True,
            repo_root=str(repo),
        )
        assert result["wrote"] is False
        assert "content" in result
        assert "DryRunContent" in str(result["content"])

    def test_live_write_omits_content(self, repo: Path) -> None:
        result = mcp.artifact_create_entity(
            artifact_type="requirement",
            name="LiveWriteNoContent",
            dry_run=False,
            repo_root=str(repo),
        )
        assert result["wrote"] is True
        assert "content" not in result

    def test_live_write_still_has_path_and_artifact_id(self, repo: Path) -> None:
        result = mcp.artifact_create_entity(
            artifact_type="outcome",
            name="PathCheck",
            dry_run=False,
            repo_root=str(repo),
        )
        assert Path(str(result["path"])).exists()
        assert result["artifact_id"]


# ---------------------------------------------------------------------------
# Integration: artifact_edit_entity
# ---------------------------------------------------------------------------


class TestEditEntityContentSuppression:
    def _make(self, repo: Path, name: str) -> str:
        r = mcp.artifact_create_entity(artifact_type="requirement", name=name, dry_run=False, repo_root=str(repo))
        return str(r["artifact_id"])

    def test_dry_run_edit_includes_content(self, repo: Path) -> None:
        eid = self._make(repo, "Edit Dry")
        result = mcp.artifact_edit_entity(
            artifact_id=eid,
            summary="Preview summary",
            dry_run=True,
            repo_root=str(repo),
        )
        assert result["wrote"] is False
        assert "content" in result
        assert "Preview summary" in str(result["content"])

    def test_live_edit_omits_content(self, repo: Path) -> None:
        eid = self._make(repo, "Edit Live")
        result = mcp.artifact_edit_entity(
            artifact_id=eid,
            summary="Updated summary",
            dry_run=False,
            repo_root=str(repo),
        )
        assert result["wrote"] is True
        assert "content" not in result

    def test_live_edit_change_is_on_disk(self, repo: Path) -> None:
        eid = self._make(repo, "On Disk Check")
        result = mcp.artifact_edit_entity(
            artifact_id=eid,
            summary="Persisted summary",
            dry_run=False,
            repo_root=str(repo),
        )
        assert "Persisted summary" in Path(str(result["path"])).read_text()


# ---------------------------------------------------------------------------
# Integration: artifact_add_connection
# ---------------------------------------------------------------------------


class TestAddConnectionContentSuppression:
    def _make(self, repo: Path, artifact_type: str, name: str) -> str:
        r = mcp.artifact_create_entity(artifact_type=artifact_type, name=name, dry_run=False, repo_root=str(repo))
        return str(r["artifact_id"])

    def test_dry_run_connection_includes_content(self, repo: Path) -> None:
        src = self._make(repo, "goal", "Src")
        tgt = self._make(repo, "requirement", "Tgt")
        result = mcp.artifact_add_connection(
            source_entity=src,
            connection_type="archimate-influence",
            target_entity=tgt,
            dry_run=True,
            repo_root=str(repo),
        )
        assert result["wrote"] is False
        assert "content" in result

    def test_live_connection_omits_content(self, repo: Path) -> None:
        src = self._make(repo, "goal", "ConnSrc")
        tgt = self._make(repo, "requirement", "ConnTgt")
        result = mcp.artifact_add_connection(
            source_entity=src,
            connection_type="archimate-influence",
            target_entity=tgt,
            dry_run=False,
            repo_root=str(repo),
        )
        assert result["wrote"] is True
        assert "content" not in result
