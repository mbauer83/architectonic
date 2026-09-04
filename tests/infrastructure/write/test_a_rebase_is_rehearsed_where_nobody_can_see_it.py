"""A rebase rehearsal reads and writes in a throwaway worktree, never in the enterprise checkout.

`change_rebase` decides; this is the binding that gives it a real place to try. The classification's
own cases are covered against records; what is left to prove here is the containment — that a
rehearsal which writes, and one which ends in conflicts, both leave the checkout as they found it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.application.modeling.proposal_edit import ProposalEdit
from src.infrastructure.write.artifact_write.rebase_rehearsal import rehearse_against, rehearsing
from tests.support.git_workflow_fixtures import build_workflow_pair, git, write_entity

TARGET = "REQ@1000001601.RbsTgt.rebase-target"


@pytest.fixture()
def enterprise(tmp_path: Path) -> Path:
    _, repo = build_workflow_pair(tmp_path)
    write_entity(repo, TARGET, "Rebase Target")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "target")
    return repo


def _state(repo: Path) -> dict[str, str]:
    return {
        "branch": git(repo, "rev-parse", "--abbrev-ref", "HEAD"),
        "head": git(repo, "rev-parse", "HEAD"),
        "status": subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True
        ).stdout,
    }


def _edit(**fields) -> ProposalEdit:
    return ProposalEdit(kind="entity", artifact_id=TARGET, fields=fields)


def test_the_rehearsal_runs_in_a_different_directory(enterprise: Path) -> None:
    with rehearsing(enterprise, start_point="HEAD") as worktree:
        assert worktree != enterprise
        assert worktree.exists()
        assert (worktree / ".git").exists()


def test_a_rehearsal_that_writes_leaves_the_checkout_untouched(enterprise: Path) -> None:
    """The containment property, with a replay that actually writes a file."""
    before = _state(enterprise)
    written: list[Path] = []

    def apply_edit(worktree: Path, edit: ProposalEdit) -> str | None:
        target = worktree / "written-by-the-rehearsal.md"
        target.write_text(f"{edit.artifact_id}\n", encoding="utf-8")
        written.append(target)
        return None

    with rehearsing(enterprise, start_point="HEAD") as worktree:
        rehearse_against(
            worktree,
            [("PCH@1.a", _edit(name="Renamed"))],
            read_current=lambda _w, _id: _present(),
            apply_edit=apply_edit,
        )

    assert written and not written[0].exists(), "the worktree went, and the file with it"
    assert not (enterprise / "written-by-the-rehearsal.md").exists()
    assert _state(enterprise) == before


def test_a_rehearsal_full_of_conflicts_leaves_the_checkout_untouched(enterprise: Path) -> None:
    before = _state(enterprise)

    with rehearsing(enterprise, start_point="HEAD") as worktree:
        rehearsed = rehearse_against(
            worktree,
            [("PCH@1.a", _edit(name="Renamed")), ("PCH@1.b", _edit(status="retired"))],
            read_current=lambda _w, _id: _present(),
            apply_edit=lambda _w, _e: "E999 refused by the verifier",
        )

    assert len(rehearsed.with_outcome("conflicting")) == 2
    assert not rehearsed.can_proceed
    assert _state(enterprise) == before


def test_the_capabilities_are_given_the_worktree_not_the_checkout(enterprise: Path) -> None:
    """The whole point of threading the path through: a reader bound to the live index would answer
    from the checkout this exists to avoid."""
    seen: list[Path] = []

    with rehearsing(enterprise, start_point="HEAD") as worktree:
        rehearse_against(
            worktree,
            [("PCH@1.a", _edit(name="Renamed"))],
            read_current=lambda w, _id: (seen.append(w), _present())[1],
            apply_edit=lambda w, _e: seen.append(w) or None,
        )

    assert seen and all(path == worktree for path in seen)
    assert enterprise not in seen


def _present():
    from src.domain.ontology_representation.artifact_types import EntityRecord

    return EntityRecord(
        artifact_id=TARGET,
        artifact_type="requirement",
        name="Rebase Target",
        version="0.1.0",
        status="draft",
        domain="motivation",
        subdomain="requirement",
        path=Path("/unused"),
        keywords=(),
        extra={},
        content_text="## Rebase Target\n\nx\n\n## Properties\n\n",
        display_blocks={},
        display_label="Rebase Target",
        display_alias="rebase_target",
    )
