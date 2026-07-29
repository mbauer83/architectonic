"""M4-based git-sync publisher: compute manifest from worktree diff → atomic publish."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.infrastructure.workspace.mutation_gate import WorkspaceMutationGate

from src.config.repo_paths import DIAGRAM_CATALOG, DOCS, MODEL
from src.infrastructure.mutation_adapters import run_git
from src.infrastructure.write.artifact_write.m4_transaction import (
    GitRefTransition,
    ManifestEntry,
    TransactionManifest,
    ensure_transactions_root,
    fsync_directory,
    hash_file,
    publish_transaction,
    write_transaction_intent,
)

GitRunner = Callable[..., Awaitable[tuple[int, str, str]]]
_MODEL_DIRS = [MODEL, DOCS, DIAGRAM_CATALOG]


def compute_sync_entries(
    repo_root: Path,
    worktree_root: Path,
    old_sha: str,
    new_sha: str,
) -> list[ManifestEntry]:
    """Build M4 entries for model-dir files changed between old_sha and new_sha.

    Status D → delete entry (prior hash from live file).
    Status A/M → create/replace entry (target hash + content from worktree).
    Rename detection is suppressed (--diff-filter=ADM); renames appear as A+D.
    """
    result = run_git(
        repo_root,
        ["diff", "--name-status", "--diff-filter=ADM", old_sha, new_sha, "--"] + _MODEL_DIRS,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git diff failed: {result.stderr.strip()}")

    entries: list[ManifestEntry] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        status_char = parts[0].strip()[0]
        rel_path = Path(parts[1].strip())
        dest_str = rel_path.as_posix()
        live_file = repo_root / rel_path

        if status_char == "D":
            prior = hash_file(live_file) if live_file.exists() else "absent"
            entries.append(ManifestEntry(
                kind="delete",
                dest=dest_str,
                target_hash="absent",
                prior_hash_or_absent=prior,
                payload=None,
            ))
        else:
            wt_file = worktree_root / rel_path
            if not wt_file.exists():
                continue
            target = hash_file(wt_file)
            prior = hash_file(live_file) if live_file.exists() else "absent"
            entries.append(ManifestEntry(
                kind="replace" if live_file.exists() else "create",
                dest=dest_str,
                target_hash=target,
                prior_hash_or_absent=prior,
                payload=f"payloads/{dest_str}",
            ))
    return entries


async def add_detached_worktree(
    git_runner: GitRunner,
    repo: Path,
    sha: str,
    *,
    timeout: float,
) -> Path:
    """Create a detached worktree at ``sha``; caller must remove it when done."""
    wt_path = repo / ".arch-repo" / "sync-worktrees" / f"sync-{sha[:16]}"
    wt_path.parent.mkdir(parents=True, exist_ok=True)
    rc, _, err = await git_runner(repo, "worktree", "add", "--detach", str(wt_path), sha, timeout=timeout)
    if rc != 0:
        raise RuntimeError(f"worktree add failed: {err.strip()}")
    return wt_path


async def prepare_rebase_worktree(
    git_runner: GitRunner,
    repo: Path,
    old_sha: str,
    *,
    timeout: float,
) -> tuple[Path, str] | None:
    """Rebase HEAD onto @{u} in an isolated worktree.

    Returns ``(worktree_path, post_rebase_sha)`` on success, or ``None`` on
    conflict (the worktree is aborted and cleaned up before returning).
    """
    wt_path = repo / ".arch-repo" / "sync-worktrees" / f"rebase-{old_sha[:16]}"
    wt_path.parent.mkdir(parents=True, exist_ok=True)
    rc, _, err = await git_runner(repo, "worktree", "add", "--detach", str(wt_path), "HEAD", timeout=timeout)
    if rc != 0:
        raise RuntimeError(f"worktree add for rebase failed: {err.strip()}")
    rc, out, err = await git_runner(wt_path, "rebase", "@{u}", timeout=timeout)
    if rc != 0:
        if "CONFLICT" in out or "CONFLICT" in err:
            await git_runner(wt_path, "rebase", "--abort")
            await git_runner(repo, "worktree", "remove", "--force", str(wt_path))
            return None
        await git_runner(repo, "worktree", "remove", "--force", str(wt_path))
        raise RuntimeError(f"rebase failed: {err.strip()}")
    rc, new_sha_out, _ = await git_runner(wt_path, "rev-parse", "HEAD")
    return wt_path, new_sha_out.strip()


def run_m4_pull(
    repo: Path,
    worktree_path: Path,
    *,
    branch: str,
    old_sha: str,
    new_sha: str,
    gate: "WorkspaceMutationGate",
    on_boundary: Callable[[str], None] | None = None,
) -> None:
    """Compute index rebuild from sync entries and call publish_git_pull_via_m4."""
    from src.infrastructure.artifact_index import notify_paths_changed  # noqa: PLC0415

    def _rebuild() -> None:
        entries = compute_sync_entries(repo, worktree_path, old_sha, new_sha)
        notify_paths_changed([repo / e.dest for e in entries])

    publish_git_pull_via_m4(
        repo, worktree_path,
        branch=branch, old_sha=old_sha, new_sha=new_sha,
        gate=gate, rebuild_index=_rebuild, on_boundary=on_boundary,
    )


def publish_git_pull_via_m4(
    repo_root: Path,
    worktree_root: Path,
    *,
    branch: str,
    old_sha: str,
    new_sha: str,
    gate: "WorkspaceMutationGate",
    rebuild_index: Callable[[], object],
    on_boundary: Callable[[str], None] | None = None,
) -> None:
    """Publish a git pull result atomically via M4 transaction.

    The caller must hold ``gate.blocking_writes("sync_in_progress")`` for the
    full scope. This function acquires ``gate.privileged_writing()`` only during
    the M4 publish window so reads are not blocked during the intent phase.
    """
    entries = compute_sync_entries(repo_root, worktree_root, old_sha, new_sha)
    ref = GitRefTransition(branch=branch, old_sha=old_sha, new_sha=new_sha)
    manifest = TransactionManifest(entries=entries, ref=ref)
    txn_id = f"sync-{new_sha[:16]}-{uuid.uuid4().hex[:6]}"
    txn_dir = ensure_transactions_root(repo_root) / txn_id
    txn_dir.mkdir(parents=True, exist_ok=True)
    fsync_directory(txn_dir.parent)
    write_transaction_intent(
        repo_root=repo_root,
        transaction_dir=txn_dir,
        staged_root=worktree_root,
        manifest=manifest,
        on_boundary=on_boundary,
    )
    with gate.privileged_writing():
        publish_transaction(
            repo_root=repo_root,
            transaction_dir=txn_dir,
            manifest=manifest,
            rebuild_index=rebuild_index,
            on_boundary=on_boundary,
        )
