"""Running one git command in a repository — the single place this package shells out.

Two things here rather than one: running a command with the shared SSH environment, and committing
under the service identity. Both are the same concern — assembling the environment a git call needs
— and both have more than one caller, which is why neither lives beside whichever operation reached
for it first.

Every git call in the package goes through here, so the shared SSH environment is applied once
rather than remembered at each call site. `git_env` is populated by `GitSyncManager` on startup,
which is why a push from the write-queue executor thread has the same askpass credentials as the
background sync.

These run in the write-queue executor thread rather than the asyncio event loop, which is why they
are synchronous. `tests/architecture/test_dependency_policy.py` names this module as the only one
in the package permitted to reach the mutation adapter's `run_git`; a second one would be a second
place the environment could be forgotten.
"""

from __future__ import annotations

import os
from pathlib import Path

from src.config.git_identity import GitIdentity, load_service_git_identity
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
    from src.infrastructure.git.git_env import get_ssh_env  # noqa: PLC0415

    env = dict(get_ssh_env() or os.environ)
    if env_overrides:
        env.update(env_overrides)
    result = run_git(repo, args, timeout=timeout, env=env)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def run_repo_git_untrimmed(repo: Path, *args: str, timeout: float = GIT_TIMEOUT) -> tuple[int, str, str]:
    """`run_repo_git` with stdout as git wrote it — for file contents, whose final newline is content."""
    from src.infrastructure.git.git_env import get_ssh_env  # noqa: PLC0415

    result = run_git(repo, args, timeout=timeout, env=dict(get_ssh_env() or os.environ))
    return result.returncode, result.stdout, result.stderr.strip()


def commit_with_identity(repo: Path, message: str, *, author: GitIdentity | None) -> tuple[int, str, str]:
    """Commit staged changes, committed by the service identity and authored by `author` where given.

    The service identity is set both as `-c user.*` and in the environment: the config flags decide
    what git records, the environment variables decide what it reports back, and a caller reading a
    commit's author needs the two to agree.
    """
    service = load_service_git_identity()
    env = {
        "GIT_COMMITTER_NAME": service.name,
        "GIT_COMMITTER_EMAIL": service.email,
    }
    if author is not None:
        env.update(
            {
                "GIT_AUTHOR_NAME": author.name,
                "GIT_AUTHOR_EMAIL": author.email,
            }
        )
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
