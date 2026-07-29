"""Tests for rewrite_document_links_for_moved_entity and its wiring into
artifact_edit_entity's group-move / rename path.

Regression coverage for a real bug found while grouping the self-model
(WU-C3-style entity re-homing): moving an entity to a different
model-project group changes its file path, but nothing rewrote hand-authored
`[label](../../model/.../X.md)` links to it from document bodies elsewhere in
the repo — the link silently broke (W155) even though the move itself
succeeded.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.mcp import mcp_artifact_server as mcp
from src.infrastructure.write.artifact_write._entity_rename import rewrite_document_links_for_moved_entity


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (root / "model").mkdir(parents=True)
    (root / "diagram-catalog" / "diagrams").mkdir(parents=True)
    (root / "docs").mkdir(parents=True)
    return root


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Unit: pure rewrite over a docs tree
# ---------------------------------------------------------------------------


def test_rewrites_relative_link_pointing_at_moved_entity(repo: Path) -> None:
    old_path = repo / "model" / "motivation" / "requirement" / "REQ@1.a.x.md"
    new_path = repo / "projects" / "my-group" / "model" / "motivation" / "requirement" / "REQ@1.a.x.md"
    doc = repo / "docs" / "standard" / "STD@1.a.y.md"
    _write(doc, "See [req](../../model/motivation/requirement/REQ@1.a.x.md) for details.\n")

    changed = rewrite_document_links_for_moved_entity(repo_root=repo, old_path=old_path, new_path=new_path)

    assert changed == [doc]
    assert "../../projects/my-group/model/motivation/requirement/REQ@1.a.x.md" in doc.read_text()


def test_leaves_unrelated_links_untouched(repo: Path) -> None:
    old_path = repo / "model" / "motivation" / "requirement" / "REQ@1.a.x.md"
    new_path = repo / "projects" / "my-group" / "model" / "motivation" / "requirement" / "REQ@1.a.x.md"
    doc = repo / "docs" / "standard" / "STD@1.a.y.md"
    original = (
        "See [other](../../model/motivation/requirement/REQ@2.b.z.md) and "
        "[external](https://example.com) and [anchor](#section).\n"
    )
    _write(doc, original)

    changed = rewrite_document_links_for_moved_entity(repo_root=repo, old_path=old_path, new_path=new_path)

    assert changed == []
    assert doc.read_text() == original


def test_no_docs_root_is_a_noop(tmp_path: Path) -> None:
    repo = tmp_path / "engagements" / "ENG-T" / "architecture-repository"
    (repo / "model").mkdir(parents=True)
    changed = rewrite_document_links_for_moved_entity(
        repo_root=repo,
        old_path=repo / "model" / "a.md",
        new_path=repo / "projects" / "g" / "model" / "a.md",
    )
    assert changed == []


# ---------------------------------------------------------------------------
# End-to-end: artifact_edit_entity(group=...) triggers the rewrite
# ---------------------------------------------------------------------------


def test_entity_group_move_rewrites_document_link(repo: Path) -> None:
    r = mcp.artifact_create_entity(artifact_type="requirement", name="Probe", dry_run=False, repo_root=str(repo))
    eid = r["artifact_id"]
    old_path = Path(r["path"])

    doc = repo / "docs" / "standard" / "STD@1.a.probe.md"
    rel = "../../" + old_path.relative_to(repo).as_posix()
    _write(doc, f"See [req]({rel}) for details.\n")

    result = mcp.artifact_edit_entity(artifact_id=eid, group="my-group", dry_run=False, repo_root=str(repo))
    assert result["wrote"], result

    new_path = Path(result["path"])
    new_rel = "../../" + new_path.relative_to(repo).as_posix()
    assert new_rel in doc.read_text()
    assert rel not in doc.read_text()
