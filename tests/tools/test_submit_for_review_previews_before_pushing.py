"""``artifact_submit_for_review`` previews by default, and the preview cannot lie.

The tool pushes a branch to a **shared remote** — the one write on this surface whose effect leaves
the machine — and it took neither ``dry_run`` nor ``confirm``, while its sibling
``artifact_withdraw_changes`` took ``confirm`` and ``artifact_help`` advertised
"all create/edit tools default to dry_run=true for safe preview". A caller following that convention
got a push.

Asserted against a **real bare remote** rather than a mocked git: "nothing was pushed" is only worth
testing if a push would have been observable, and a stubbed ``push_enterprise_branch`` would pass
this file no matter what the tool did.

The last two tests are the ones that keep the preview honest. A preview is only useful if it refuses
exactly what the live call refuses, so the checks live in one function
(``enterprise_git_ops.submission_preflight``) that the push itself calls — and one test pins the
messages to each other rather than to a literal, while the other proves the push still routes
through it and has not grown a second copy.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.infrastructure.git import enterprise_git_ops, enterprise_sync_state
from src.infrastructure.mcp.artifact_mcp.write.sync_ops import artifact_submit_for_review
from tests.support.git_workflow_fixtures import build_workflow_pair, git, write_entity


@pytest.fixture()
def enterprise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An enterprise repo with committed work on a working branch, ready to submit."""
    _engagement, enterprise_root = build_workflow_pair(tmp_path)
    monkeypatch.setattr(
        "src.infrastructure.rest.routers.state.maybe_enterprise_root", lambda: enterprise_root
    )
    enterprise_git_ops.ensure_working_branch(enterprise_root)
    write_entity(enterprise_root, "REQ@1000001102.SubRvw.submit-work", "Submit Work")
    enterprise_git_ops.commit_enterprise_work(enterprise_root, "work to submit")
    return enterprise_root


def _remote_heads(tmp_path: Path) -> str:
    origin = tmp_path / "enterprise-origin.git"
    return subprocess.run(
        ["git", "-C", str(origin), "for-each-ref", "refs/heads"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_the_default_call_pushes_nothing(enterprise: Path, tmp_path: Path) -> None:
    branch = enterprise_sync_state.load(enterprise).branch
    assert branch is not None

    answer = artifact_submit_for_review()

    assert answer["ok"] is True
    assert answer["dry_run"] is True
    assert answer["pushed"] is False
    assert answer["branch"] == branch
    # The remote is the only witness that matters.
    assert branch not in _remote_heads(tmp_path)
    # And the aggregate has not been moved to `pending` by a preview.
    assert enterprise_sync_state.load(enterprise).is_accumulating()


def test_dry_run_false_actually_submits(enterprise: Path, tmp_path: Path) -> None:
    branch = enterprise_sync_state.load(enterprise).branch
    assert branch is not None

    answer = artifact_submit_for_review(dry_run=False)

    assert answer["ok"] is True
    assert answer["dry_run"] is False
    assert answer["pushed"] is True
    assert answer["branch"] == branch
    assert branch in _remote_heads(tmp_path)
    assert enterprise_sync_state.load(enterprise).is_pending()


def test_an_already_submitted_branch_reports_that_it_pushed_nothing(enterprise: Path) -> None:
    artifact_submit_for_review(dry_run=False)

    answer = artifact_submit_for_review(dry_run=False)

    assert answer["already_submitted"] is True
    # `pushed` is the key `artifact_save_changes` already uses for "did a push happen"; this branch
    # never pushes, and said nothing about it before.
    assert answer["pushed"] is False


def test_the_preview_refuses_exactly_what_the_submission_refuses(enterprise: Path, tmp_path: Path) -> None:
    """An uncommitted change: both answers must be the same refusal, not two similar sentences."""
    write_entity(enterprise, "REQ@1000001103.Unsavd.unsaved-work", "Unsaved Work")

    previewed = artifact_submit_for_review()
    submitted = artifact_submit_for_review(dry_run=False)

    assert previewed["ok"] is False
    assert previewed == submitted
    assert "unsaved changes" in str(previewed["error"])
    assert _remote_heads(tmp_path).count("arch/work-") == 0


def test_the_submission_still_routes_through_the_preflight(
    enterprise: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The delegation, not just its result: a second copy of the checks would pass every test above.

    Without this, `push_enterprise_branch` could stop calling `submission_preflight` — or keep its own
    inline copy of the conditions — and the preview would drift out of agreement silently, which is
    the whole failure this shared function exists to prevent.
    """
    sentinel = RuntimeError("preflight was consulted")

    def refuse(_root: Path) -> str:
        raise sentinel

    monkeypatch.setattr(enterprise_git_ops, "submission_preflight", refuse)

    with pytest.raises(RuntimeError) as raised:
        enterprise_git_ops.push_enterprise_branch(enterprise)

    assert raised.value is sentinel


def test_a_detached_head_is_reported_rather_than_pushed(enterprise: Path) -> None:
    git(enterprise, "checkout", "--detach")

    answer = artifact_submit_for_review()

    assert answer["ok"] is False
    assert "detached HEAD" in str(answer["error"])
