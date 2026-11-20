"""A lift against a scratchpad that has moved on is refused before the model is touched.

A lift writes twice: the model content, through the ordinary write path, and then the scratchpad,
to record on each note what it became. The version was checked only by the second write. A caller
holding a stale token therefore got the entity committed, then a conflict, and notes that did not
say they had been lifted — so the retry the conflict asks for created the same content again.

Driven through the real repository and the real write path on a repository this test creates,
because the property is about what reaches disk, and a recording writer cannot report that.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.infrastructure.mcp.artifact_mcp.scratchpad_tools import (
    scratchpad_create,
    scratchpad_edit,
    scratchpad_lift,
)


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    root = tmp_path / "architecture-repository"
    root.mkdir()
    return root


def _pad_with_a_liftable_note(repo_root: Path) -> dict[str, Any]:
    created = scratchpad_create(name="Q3 thinking", repo_root=str(repo_root))
    assert created["ok"], created
    return _edit(repo_root, created["scratchpad"], {
        "id": "n1", "title": "Grow into mid-market", "destination": "element",
        "element-type": "goal",
    })


def _edit(repo_root: Path, pad: dict[str, Any], note: dict[str, Any]) -> dict[str, Any]:
    stored = scratchpad_edit(
        artifact_id=pad["artifact-id"], version=pad["version"],
        upsert={"notes": [note]},  # type: ignore[arg-type]
        repo_root=str(repo_root),
    )
    assert stored["ok"], stored
    return stored["scratchpad"]


def _model_files(repo_root: Path) -> list[Path]:
    """Everything on disk that is not a scratchpad — which is everything a lift could have added,
    the group registry and the write path's own bookkeeping included."""
    return sorted(
        path for path in repo_root.rglob("*")
        if path.is_file() and not path.name.endswith(".scratchpad.yaml")
    )


def _lift(repo_root: Path, pad: dict[str, Any], *, version: str, **overrides: Any) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "artifact_id": pad["artifact-id"], "selection": ["n1"], "version": version,
        "dry_run": False, "repo_root": str(repo_root), **overrides,
    }
    return scratchpad_lift(**arguments)


class TestALiftAgainstAStaleVersion:
    def test_it_is_refused_as_a_conflict_and_the_model_is_untouched(self, repo_root: Path) -> None:
        read_first = _pad_with_a_liftable_note(repo_root)
        _edit(repo_root, read_first, {"id": "n2", "title": "Someone else's thought"})
        before = _model_files(repo_root)

        answer = _lift(repo_root, read_first, version=read_first["version"])

        assert answer["ok"] is False and answer["error"] == "version_conflict", answer
        assert _model_files(repo_root) == before

    def test_it_creates_no_target_project_either(self, repo_root: Path) -> None:
        read_first = _pad_with_a_liftable_note(repo_root)
        _edit(repo_root, read_first, {"id": "n2", "title": "Someone else's thought"})
        before = _model_files(repo_root)

        answer = _lift(
            repo_root, read_first, version=read_first["version"],
            targets={"unfiled": "a-new-project"},
        )

        assert answer["error"] == "version_conflict", answer
        assert _model_files(repo_root) == before

    def test_the_retry_with_the_current_version_creates_the_content_once(
        self, repo_root: Path
    ) -> None:
        read_first = _pad_with_a_liftable_note(repo_root)
        current = _edit(repo_root, read_first, {"id": "n2", "title": "Someone else's thought"})
        _lift(repo_root, read_first, version=read_first["version"])

        answer = _lift(repo_root, current, version=current["version"])

        assert answer["ok"] and answer["lift"]["committed"], answer
        goals = [path for path in _model_files(repo_root) if "grow-into-mid-market" in path.name]
        assert len(goals) == 1, goals


class TestALiftAgainstTheCurrentVersion:
    @pytest.mark.verifies("REQ@1786223986.VV89psV")
    def test_it_commits_and_the_note_says_what_it_became(self, repo_root: Path) -> None:
        pad = _pad_with_a_liftable_note(repo_root)

        answer = _lift(repo_root, pad, version=pad["version"])

        assert answer["ok"] and answer["lift"]["committed"], answer
        second = _lift(repo_root, pad, version=_bumped(pad["version"]))
        assert second["ok"], second
        assert [item["outcome"] for item in second["lift"]["items"]] == ["skip"]


def _bumped(version: str) -> str:
    major, minor, patch = version.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"
