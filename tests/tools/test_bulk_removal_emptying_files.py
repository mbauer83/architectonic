"""Two removals in one batch, each emptying its own outgoing file.

Observed against a *stale* running backend: one of the two silently did not happen, and the batch
reported success with neither warning nor error for it. A removal that reports success without
happening is the failure this suite already pins from a different cause, so the shape is worth
holding whatever the outcome here.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.mcp.artifact_mcp.bulk_tools import artifact_bulk_write


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    return root


def _make(repo: Path, artifact_type: str, name: str) -> str:
    r = mcp.artifact_create_entity(artifact_type=artifact_type, name=name, dry_run=False, repo_root=str(repo))
    assert r["wrote"], r
    return str(r["artifact_id"])


def test_two_removals_that_each_empty_their_file_both_happen(repo: Path) -> None:
    target = _make(repo, "requirement", "The Target")
    first = _make(repo, "application-component", "First Source")
    second = _make(repo, "application-component", "Second Source")
    for src in (first, second):
        r = mcp.artifact_add_connection(
            source_entity=src, connection_type="archimate-realization", target_entity=target,
            dry_run=False, repo_root=str(repo),
        )
        assert r["wrote"], r

    payload = artifact_bulk_write(
        items=[
            {"op": "edit_connection", "source_entity": src, "connection_type": "archimate-realization",
             "target_entity": target, "operation": "remove"}
            for src in (first, second)
        ],
        dry_run=False, return_mode="full", repo_root=str(repo),
    )

    assert payload["failed_count"] == 0, payload
    surviving = [
        p for p in (repo / "model").rglob("*.outgoing.md")
        if "archimate-realization" in p.read_text(encoding="utf-8")
    ]
    assert surviving == [], f"a removal reported success without happening: {[p.name for p in surviving]}"
