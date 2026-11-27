"""Running one git command in a repository — the single place this package shells out.

Two things here rather than one: running a command with the shared SSH environment, and committing
under the service identity. Both are the same concern — assembling the environment a git call needs
— and both have more than one caller, which is why neither lives beside whichever operation reached
for it first.

Every git call in the package goes through here, so the shared SSH environment is applied once
rather than remembered at each call site. `held_credentials` is populated by `GitSyncManager` on
startup, which is why a push from the write-queue executor thread has the same askpass credentials as
the background sync.

A command that reaches `origin` runs through `push_to_origin` or `ask_origin`, which raise
`GitCredentialsRequired` where the remote refused for want of a credential. That is the one place a
refusal is recognised, so no operation has to remember to ask, and the direction (push URL or fetch URL)
follows from which runner was called.

These run in the write-queue executor thread rather than the asyncio event loop, which is why they
are synchronous. `tests/architecture/test_dependency_policy.py` names this module as the only one
in the package permitted to reach the mutation adapter's `run_git`; a second one would be a second
place the environment could be forgotten.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from src.config.git_identity import load_service_git_identity
from src.domain.repository.repo_layout import RUNTIME_STATE
from src.infrastructure.mutation_adapters import run_git

#: Local plumbing answers immediately or something is wrong.
GIT_TIMEOUT = 30

#: Network operations reach a remote, so they get longer.
PUSH_TIMEOUT = 60

#: **Repository content, as git is asked about it**: the whole repository except its declared runtime
#: state. The one pathspec every git question about content carries — what a save stages, whether
#: there is anything to save, what a pull installs, what a branch changes against upstream. They
#: were five spellings; three named `model/`, `docs/` and `diagram-catalog/` and so left
#: `projects/` and `scratchpads/` out, and a pull that moved the branch without installing those
#: made the next save publish the reversal of a teammate's work. What is runtime state is the
#: layout's to declare (`repo_layout.RUNTIME_STATE`); this is only its git dialect.
#:
#: A glob that **opens with a wildcard** rather than a plain `:(exclude).arch`: when a `.gitignore`
#: lists the path and it exists, git treats whatever literal text an exclude begins with as a path
#: named on the command line that is ignored, and refuses the whole `add` — so a data upgrade's
#: checkpoint failed on exactly the enterprise repositories the template ships. `**/` matches at any
#: depth, the root included, leaves no literal prefix to be mistaken for a named path, and so holds
#: whether the runtime state is ignored or merely untracked.
CONTENT_PATHSPEC: tuple[str, ...] = (
    ".",
    *(f":(exclude,glob)**/{path}{'**' if path.endswith('/') else ''}" for path in RUNTIME_STATE),
)

#: Stage everything that is content. A blind `git add .` once carried `.arch/enterprise-sync.json`
#: through a PR into origin/main; the exclude holds even when the repository has no `.gitignore`.
#: Here rather than beside a caller because the checkpoint, the repair and every work commit stage
#: the same way, and the incident above is the reason they must not drift apart.
STAGE_ALL_BUT_RUNTIME_STATE = ("add", "-A", "--", *CONTENT_PATHSPEC)

#: The question "does this repository hold content nobody has committed", as git is asked it.
#: Untracked files are listed one by one (`-u`) so that an untracked directory holding only runtime
#: state is not reported by its content-named parent. Stated as arguments rather than as a function
#: because it has two askers that run git differently — the write path synchronously, the sync
#: manager on its event loop — and they have to be asking the same thing: the status once reported
#: a saved repository that the pull refused to touch as unsaved.
UNCOMMITTED_CONTENT_QUERY = ("status", "--porcelain", "-u", "--", *CONTENT_PATHSPEC)


def run_repo_git(
    repo: Path,
    *args: str,
    timeout: float = GIT_TIMEOUT,
    env_overrides: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run `git *args` in `repo`, returning `(returncode, stdout, stderr)` with both trimmed."""
    from src.infrastructure.git.held_credentials import git_environment  # noqa: PLC0415

    env = dict(git_environment() or os.environ)
    if env_overrides:
        env.update(env_overrides)
    result = run_git(repo, args, timeout=timeout, env=env)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def push_to_origin(
    repo: Path, *args: str, timeout: float = PUSH_TIMEOUT, environment: Mapping[str, str] | None = None,
) -> tuple[int, str, str]:
    """`git push *args` in `repo`, as `run_repo_git` answers it; a refusal of the push URL for want of a
    credential is raised as `GitCredentialsRequired` instead. *environment* replaces the held one where a
    caller wires its own credentials (`arch-repair`)."""
    return _reaching_origin(repo, ("push", *args), pushing=True, timeout=timeout, environment=environment)


def ask_origin(
    repo: Path, *args: str, timeout: float = PUSH_TIMEOUT, environment: Mapping[str, str] | None = None,
) -> tuple[int, str, str]:
    """A git command that reads `origin` (`fetch`, `pull`, `ls-remote`), as `run_repo_git` answers it; a
    refusal of the fetch URL for want of a credential is raised as `GitCredentialsRequired` instead."""
    return _reaching_origin(repo, args, pushing=False, timeout=timeout, environment=environment)


def raise_a_refusal(repo: Path, *, pushing: bool, returncode: int, stderr: str) -> None:
    """Raise `GitCredentialsRequired` where a command that reached `origin` failed for want of a
    credential; return otherwise. The remote runners' one decision, shared with the background sync's
    own (asynchronous) runner."""
    if returncode == 0:
        return
    from src.infrastructure.git import held_credentials  # noqa: PLC0415
    from src.infrastructure.git.credential_refusal import credentials_required_for  # noqa: PLC0415

    refusal = credentials_required_for(repo, pushing=pushing, git_output=stderr, held=held_credentials.held())
    if refusal is not None:
        raise refusal


def _reaching_origin(
    repo: Path, args: tuple[str, ...], *, pushing: bool, timeout: float, environment: Mapping[str, str] | None,
) -> tuple[int, str, str]:
    if environment is None:
        rc, out, err = run_repo_git(repo, *args, timeout=timeout)
    else:
        result = run_git(repo, args, timeout=timeout, env=dict(environment))
        rc, out, err = result.returncode, result.stdout.strip(), result.stderr.strip()
    raise_a_refusal(repo, pushing=pushing, returncode=rc, stderr=err)
    return rc, out, err


def run_repo_git_untrimmed(repo: Path, *args: str, timeout: float = GIT_TIMEOUT) -> tuple[int, str, str]:
    """`run_repo_git` with stdout as git wrote it — for file contents, whose final newline is content."""
    from src.infrastructure.git.held_credentials import git_environment  # noqa: PLC0415

    result = run_git(repo, args, timeout=timeout, env=dict(git_environment() or os.environ))
    return result.returncode, result.stdout, result.stderr.strip()


def commit_with_identity(repo: Path, message: str) -> tuple[int, str, str]:
    """Commit staged changes, authored and committed by the service identity the server is configured with.

    Authorship is the server's to establish, never a caller's to assert: a request that could name an
    author could record its commit under anyone's name. When a principal exists it becomes the author
    and the service identity stays the committer; until then both are the service identity.

    The identity is set both as `-c user.*` and in the environment: the config flags decide what git
    records, the environment variables decide what it reports back, and the process environment must
    not override either with a `GIT_AUTHOR_*` of its own.
    """
    service = load_service_git_identity()
    env = {
        "GIT_AUTHOR_NAME": service.name,
        "GIT_AUTHOR_EMAIL": service.email,
        "GIT_COMMITTER_NAME": service.name,
        "GIT_COMMITTER_EMAIL": service.email,
    }
    return run_repo_git(
        repo,
        "-c",
        f"user.name={service.name}",
        "-c",
        f"user.email={service.email}",
        "commit",
        "-m",
        message,
        env_overrides=env,
    )
