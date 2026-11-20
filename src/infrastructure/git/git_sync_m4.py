"""M4-based git-sync publisher: compute manifest from worktree diff → atomic publish."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.infrastructure.workspace.mutation_gate import WorkspaceMutationGate

from src.config.git_identity import load_service_git_identity
from src.domain.repository.repo_layout import ARCH_REPO, SYNC_WORKTREES
from src.infrastructure.git._git_command import CONTENT_PATHSPEC, UNCOMMITTED_CONTENT_QUERY
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


#: Paths as they are on disk rather than octal-escaped: an entry's destination is joined onto the
#: repository root, and an escaped name is a file that does not exist — which the entry loop reads
#: as "nothing to install".
_VERBATIM_PATHS = ("-c", "core.quotepath=off")


class LocalWorkInTheWay(RuntimeError):
    """A pull would replace a file that holds content nobody has committed.

    Raised before anything is written — no intent, no file, no ref — so the repository is exactly
    as the author left it, and the remedy is theirs: save, then pull.
    """


def compute_sync_entries(
    repo_root: Path,
    worktree_root: Path,
    old_sha: str,
    new_sha: str,
) -> list[ManifestEntry]:
    """Build M4 entries for every content file changed between old_sha and new_sha.

    Status D → delete entry (prior hash from live file).
    Status A/M → create/replace entry (target hash + content from worktree).

    **Every content file**, because the ref is moved for the whole commit: a file the commit changed
    and this did not install stays at its old content under a branch that names the new one, which
    git reads as a local edit undoing it — and the next save commits exactly that. It was limited to
    `model/`, `docs/` and `diagram-catalog/`, which is how a teammate's change to a grouped entity or
    a scratchpad came to be reverted by whoever pulled it.

    `--no-renames` is what makes a rename arrive as an addition and a deletion. The filter alone
    does not: with rename detection on, which is git's default, a renamed file is reported as `R`
    and `--diff-filter=ADM` then drops it altogether.
    """
    result = run_git(
        repo_root,
        [*_VERBATIM_PATHS, "diff", "--name-status", "--no-renames", "--diff-filter=ADM", old_sha, new_sha,
         "--", *CONTENT_PATHSPEC],
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
    wt_path = repo / ARCH_REPO / SYNC_WORKTREES / f"sync-{sha[:16]}"
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
    """Rebase HEAD onto its upstream in an isolated worktree.

    Returns ``(worktree_path, post_rebase_sha)`` on success, or ``None`` on
    conflict (the worktree is aborted and cleaned up before returning).

    The upstream is resolved **in the repository**, to a commit, before the worktree exists. The
    worktree is detached, and a detached HEAD has no upstream: asked to ``rebase @{u}`` there, git
    answers "HEAD does not point to a branch" — so an engagement holding a commit its remote did
    not could never pull, and reported a failed pull on every poll instead.

    The replayed commits are committed by the service identity, as every commit this product makes
    is; a deployment has no git configuration of its own to fall back on.
    """
    rc, upstream_out, err = await git_runner(repo, "rev-parse", "@{u}")
    if rc != 0:
        raise RuntimeError(f"no upstream to rebase onto: {err.strip()}")
    wt_path = repo / ARCH_REPO / SYNC_WORKTREES / f"rebase-{old_sha[:16]}"
    wt_path.parent.mkdir(parents=True, exist_ok=True)
    rc, _, err = await git_runner(repo, "worktree", "add", "--detach", str(wt_path), "HEAD", timeout=timeout)
    if rc != 0:
        raise RuntimeError(f"worktree add for rebase failed: {err.strip()}")
    service = load_service_git_identity()
    rc, out, err = await git_runner(
        wt_path,
        "-c", f"user.name={service.name}",
        "-c", f"user.email={service.email}",
        "rebase", upstream_out.strip(),
        timeout=timeout,
    )
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
    _refuse_to_replace_uncommitted_work(repo_root, entries)
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


def _refuse_to_replace_uncommitted_work(repo_root: Path, entries: list[ManifestEntry]) -> None:
    """Refuse the pull when a file it would install or delete holds uncommitted content.

    An entry's prior hash is read from the live file, so the transaction itself cannot tell a file
    at the old commit from one the author has since edited — it would install over either. Callers
    skip a pull into a tree with unsaved work, but not every one of them in every state (an
    engagement that is ahead of its remote is rebased whatever the tree holds), and none of them
    can close the window between asking and publishing. This is asked here, immediately before the
    intent is written, so that no caller has to remember it.

    Work in files the pull does not touch is left alone and stays unsaved, as it was.
    """
    result = run_git(repo_root, [*_VERBATIM_PATHS, *UNCOMMITTED_CONTENT_QUERY])
    if result.returncode != 0:
        raise RuntimeError(f"git status failed: {result.stderr.strip()}")
    unsaved = {_porcelain_path(line) for line in result.stdout.splitlines() if line.strip()}
    in_the_way = sorted(unsaved & {entry.dest for entry in entries})
    if in_the_way:
        raise LocalWorkInTheWay(
            "the pull would replace unsaved local work in "
            + ", ".join(in_the_way)
            + " — save your changes, then the pull is retried"
        )


def _porcelain_path(line: str) -> str:
    """The path a `status --porcelain` line is about, as git names it in a diff.

    Two status columns and a space, then the path — quoted when it holds a character git escapes.
    A rename's `old -> new` cannot occur: this status is read with the index at HEAD, where git has
    nothing staged to pair into one.
    """
    path = line[3:]
    return path[1:-1] if path.startswith('"') and path.endswith('"') else path
