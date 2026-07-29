"""Remote-aware git bootstrap for workspace initialization.

``arch-init`` must distinguish a *populated* remote — which has to be CLONED so
the local checkout shares the remote's history and upstream tracking — from a
*genuinely empty* remote, which may be INITIALIZED locally and published.

Conflating the two (initializing a fresh repo whenever the local clone directory
is merely absent, or whenever the *configured branch* is absent) produces a
checkout with an unrelated history and no upstream. The background git-sync can
then never fast-forward onto the real remote, so a deployment silently shows its
own empty scaffold instead of the pushed content.

This module classifies the remote's actual state, keeps upstream tracking
correct on every path, and — because a checkout without tracking is the exact
defect we are eliminating — treats a failure to establish tracking as fatal.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from src.infrastructure.workspace.engagement_repo_template import (
    create_engagement_repo,
    initialize_arch_repo_in_place,
)


class RemoteState(Enum):
    """How a remote relates to the configured branch."""

    HAS_BRANCH = "has_branch"  # configured branch exists → clone it
    OTHER_REFS = "other_refs"  # remote has refs but not the branch → configuration error
    EMPTY = "empty"  # no refs at all → bootstrapping an empty remote is allowed


@dataclass(frozen=True)
class BootstrapContext:
    """Everything needed to bring one workspace repo into existence."""

    label: str
    url: str
    branch: str
    dest: Path
    initialize_if_empty: bool
    env: dict[str, str] | None
    author_name: str
    author_email: str


def run_git(
    args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=120, env=env)


def classify_remote(url: str, branch: str, env: dict[str, str] | None = None) -> RemoteState:
    """Classify a remote against the configured branch.

    Raises ``SystemExit`` on an inconclusive probe (auth/network) rather than
    guessing "empty": guessing wrong fabricates an unrelated local history over a
    populated remote — the exact failure this module exists to prevent.
    """
    result = run_git(["ls-remote", url], env=env)
    if result.returncode != 0:
        raise SystemExit(
            f"ERROR: could not reach git remote {url!r}: {result.stderr.strip() or 'unknown error'}"
        )
    refs = result.stdout.strip()
    if not refs:
        return RemoteState.EMPTY
    target = f"refs/heads/{branch}"
    has_branch = any(line.split("\t")[-1] == target for line in refs.splitlines())
    return RemoteState.HAS_BRANCH if has_branch else RemoteState.OTHER_REFS


def clone(url: str, branch: str, dest: Path, env: dict[str, str] | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = run_git(["clone", "--branch", branch, url, str(dest)], env=env)
    if result.returncode != 0:
        raise SystemExit(f"ERROR: git clone failed for {url}\n{result.stderr.strip()}")


def bootstrap_absent(ctx: BootstrapContext) -> None:
    """Create a repo whose local clone directory does not exist yet."""
    state = classify_remote(ctx.url, ctx.branch, ctx.env)
    if state is RemoteState.HAS_BRANCH:
        print(f"  {ctx.label}: cloning {ctx.url} (branch={ctx.branch}) → {ctx.dest}")
        clone(ctx.url, ctx.branch, ctx.dest, env=ctx.env)
        return
    if state is RemoteState.OTHER_REFS:
        raise SystemExit(
            f"ERROR: {ctx.label} remote {ctx.url} has refs but no branch '{ctx.branch}'. "
            f"Set git.branch to an existing branch, or create '{ctx.branch}' on the remote first."
        )
    if not ctx.initialize_if_empty:
        raise SystemExit(
            f"ERROR: {ctx.label} remote {ctx.url} is empty. "
            f"Pass --initialize-{ctx.label}-repo-if-empty to bootstrap it."
        )
    _initialize_and_publish(ctx)


def reconcile_empty_checkout(ctx: BootstrapContext) -> None:
    """Resolve an existing checkout that has no commits yet.

    If the remote already has the branch, adopt its history (never commit an
    unrelated local scaffold over it); otherwise initialize + publish when the
    caller opted into empty-remote bootstrapping.
    """
    state = classify_remote(ctx.url, ctx.branch, ctx.env)
    if state is RemoteState.HAS_BRANCH:
        print(f"  {ctx.label}: empty checkout but remote has '{ctx.branch}' — adopting remote history ({ctx.dest})")
        _adopt_remote(ctx)
        return
    if state is RemoteState.OTHER_REFS:
        raise SystemExit(
            f"ERROR: {ctx.label} remote {ctx.url} has refs but no branch '{ctx.branch}'. "
            f"Set git.branch to an existing branch, or create '{ctx.branch}' on the remote first."
        )
    if ctx.initialize_if_empty:
        _initialize_and_publish(ctx)


def validate_tracking(ctx: BootstrapContext) -> None:
    """Verify a populated existing checkout actually mirrors the configured remote.

    Fails closed on the conditions that silently broke deployments — wrong origin
    URL or an unrelated history — and self-heals a missing/incorrect upstream when
    the histories are related. Ahead/diverged state is role-specific (engagement
    drafts locally) and is enforced by the watcher, not here.

    A transient fetch failure downgrades to a warning so a network blip cannot
    brick container startup; the origin-URL check still applies offline.
    """
    _check_origin_url(ctx)
    fetched = run_git(["fetch", "origin", ctx.branch], cwd=ctx.dest, env=ctx.env)
    if fetched.returncode != 0:
        print(
            f"  WARNING: {ctx.label}: could not fetch origin/{ctx.branch} to validate {ctx.dest} "
            f"({fetched.stderr.strip() or 'unknown error'}); skipping ancestry/upstream checks"
        )
        return
    remote_ref = f"origin/{ctx.branch}"
    _check_shared_history(ctx, remote_ref)
    _ensure_upstream(ctx, remote_ref)


def _check_origin_url(ctx: BootstrapContext) -> None:
    result = run_git(["remote", "get-url", "origin"], cwd=ctx.dest)
    actual = result.stdout.strip()
    if result.returncode != 0 or actual != ctx.url:
        raise SystemExit(
            f"ERROR: {ctx.label} repo at {ctx.dest} has origin {actual or '<none>'!r}, "
            f"expected {ctx.url!r}. Re-point origin or remove the directory and re-run arch-init."
        )


def _check_shared_history(ctx: BootstrapContext, remote_ref: str) -> None:
    merge_base = run_git(["merge-base", "HEAD", remote_ref], cwd=ctx.dest)
    if merge_base.returncode == 0 and merge_base.stdout.strip():
        return
    raise SystemExit(
        f"ERROR: {ctx.label} repo at {ctx.dest} shares no history with {remote_ref} — it was "
        f"initialized locally, not cloned from origin. Remove the directory and re-run arch-init, or run:\n"
        f"    git -C {ctx.dest} fetch origin && git -C {ctx.dest} reset --hard {remote_ref} && "
        f"git -C {ctx.dest} branch --set-upstream-to={remote_ref} {ctx.branch}"
    )


def _ensure_upstream(ctx: BootstrapContext, remote_ref: str) -> None:
    current = run_git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=ctx.dest)
    if current.returncode == 0 and current.stdout.strip() == remote_ref:
        return
    print(f"  {ctx.label}: repairing upstream tracking → {remote_ref} ({ctx.dest})")
    result = run_git(["branch", f"--set-upstream-to={remote_ref}", ctx.branch], cwd=ctx.dest)
    if result.returncode != 0:
        raise SystemExit(
            f"ERROR: {ctx.label}: could not set upstream {remote_ref} for {ctx.dest}\n{result.stderr.strip()}"
        )


def scaffold_in_place_and_publish(ctx: BootstrapContext) -> None:
    """Scaffold arch-repo structure into a cloned repo that lacks it, then publish.

    A populated remote without a ``model/`` directory (e.g. a new repo created with
    only a README) is a *migration*, not an empty bootstrap. The scaffold must be
    PUBLISHED — never left as an unsynchronized local commit that makes the watcher
    see the mirror as ahead of origin.
    """
    print(f"  {ctx.label}: clone has no arch-repo structure — scaffolding in place and publishing ({ctx.dest})")
    initialize_arch_repo_in_place(
        ctx.dest, commit_author_name=ctx.author_name, commit_author_email=ctx.author_email
    )
    result = run_git(["push", "origin", ctx.branch], cwd=ctx.dest, env=ctx.env)
    if result.returncode != 0:
        raise SystemExit(
            f"ERROR: {ctx.label}: failed to publish the scaffold to origin/{ctx.branch} "
            f"({result.stderr.strip() or 'unknown error'}). It would remain an unpublished local commit; "
            f"fix push credentials/permissions and re-run."
        )


def _initialize_and_publish(ctx: BootstrapContext) -> None:
    print(f"  {ctx.label}: remote empty — initializing and publishing '{ctx.branch}' → {ctx.dest}")
    create_engagement_repo(
        ctx.dest,
        git_url=ctx.url,
        branch=ctx.branch,
        commit_author_name=ctx.author_name,
        commit_author_email=ctx.author_email,
    )
    _publish_initial_branch(ctx)


def _publish_initial_branch(ctx: BootstrapContext) -> None:
    """Push a freshly initialized scaffold to the empty remote and set upstream.

    Fatal on failure: a checkout with no upstream is the defect this module
    prevents. If the push was rejected because the remote gained the branch
    concurrently, instruct the operator to re-run so it clones the published
    history instead of keeping the unrelated local scaffold.
    """
    result = run_git(["push", "-u", "origin", ctx.branch], cwd=ctx.dest, env=ctx.env)
    if result.returncode == 0:
        return
    if classify_remote(ctx.url, ctx.branch, ctx.env) is RemoteState.HAS_BRANCH:
        raise SystemExit(
            f"ERROR: {ctx.label}: remote gained branch '{ctx.branch}' while {ctx.dest} was being bootstrapped. "
            f"Remove the directory and re-run arch-init so it clones the published history."
        )
    raise SystemExit(
        f"ERROR: {ctx.label}: failed to publish '{ctx.branch}' to origin "
        f"({result.stderr.strip() or 'unknown error'}). The checkout would have no upstream tracking; "
        f"fix push credentials/permissions and re-run."
    )


def _adopt_remote(ctx: BootstrapContext) -> None:
    """Fast-forward a commit-less checkout onto a remote that has the branch."""
    steps = (
        ["fetch", "origin", ctx.branch],
        ["checkout", "-B", ctx.branch, f"origin/{ctx.branch}"],
        ["branch", f"--set-upstream-to=origin/{ctx.branch}", ctx.branch],
    )
    for args in steps:
        result = run_git(args, cwd=ctx.dest, env=ctx.env)
        if result.returncode != 0:
            raise SystemExit(
                f"ERROR: {ctx.label}: adopting remote '{ctx.branch}' into {ctx.dest} failed\n{result.stderr.strip()}"
            )
