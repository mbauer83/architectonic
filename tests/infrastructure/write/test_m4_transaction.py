from __future__ import annotations

import os
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from src.infrastructure.write.artifact_write.batch_transaction import (
    BatchCommitResult,
    StagingDirectory,
    _derive_manifest,
    _derive_manifest_from_touched_paths,
    commit_staged_repo,
    create_staging_repo,
)
from src.infrastructure.write.artifact_write.m4_transaction import (
    GitRefTransition,
    TransactionRecoveryError,
    recover_transactions,
)
from src.infrastructure.write.artifact_write.staged_workspace import stage_live_path


class SimulatedKill(BaseException):
    pass


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write(repo / "model" / "a.md", "old-a")
    _write(repo / "model" / "delete.md", "old-delete")
    return repo


def _stage_post_state(repo: Path) -> tuple[StagingDirectory, Path]:
    staging, staged_root = create_staging_repo(repo)
    _write(staged_root / "model" / "a.md", "new-a")
    _write(staged_root / "model" / "create.md", "new-create")
    stage_live_path(staged_root / "model" / "delete.md", repo / "model" / "delete.md")
    (staged_root / "model" / "delete.md").unlink()
    return staging, staged_root


def _touched_post_state(staged_root: Path) -> set[Path]:
    return {
        staged_root / "model" / "a.md",
        staged_root / "model" / "create.md",
        staged_root / "model" / "delete.md",
    }


def _assert_pre_state(repo: Path) -> None:
    assert (repo / "model" / "a.md").read_text() == "old-a"
    assert not (repo / "model" / "create.md").exists()
    assert (repo / "model" / "delete.md").read_text() == "old-delete"


def _assert_post_state(repo: Path) -> None:
    assert (repo / "model" / "a.md").read_text() == "new-a"
    assert (repo / "model" / "create.md").read_text() == "new-create"
    assert not (repo / "model" / "delete.md").exists()


def test_tracked_path_manifest_matches_full_tree_diff(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    staging, staged_root = _stage_post_state(repo)
    try:
        tracked_entries, tracked_result = _derive_manifest_from_touched_paths(
            live_root=repo,
            staged_root=staged_root,
            touched_paths=_touched_post_state(staged_root),
        )
        full_entries, full_result = _derive_manifest(live_root=repo, staged_root=staged_root)
    finally:
        staging.cleanup()

    assert tracked_entries == full_entries
    assert tracked_result == full_result


@pytest.mark.parametrize(
    ("boundary", "expected"),
    [
        ("payloads_written", "pre"),
        ("intent_installed", "post"),
        ("entry_applied:0", "post"),
        ("entry_applied:1", "post"),
        ("entry_applied:2", "post"),
        ("done_written", "post"),
        ("index_rebuilt", "post"),
    ],
)
def test_boundary_kill_recovers_to_pre_or_post(
    tmp_path: Path,
    boundary: str,
    expected: str,
) -> None:
    repo = _fixture_repo(tmp_path)
    _staging, staged_root = _stage_post_state(repo)
    rebuilt: list[str] = []

    def kill_at(name: str) -> None:
        if name == boundary:
            raise SimulatedKill

    with pytest.raises(SimulatedKill):
        commit_staged_repo(
            live_root=repo,
            staged_root=staged_root,
            touched_paths=_touched_post_state(staged_root),
            rebuild_index=lambda _result: rebuilt.append("commit"),
            on_boundary=kill_at,
        )

    recover_transactions(repo, rebuild_index=lambda: rebuilt.append("recovery"))
    (_assert_pre_state if expected == "pre" else _assert_post_state)(repo)
    assert not any((repo / ".arch-repo" / "transactions").iterdir())
    if expected == "post":
        assert rebuilt


def test_recovery_is_idempotent_and_delete_replay_ignores_absence(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    _staging, staged_root = _stage_post_state(repo)

    with pytest.raises(SimulatedKill):
        commit_staged_repo(
            live_root=repo,
            staged_root=staged_root,
            touched_paths=_touched_post_state(staged_root),
            rebuild_index=lambda _result: None,
            on_boundary=_kill_on("entry_applied:2"),
        )

    assert not (repo / "model" / "delete.md").exists()
    assert recover_transactions(repo, rebuild_index=lambda: None) == 1
    assert recover_transactions(repo, rebuild_index=lambda: None) == 0
    _assert_post_state(repo)


def test_recovery_fails_closed_on_third_state(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    _staging, staged_root = _stage_post_state(repo)
    with pytest.raises(SimulatedKill):
        commit_staged_repo(
            live_root=repo,
            staged_root=staged_root,
            touched_paths=_touched_post_state(staged_root),
            rebuild_index=lambda _result: None,
            on_boundary=_kill_on("intent_installed"),
        )
    _write(repo / "model" / "a.md", "unexpected-third-state")

    with pytest.raises(TransactionRecoveryError, match="Third state"):
        recover_transactions(repo, rebuild_index=lambda: None)


def test_done_is_durable_before_index_rebuild_and_cleanup(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    _staging, staged_root = _stage_post_state(repo)

    def fail_rebuild(_result: BatchCommitResult) -> None:
        raise RuntimeError("index unavailable")

    with pytest.raises(RuntimeError, match="index unavailable"):
        commit_staged_repo(
            live_root=repo,
            staged_root=staged_root,
            touched_paths=_touched_post_state(staged_root),
            rebuild_index=fail_rebuild,
        )

    transaction = next((repo / ".arch-repo" / "transactions").iterdir())
    assert (transaction / "intent").is_file()
    assert (transaction / "done").read_bytes() == b"done\n"
    _assert_post_state(repo)
    assert recover_transactions(repo, rebuild_index=lambda: None) == 1


def test_staging_and_transaction_are_repo_local(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    staging, staged_root = create_staging_repo(repo)
    assert staged_root.is_relative_to(repo / ".arch-repo" / "transactions")
    staging.cleanup()


def test_symlink_staging_write_does_not_mutate_live_file(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    staging, staged_root = create_staging_repo(repo)
    try:
        staged_file = stage_live_path(staged_root / "model" / "a.md", repo / "model" / "a.md")
        assert staged_file.is_symlink()

        staged_file.write_text("staged-only", encoding="utf-8")

        assert not staged_file.is_symlink()
        assert staged_file.read_text(encoding="utf-8") == "staged-only"
        assert (repo / "model" / "a.md").read_text(encoding="utf-8") == "old-a"
    finally:
        staging.cleanup()


def test_symlink_staging_delete_does_not_mutate_live_file(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    staging, staged_root = create_staging_repo(repo)
    try:
        staged_file = stage_live_path(staged_root / "model" / "a.md", repo / "model" / "a.md")
        staged_file.unlink()

        assert not staged_file.exists()
        assert (repo / "model" / "a.md").read_text(encoding="utf-8") == "old-a"
    finally:
        staging.cleanup()


def test_symlink_staging_rename_does_not_replace_live_destination(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    _write(repo / "model" / "target.md", "live-target")
    staging, staged_root = create_staging_repo(repo)
    try:
        stage_live_path(staged_root / "model" / "a.md", repo / "model" / "a.md")
        stage_live_path(staged_root / "model" / "target.md", repo / "model" / "target.md")
        os.rename(staged_root / "model" / "a.md", staged_root / "model" / "target.md")

        assert (repo / "model" / "a.md").read_text(encoding="utf-8") == "old-a"
        assert (repo / "model" / "target.md").read_text(encoding="utf-8") == "live-target"
        assert (staged_root / "model" / "target.md").read_text(encoding="utf-8") == "old-a"
    finally:
        staging.cleanup()


def test_broken_symlink_materializes_as_absent_for_write(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    staging, staged_root = create_staging_repo(repo)
    try:
        stage_live_path(staged_root / "model" / "a.md", repo / "model" / "a.md")
        (repo / "model" / "a.md").unlink()
        staged_file = staged_root / "model" / "a.md"
        assert staged_file.is_symlink()

        staged_file.write_text("recreated-in-stage", encoding="utf-8")

        assert staged_file.read_text(encoding="utf-8") == "recreated-in-stage"
        assert not (repo / "model" / "a.md").exists()
    finally:
        staging.cleanup()


def test_sparse_staging_does_not_walk_repo_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _fixture_repo(tmp_path)
    for index in range(50):
        _write(repo / "model" / f"extra-{index}.md", f"extra-{index}")
    rglob_calls = 0
    original = Path.rglob

    def counted_rglob(path: Path, pattern: str):
        nonlocal rglob_calls
        rglob_calls += 1
        return original(path, pattern)

    monkeypatch.setattr(Path, "rglob", counted_rglob)
    staging, staged_root = create_staging_repo(repo)
    try:
        assert staged_root.exists()
        assert rglob_calls == 0
    finally:
        staging.cleanup()


def test_transactions_journal_is_gitignored_from_every_commit_path(tmp_path: Path) -> None:
    """The transient journal must never be staged by `git add .` / `git add -A` (no repo .gitignore)."""
    repo = _fixture_repo(tmp_path)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    staging, _staged_root = create_staging_repo(repo)  # creates the journal + .arch-repo/.gitignore

    assert "transactions/" in (repo / ".arch-repo" / ".gitignore").read_text().splitlines()
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout
    assert ".arch-repo/transactions" not in staged
    staging.cleanup()
    # The journal dir stays empty at rest, so the "no pending transactions" invariant still holds.
    assert not any((repo / ".arch-repo" / "transactions").iterdir())


def test_ref_transition_replays_after_kill(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "old")
    old_sha = _git(repo, "rev-parse", "HEAD")
    _write(repo / "model" / "ref.md", "new")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "new")
    new_sha = _git(repo, "rev-parse", "HEAD")
    _git(repo, "reset", "--hard", old_sha)

    _staging, staged_root = create_staging_repo(repo)
    with pytest.raises(SimulatedKill):
        commit_staged_repo(
            live_root=repo,
            staged_root=staged_root,
            touched_paths=set(),
            rebuild_index=lambda _result: None,
            ref_transition=GitRefTransition(branch="main", old_sha=old_sha, new_sha=new_sha),
            on_boundary=_kill_on("ref_updated"),
        )

    assert _git(repo, "rev-parse", "refs/heads/main") == new_sha
    assert recover_transactions(repo, rebuild_index=lambda: None) == 1
    assert _git(repo, "rev-parse", "refs/heads/main") == new_sha


def test_recovery_fails_closed_when_payload_is_missing(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    _staging, staged_root = _stage_post_state(repo)
    with pytest.raises(SimulatedKill):
        commit_staged_repo(
            live_root=repo,
            staged_root=staged_root,
            touched_paths=_touched_post_state(staged_root),
            rebuild_index=lambda _result: None,
            on_boundary=_kill_on("intent_installed"),
        )
    transaction = next((repo / ".arch-repo" / "transactions").iterdir())
    next((transaction / "payloads").iterdir()).unlink()

    with pytest.raises(TransactionRecoveryError, match="Missing payload"):
        recover_transactions(repo, rebuild_index=lambda: None)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _kill_on(boundary: str) -> Callable[[str], None]:
    def callback(name: str) -> None:
        if name == boundary:
            raise SimulatedKill

    return callback
