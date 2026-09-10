"""Opening a replacement branch leaves the reviewed one published until it is retired.

The existing primitives permitted only *abandon then create*: creation is reachable from `synced`
alone, and abandon deletes the remote ref first. So replacing a branch under review meant deleting
what a reviewer was reading before its successor existed — and a creation that then failed left the
reviewed work gone from the remote with nothing to point at.

Create first, record the old branch as superseded, retire it separately. Every case below is about
the window between those two: what a reviewer can still reach, and what a failure leaves behind.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.infrastructure.git import (
    enterprise_branch_lifecycle as lifecycle,
)
from src.infrastructure.git import (
    enterprise_sync_state,
    git_work_commits,
)
from tests.support.git_workflow_fixtures import build_workflow_pair, git, write_entity


@pytest.fixture()
def submitted(tmp_path: Path) -> tuple[Path, Path, str]:
    """An enterprise repo with a branch pushed and under review."""
    _, enterprise = build_workflow_pair(tmp_path)
    git(enterprise, "push", "origin", "main")
    branch = lifecycle.ensure_working_branch(enterprise)
    write_entity(enterprise, "REQ@1000001501.RepWrk.replacement-work", "Replacement Work")
    git_work_commits.commit_enterprise_work(enterprise, "reviewed work")
    lifecycle.push_enterprise_branch(enterprise)
    return enterprise, tmp_path / "enterprise-origin.git", branch


def _remote_heads(origin: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(origin), "for-each-ref", "refs/heads"], check=True, capture_output=True, text=True
    ).stdout


class TestOpeningOne:
    def test_the_reviewed_branch_stays_on_origin(self, submitted) -> None:
        """The whole point: a reviewer's link still resolves while the replacement is being built."""
        enterprise, origin, reviewed = submitted

        replacement = lifecycle.open_replacement_branch(enterprise, from_head="HEAD")

        assert reviewed in _remote_heads(origin)
        assert replacement != reviewed

    def test_the_checkout_moves_to_the_replacement(self, submitted) -> None:
        enterprise, _origin, _reviewed = submitted

        replacement = lifecycle.open_replacement_branch(enterprise, from_head="HEAD")

        assert git(enterprise, "rev-parse", "--abbrev-ref", "HEAD") == replacement

    def test_both_branches_are_recorded(self, submitted) -> None:
        """One branch work goes to, at most one awaiting retirement — two named roles, not a list."""
        enterprise, _origin, reviewed = submitted

        replacement = lifecycle.open_replacement_branch(enterprise, from_head="HEAD")
        state = enterprise_sync_state.load(enterprise)

        assert state.branch == replacement
        assert state.superseded_branch == reviewed
        assert state.status == "accumulating"

    def test_it_starts_from_the_commit_it_was_given(self, submitted) -> None:
        enterprise, _origin, _reviewed = submitted
        base = git(enterprise, "rev-parse", "HEAD~1")

        lifecycle.open_replacement_branch(enterprise, from_head=base)

        assert git(enterprise, "rev-parse", "HEAD") == base


def test_a_replacement_opened_in_the_same_second_gets_its_own_name(submitted) -> None:
    """Found by these tests before it could be found in use.

    The branch name stamps to the second, which was fine while a branch was only created from
    `synced` — minutes after the last was abandoned. A replacement is opened *while* the branch it
    replaces still exists, so created in the same second the two names collided and `checkout -b`
    refused: `a branch named 'arch/work-…' already exists`. The operation failed exactly when it was
    used quickly, which is how an automated rebase would use it.
    """
    enterprise, _origin, reviewed = submitted

    replacement = lifecycle.open_replacement_branch(enterprise, from_head="HEAD")

    assert replacement != reviewed
    assert reviewed in git(enterprise, "branch", "--list", reviewed), "the reviewed branch still exists"
    assert replacement.startswith("arch/work-")


def test_the_name_steps_past_every_branch_that_still_exists(tmp_path) -> None:
    """One suffix is a coincidence that works once; the loop is what makes it a rule.

    Stated over branches that *still exist*, which is the actual invariant. A name freed by a
    retirement is available again, and reusing it is correct — asserting three distinct names across
    a retirement would have pinned something the design does not promise.
    """
    _, enterprise = build_workflow_pair(tmp_path)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    for taken in (f"arch/work-{stamp}", f"arch/work-{stamp}-2"):
        git(enterprise, "branch", taken)

    opened = lifecycle.ensure_working_branch(enterprise)

    assert opened not in (f"arch/work-{stamp}", f"arch/work-{stamp}-2")
    assert opened.startswith(f"arch/work-{stamp}")


class TestWhenItIsRefused:
    def test_not_while_merely_accumulating(self, tmp_path) -> None:
        """Nothing is published, so there is nothing to preserve — that is `ensure_working_branch`."""
        _, enterprise = build_workflow_pair(tmp_path)
        lifecycle.ensure_working_branch(enterprise)

        with pytest.raises(ValueError, match="under review"):
            lifecycle.open_replacement_branch(enterprise, from_head="HEAD")

    def test_not_when_one_is_already_awaiting_retirement(self, submitted) -> None:
        """A second would lose track of the first, and the first is still on the remote."""
        enterprise, _origin, _reviewed = submitted
        lifecycle.open_replacement_branch(enterprise, from_head="HEAD")
        enterprise_sync_state.replace_lifecycle(
            enterprise, status="pending", branch=enterprise_sync_state.load(enterprise).branch
        )

        with pytest.raises(ValueError, match="awaiting retirement"):
            lifecycle.open_replacement_branch(enterprise, from_head="HEAD")


class TestRetiring:
    def test_it_removes_the_branch_from_origin_and_locally(self, submitted) -> None:
        enterprise, origin, reviewed = submitted
        lifecycle.open_replacement_branch(enterprise, from_head="HEAD")

        retired = lifecycle.retire_superseded_branch(enterprise)

        assert retired == reviewed
        assert reviewed not in _remote_heads(origin)
        assert reviewed not in git(enterprise, "branch", "--list", reviewed)
        assert enterprise_sync_state.load(enterprise).superseded_branch is None

    def test_it_leaves_the_replacement_alone(self, submitted) -> None:
        enterprise, _origin, _reviewed = submitted
        replacement = lifecycle.open_replacement_branch(enterprise, from_head="HEAD")

        lifecycle.retire_superseded_branch(enterprise)

        assert git(enterprise, "rev-parse", "--abbrev-ref", "HEAD") == replacement
        assert enterprise_sync_state.load(enterprise).branch == replacement

    def test_with_nothing_to_retire_it_answers_none(self, submitted) -> None:
        enterprise, _origin, _reviewed = submitted

        assert lifecycle.retire_superseded_branch(enterprise) is None

    def test_it_is_idempotent(self, submitted) -> None:
        """Retirement may be retried after a partial failure, so a second pass must be harmless."""
        enterprise, _origin, _reviewed = submitted
        lifecycle.open_replacement_branch(enterprise, from_head="HEAD")

        first = lifecycle.retire_superseded_branch(enterprise)
        second = lifecycle.retire_superseded_branch(enterprise)

        assert first is not None
        assert second is None

    def test_a_failed_remote_deletion_keeps_the_branch_recorded(self, submitted, monkeypatch) -> None:
        """No claimed retirement: the ref is still there, so the record that tracks it must stay."""
        enterprise, origin, reviewed = submitted
        lifecycle.open_replacement_branch(enterprise, from_head="HEAD")
        real = lifecycle.run_repo_git

        def failing_delete(repo, *args, **kwargs):
            if args[:3] == ("push", "origin", "--delete"):
                return (1, "", "injected remote failure")
            return real(repo, *args, **kwargs)

        monkeypatch.setattr(lifecycle, "run_repo_git", failing_delete)
        with pytest.raises(RuntimeError, match="delete remote branch"):
            lifecycle.retire_superseded_branch(enterprise)

        assert reviewed in _remote_heads(origin)
        assert enterprise_sync_state.load(enterprise).superseded_branch == reviewed

    def test_it_refuses_to_retire_the_branch_work_is_going_to(self, submitted) -> None:
        """A state where both roles name one branch is corrupt; retiring it would delete live work."""
        enterprise, _origin, _reviewed = submitted
        current = enterprise_sync_state.load(enterprise).branch
        enterprise_sync_state.replace_superseded_branch(enterprise, current)

        with pytest.raises(ValueError, match="both as the current branch"):
            lifecycle.retire_superseded_branch(enterprise)


class TestTheRecordSurvivesTheLifecycle:
    def test_a_lifecycle_transition_does_not_retire_by_side_effect(self, submitted) -> None:
        """The superseded branch outlives the transitions that happen while it waits: work
        accumulates on the replacement and that replacement is submitted, and throughout a reviewer
        may still be reading the old one."""
        enterprise, _origin, reviewed = submitted
        replacement = lifecycle.open_replacement_branch(enterprise, from_head="HEAD")

        enterprise_sync_state.replace_lifecycle(enterprise, status="pending", branch=replacement)

        assert enterprise_sync_state.load(enterprise).superseded_branch == reviewed

    def test_it_survives_a_save_and_load(self, submitted) -> None:
        enterprise, _origin, reviewed = submitted
        lifecycle.open_replacement_branch(enterprise, from_head="HEAD")

        assert enterprise_sync_state.load(enterprise).superseded_branch == reviewed


def test_a_state_file_predating_the_field_loads_without_one(tmp_path: Path) -> None:
    """The field is new and additive, which is why no migration step exists: an older file simply
    has no `superseded_branch` key, and absent is the correct value rather than a missing one."""
    (tmp_path / ".arch").mkdir()
    (tmp_path / ".arch" / "enterprise-sync.json").write_text(
        '{"version": 3, "status": "pending", "branch": "arch/work-1", "commits_behind": 0}',
        encoding="utf-8",
    )

    loaded = enterprise_sync_state.load(tmp_path)

    assert loaded.superseded_branch is None
    assert loaded.branch == "arch/work-1"
    assert loaded.status == "pending"
    assert not loaded.is_blocked


class TestNamingAcrossTwoDeployments:
    """Two deployments share an enterprise remote — the arrangement the whole feature is for.

    The name is stamped to the second, and the uniqueness check used to read local refs alone on
    the reasoning that "the remote cannot hold a branch this repository never created". That is
    false here: the other deployment created it. Two submissions in the same second produced the
    same name and the second push refused, reporting someone else's move.
    """

    def test_a_name_the_remote_is_known_to_hold_is_not_reused(self, tmp_path: Path) -> None:
        _, enterprise = build_workflow_pair(tmp_path)
        git(enterprise, "push", "origin", "main")
        taken = lifecycle._new_working_branch_name(enterprise)  # noqa: SLF001
        # Another deployment publishes that name, and this one hears about it on its next fetch.
        git(enterprise, "push", "origin", f"HEAD:refs/heads/{taken}")
        git(enterprise, "fetch", "origin")

        assert lifecycle._new_working_branch_name(enterprise) != taken  # noqa: SLF001

    def test_it_asks_no_remote_to_find_out(self, tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
        """Naming must not put the network in its own path — a round trip per attempt turns a
        hanging remote into a hanging save."""
        from src.infrastructure.git import git_repository_state

        _, enterprise = build_workflow_pair(tmp_path)

        def _refuse(*_args, **_kwargs):  # noqa: ANN002, ANN003, ANN202
            raise AssertionError("naming asked the remote")

        monkeypatch.setattr(git_repository_state, "remote_ref_commit", _refuse)

        assert lifecycle._new_working_branch_name(enterprise)  # noqa: SLF001
