"""WS8 acceptance tests: git sync via isolated worktree + M4 publish.

Kill matrix: killing at any M4 boundary leaves the repo in a consistent state
(pre or post), never referentially partial. M5 recovery restores correctness.
Writes during sync are rejected with GateRejected (423). Reads are not blocked
during the fetch/worktree phase, only during the M4 publish window.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from src.infrastructure.workspace.mutation_gate import (
    GateRejected,
    WorkspaceMutationGate,
    _reset_for_test,
)
from src.infrastructure.write.artifact_write.m4_transaction import recover_transactions
from tests.infrastructure.write.test_rename_sidecar import SimulatedKill

# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------

def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _init_repo(path: Path, *, initial_branch: str = "main") -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", initial_branch, "--quiet"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


def _commit(repo: Path, message: str, *, files: dict[str, str]) -> str:
    """Write files, stage them, and commit. Returns the new HEAD sha."""
    for rel, content in files.items():
        dest = repo / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", rel], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", message, "--quiet"], cwd=repo, check=True)
    return _git(repo, "rev-parse", "HEAD")


def _setup_origin_and_clone(tmp_path: Path, *, model_file: str = "model/entities/A.md") -> tuple[Path, Path]:
    """Create a bare origin with one commit, then clone it as 'local'."""
    origin = tmp_path / "origin"
    local = tmp_path / "local"
    _init_repo(origin)
    _commit(origin, "initial", files={model_file: "v1\n"})

    subprocess.run(
        ["git", "clone", "--quiet", str(origin), str(local)],
        check=True,
    )
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=local, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=local, check=True)
    return origin, local


# ---------------------------------------------------------------------------
# Boundary-kill helper
# ---------------------------------------------------------------------------

def _on_boundary_kill(kill_at: str) -> Callable[[str], None]:
    def _cb(name: str) -> None:
        if name == kill_at:
            raise SimulatedKill(f"killed at {name}")
    return _cb


# ---------------------------------------------------------------------------
# Core helper: run publish_git_pull_via_m4 synchronously
# ---------------------------------------------------------------------------

def _run_m4_sync(
    repo: Path,
    worktree: Path,
    *,
    branch: str,
    old_sha: str,
    new_sha: str,
    gate: WorkspaceMutationGate,
    on_boundary: Callable[[str], None] | None = None,
) -> None:
    from src.infrastructure.artifact_index import notify_paths_changed
    from src.infrastructure.git.git_sync_m4 import compute_sync_entries, publish_git_pull_via_m4

    def _rebuild() -> None:
        entries = compute_sync_entries(repo, worktree, old_sha, new_sha)
        notify_paths_changed([repo / e.dest for e in entries])

    publish_git_pull_via_m4(
        repo, worktree,
        branch=branch, old_sha=old_sha, new_sha=new_sha,
        gate=gate,
        rebuild_index=_rebuild,
        on_boundary=on_boundary,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_sync_ff_only_happy_path(tmp_path: Path) -> None:
    """ff-only pull via M4 updates files, branch ref, and leaves no transaction dir."""
    origin, local = _setup_origin_and_clone(tmp_path)
    _commit(origin, "upstream change", files={"model/entities/A.md": "v2\n"})
    subprocess.run(["git", "fetch", "origin"], cwd=local, check=True)

    old_sha = _git(local, "rev-parse", "HEAD")
    new_sha = _git(local, "rev-parse", "@{u}")
    worktree = tmp_path / "wt"
    subprocess.run(["git", "worktree", "add", "--detach", str(worktree), new_sha], cwd=local, check=True)

    _reset_for_test()
    gate = WorkspaceMutationGate()
    try:
        with gate.blocking_writes("sync_in_progress"):
            _run_m4_sync(local, worktree, branch="main", old_sha=old_sha, new_sha=new_sha, gate=gate)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=local)

    assert (local / "model" / "entities" / "A.md").read_text() == "v2\n"
    assert _git(local, "rev-parse", "HEAD") == new_sha
    txns = local / ".arch-repo" / "transactions"
    assert not any(True for _ in txns.iterdir()) if txns.exists() else True


@pytest.mark.parametrize(
    ("boundary", "expected_content"),
    [
        ("payloads_written", "v1\n"),
        ("intent_installed", "v2\n"),
        ("entry_applied:0", "v2\n"),
        ("ref_updated", "v2\n"),
        ("done_written", "v2\n"),
        ("index_rebuilt", "v2\n"),
    ],
)
def test_sync_boundary_kill_recovers(tmp_path: Path, boundary: str, expected_content: str) -> None:
    """Kill at any M4 boundary → pre or post state; never partial; M5 recovers."""
    origin, local = _setup_origin_and_clone(tmp_path)
    _commit(origin, "upstream change", files={"model/entities/A.md": "v2\n"})
    subprocess.run(["git", "fetch", "origin"], cwd=local, check=True)

    old_sha = _git(local, "rev-parse", "HEAD")
    new_sha = _git(local, "rev-parse", "@{u}")
    worktree = tmp_path / "wt"
    subprocess.run(["git", "worktree", "add", "--detach", str(worktree), new_sha], cwd=local, check=True)

    _reset_for_test()
    gate = WorkspaceMutationGate()
    with pytest.raises(SimulatedKill):
        with gate.blocking_writes("sync_in_progress"):
            _run_m4_sync(
                local, worktree,
                branch="main", old_sha=old_sha, new_sha=new_sha,
                gate=gate,
                on_boundary=_on_boundary_kill(boundary),
            )

    subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=local)

    recover_transactions(local, rebuild_index=lambda: None)
    assert (local / "model" / "entities" / "A.md").read_text() == expected_content
    final_sha = _git(local, "rev-parse", "HEAD")
    if expected_content == "v1\n":
        assert final_sha == old_sha
    else:
        assert final_sha == new_sha


def test_sync_m5_recovery_idempotent(tmp_path: Path) -> None:
    """recover_transactions is safe to call even when no transaction is pending."""
    origin, local = _setup_origin_and_clone(tmp_path)
    recovered = recover_transactions(local, rebuild_index=lambda: None)
    assert recovered == 0


def test_sync_423_during_sync(tmp_path: Path) -> None:
    """Concurrent write is rejected while sync_in_progress gate is held."""
    _reset_for_test()
    gate = WorkspaceMutationGate()
    with gate.blocking_writes("sync_in_progress"):
        with pytest.raises(GateRejected) as exc_info:
            with gate.writing():
                pass
    assert exc_info.value.reason == "sync_in_progress"


def test_reads_not_blocked_during_intent_phase(tmp_path: Path) -> None:
    """gate.reading() succeeds while sync_in_progress is set (no WRITE held yet)."""
    _reset_for_test()
    gate = WorkspaceMutationGate()
    with gate.blocking_writes("sync_in_progress"):
        with gate.reading():
            pass


def test_sync_no_model_changes_updates_ref(tmp_path: Path) -> None:
    """Pull with only non-model changes still advances the branch ref via M4."""
    origin, local = _setup_origin_and_clone(tmp_path)
    _commit(origin, "non-model change", files={"README.md": "updated\n"})
    subprocess.run(["git", "fetch", "origin"], cwd=local, check=True)

    old_sha = _git(local, "rev-parse", "HEAD")
    new_sha = _git(local, "rev-parse", "@{u}")
    worktree = tmp_path / "wt"
    subprocess.run(["git", "worktree", "add", "--detach", str(worktree), new_sha], cwd=local, check=True)

    _reset_for_test()
    gate = WorkspaceMutationGate()
    try:
        with gate.blocking_writes("sync_in_progress"):
            _run_m4_sync(local, worktree, branch="main", old_sha=old_sha, new_sha=new_sha, gate=gate)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=local)

    assert _git(local, "rev-parse", "HEAD") == new_sha


def test_sync_deleted_model_file_removed(tmp_path: Path) -> None:
    """A file deleted upstream is removed from the live tree by M4."""
    origin, local = _setup_origin_and_clone(tmp_path)
    _commit(origin, "add extra", files={"model/entities/B.md": "extra\n"})
    subprocess.run(
        ["git", "push", "origin", "main"],
        cwd=origin,
        capture_output=True,
    )
    subprocess.run(["git", "pull", "--ff-only"], cwd=local, capture_output=True)

    subprocess.run(["git", "rm", "model/entities/B.md", "--quiet"], cwd=origin, check=True)
    subprocess.run(["git", "commit", "-m", "delete B", "--quiet"], cwd=origin, check=True)
    subprocess.run(["git", "fetch", "origin"], cwd=local, check=True)

    old_sha = _git(local, "rev-parse", "HEAD")
    new_sha = _git(local, "rev-parse", "@{u}")
    worktree = tmp_path / "wt"
    subprocess.run(["git", "worktree", "add", "--detach", str(worktree), new_sha], cwd=local, check=True)

    _reset_for_test()
    gate = WorkspaceMutationGate()
    try:
        with gate.blocking_writes("sync_in_progress"):
            _run_m4_sync(local, worktree, branch="main", old_sha=old_sha, new_sha=new_sha, gate=gate)
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], cwd=local)

    assert not (local / "model" / "entities" / "B.md").exists()
    assert _git(local, "rev-parse", "HEAD") == new_sha
