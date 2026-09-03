"""The submission in flight survives a save and load, and an unreadable one is not dropped.

The whole point of persisting a submission before the push is that a crash between the push and the
local write is recoverable. That only holds if the record comes back — and if a record that cannot be
read surfaces as a problem rather than as "no submission in flight", which would leave a review
branch on the remote that nothing local reconciles and let the next submission open a second one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.domain.submission_phase import PreparedSubmission, SubmissionIntent
from src.infrastructure.git import enterprise_sync_state as state


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / ".arch").mkdir()
    return tmp_path


def _prepared() -> PreparedSubmission:
    return PreparedSubmission(
        intent=SubmissionIntent(("PCH@1.a", "PCH@1.b"), "arch/work-20260903-100000", "abc1234")
    )


def _write(root: Path, payload: dict) -> None:
    (root / ".arch" / "enterprise-sync.json").write_text(json.dumps(payload), encoding="utf-8")


def test_a_state_with_no_submission_is_the_ordinary_one(root: Path) -> None:
    assert state.load(root).submission is None


def test_a_prepared_submission_survives_a_save_and_load(root: Path) -> None:
    saved = state.EnterpriseSyncState(status="pending", branch="arch/work-1", submission=_prepared())
    state._persist_unlocked(root, state.EnterpriseSyncState(), saved)

    loaded = state.load(root)

    assert loaded.submission == _prepared()
    assert loaded.submission.intent.proposal_ids == ("PCH@1.a", "PCH@1.b")


def test_each_phase_survives_a_save_and_load(root: Path) -> None:
    """Every arm, because the phase is what reconciliation dispatches on."""
    prepared = _prepared()
    for phase in (prepared, prepared.pushed(at="t1"), prepared.pushed(at="t1").submitted(at="t2")):
        saved = state.EnterpriseSyncState(status="pending", submission=phase)
        state._persist_unlocked(root, state.EnterpriseSyncState(), saved)
        assert state.load(root).submission == phase, phase


def test_a_state_file_predating_submissions_loads_with_none(root: Path) -> None:
    """The field is new. An existing workspace's file has no `submission` key at all."""
    _write(root, {"version": 2, "status": "pending", "branch": "arch/work-1", "commits_behind": 0})

    loaded = state.load(root)

    assert loaded.submission is None
    assert loaded.status == "pending"
    assert loaded.branch == "arch/work-1"
    assert not loaded.is_blocked


@pytest.mark.parametrize(
    "record",
    [
        {"phase": "prepared"},
        {"phase": "invented", "proposal_ids": ["a"], "branch": "b", "expected_commit": "c"},
        {"phase": "pushed", "proposal_ids": ["a"], "branch": "b", "expected_commit": "c"},
        {"proposal_ids": ["a"], "branch": "b", "expected_commit": "c"},
        "not a mapping",
        [],
    ],
)
def test_an_unreadable_submission_surfaces_as_corrupt_not_as_none(root: Path, record) -> None:
    """The dangerous reading. "No submission in flight" is what an operator acts on, and acting on it
    when a branch is under review is how a second one gets opened."""
    _write(root, {"version": 3, "status": "pending", "submission": record})

    loaded = state.load(root)

    assert loaded.is_blocked, loaded
    assert loaded.health is not None
    assert loaded.health.reason == "state_file_corrupt"
    assert loaded.submission is None


def test_the_schema_version_moved_with_the_field(root: Path) -> None:
    """A file written now declares 3. The reader tolerates 2, which is why no migration is needed —
    an absent submission is a valid state, not a missing one."""
    state._persist_unlocked(
        root, state.EnterpriseSyncState(), state.EnterpriseSyncState(status="pending", submission=_prepared())
    )
    written = json.loads((root / ".arch" / "enterprise-sync.json").read_text(encoding="utf-8"))

    assert written["version"] == state.SCHEMA_VERSION == 3
    assert written["submission"]["phase"] == "prepared"
    assert written["submission"]["proposal_ids"] == ["PCH@1.a", "PCH@1.b"]
