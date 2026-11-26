"""`artifact_verify` reports a body whose generated header the renderer no longer states (W387).

A stored body keeps a copy of the renderer's statements — palette, glyphs, relationship styles, the
label width bound — and only an edit restates it. So after an upgrade that changed any of them, every
diagram nobody had edited since kept drawing the old styling, and the check an author runs passed: only
the development gate `generate_static_includes --check` could name them.

The stale state is made here the way an upgrade makes it: the stored body states a skinparam the
renderer states differently today. Nothing else about the diagram changes, so any warning is this one.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.rendering.generate_static_includes import stale_generated_headers

_STATED = "skinparam defaultTextAlignment center"
_SUPERSEDED = "skinparam defaultTextAlignment left"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-HDR" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


@pytest.fixture
def diagram(repo: Path) -> tuple[str, Path]:
    goal = mcp.artifact_create_entity(
        artifact_type="goal", name="A goal", summary="Why it exists", dry_run=False, repo_root=str(repo),
    )
    assert goal["wrote"], goal
    created = mcp.artifact_create_diagram(
        diagram_type="archimate-motivation", name="Untouched since", entity_ids=[goal["artifact_id"]],
        dry_run=False, repo_root=str(repo),
    )
    assert created["wrote"], created
    return str(created["artifact_id"]), Path(created["path"])


def _codes(repo: Path, path: Path) -> list[str]:
    verified = asyncio.run(mcp.artifact_verify(path=str(path), repo_root=str(repo), repo_scope="engagement"))
    return [issue["code"] for issue in verified["issues"]]


def _age(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(_STATED) == 1, "the fixture no longer states what this test ages"
    path.write_text(text.replace(_STATED, _SUPERSEDED), encoding="utf-8")


def test_a_current_header_is_not_reported(repo: Path, diagram: tuple[str, Path]) -> None:
    _, path = diagram

    assert "W387" not in _codes(repo, path)


def test_a_superseded_header_is_reported(repo: Path, diagram: tuple[str, Path]) -> None:
    _, path = diagram
    _age(path)

    assert "W387" in _codes(repo, path)


def test_the_development_gate_and_verification_agree(repo: Path, diagram: tuple[str, Path]) -> None:
    """One question, one answer: the CLI gate asks the same predicate the rule does."""
    _, path = diagram
    assert stale_generated_headers(repo) == []
    _age(path)

    assert stale_generated_headers(repo) == [str(path.relative_to(repo / "diagram-catalog" / "diagrams"))]


def test_the_named_remedy_clears_it(repo: Path, diagram: tuple[str, Path]) -> None:
    """The message says an edit restates the header; an edit that changes nothing else must do it."""
    artifact_id, path = diagram
    _age(path)

    edited = mcp.artifact_edit_diagram(artifact_id=artifact_id, puml="auto-sync", dry_run=False, repo_root=str(repo))

    assert edited["wrote"], edited
    assert "W387" not in _codes(repo, path)
