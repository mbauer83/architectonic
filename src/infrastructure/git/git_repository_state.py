"""What a git repository currently says about itself — read-only questions, no side effects.

Separated from the operations that *change* a repository because these are what a status read, a
preflight and a reconciliation all consult, and none of them should have to import a module that can
also push. Grouped rather than scattered so "is this branch ahead" has one answer.

Two functions did not come across in the split. `commits_behind_main` had no caller. Neither did
`promotion_merged_into_main`, and it answered a question `git_sync_enterprise.promotion_merged`
already answers for the caller that actually asks it — the same content diff, reached through the
sync manager rather than a fresh subprocess. Moving a dead second reading of "has this been merged"
into a new module would have been the split laundering it.
"""

from __future__ import annotations

from pathlib import Path

from src.infrastructure.git._git_command import PUSH_TIMEOUT, run_repo_git

#: What an enterprise working branch is opened from and merged back into. Spelled here because two
#: questions need it — how far behind a branch is, and what a rebase re-applies onto — and a second
#: spelling of the upstream is a second place to be wrong about which branch review happens against.
UPSTREAM_REF = "origin/main"


def current_branch(repo: Path) -> str | None:
    rc, out, _ = run_repo_git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    return out if rc == 0 and out not in ("", "HEAD") else None


def current_commit(repo: Path) -> str | None:
    rc, out, _ = run_repo_git(repo, "rev-parse", "HEAD")
    return out if rc == 0 else None


def has_uncommitted_changes(repo: Path, *pathspecs: str) -> bool:
    # `.arch/` holds runtime sync state, never user work — it must not count as
    # (or ever be committed with) unsaved changes.
    args = ["status", "--porcelain", "--", *(pathspecs or (".",)), ":(exclude).arch"]
    rc, out, _ = run_repo_git(repo, *args)
    return rc == 0 and bool(out)


def commits_ahead_of_main(repo: Path) -> int:
    rc, out, _ = run_repo_git(repo, "rev-list", "--count", f"{UPSTREAM_REF}..HEAD")
    try:
        return int(out) if rc == 0 else 0
    except ValueError:
        return 0


def is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    """Whether `ancestor` is reachable from `descendant` — a push of the second fast-forwards a
    remote at the first.

    The question that separates "this branch carries work we published earlier" from "this branch
    moved for a reason we did not cause". Both look identical as a pair of differing commit ids, and
    only reachability tells them apart.
    """
    rc, _, _ = run_repo_git(repo, "merge-base", "--is-ancestor", ancestor, descendant)
    return rc == 0


def remote_ref_commit(enterprise_root: Path, branch: str) -> str | None:
    """The commit `origin/<branch>` points at, or None where the remote has no such branch.

    The commit rather than a yes/no, because a submission that has to survive a crash between the
    push and the local write needs to know *which* commit is published: a ref at the commit the
    submission expected is a completed push to recognise, and a ref at any other commit is someone
    else's work to report rather than overwrite. `remote_ref_exists` is this question with the answer
    thrown away, and is kept as the narrower form for callers that only need presence.
    """
    rc, out, _ = run_repo_git(enterprise_root, "ls-remote", "--heads", "origin", branch, timeout=PUSH_TIMEOUT)
    if rc != 0:
        raise RuntimeError(f"Could not inspect origin for branch '{branch}'")
    first = out.split("\n", 1)[0].strip()
    return first.split()[0] if first else None


def remote_ref_exists(enterprise_root: Path, branch: str) -> bool:
    """Whether `origin/<branch>` exists at all. One reading of the ref, asked two ways."""
    return remote_ref_commit(enterprise_root, branch) is not None


def local_ref_exists(enterprise_root: Path, branch: str) -> bool:
    rc, _, _ = run_repo_git(enterprise_root, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}")
    return rc == 0


