"""The repository's own `.gitignore` for the runtime state kept beside its configuration.

`.arch-repo/` holds configuration, which is content, and — in `transactions/`, `sync-worktrees/` and
the exchange identity map — state that is not. Every git operation this product runs excludes the
second by pathspec (`_git_command.CONTENT_PATHSPEC`), so nothing here protects the product from
itself. The file is for everyone else: a person running `git add .` in a clone, where an interrupted
write may have left a transaction journal on disk.

**The file is content, and tracked.** It is written when a repository is scaffolded or brought up
to current defaults, so it is committed with the rest of the configuration. The writers of runtime
state call this too, as the repair for a repository that predates that — where it is an honest
uncommitted change the next save carries, once.

One writer, because there were two — the transaction journal's and the exchange identity map's —
each appending its own line, so a repository ignored whichever state it happened to have produced
first. The lines are read from the layout's declaration rather than listed again.
"""

from __future__ import annotations

from pathlib import Path

from src.domain.repository.repo_layout import ARCH_REPO, RUNTIME_STATE

_GITIGNORE = ".gitignore"
_INSIDE_CONFIGURATION = f"{ARCH_REPO}/"

#: What `.arch-repo/.gitignore` must list — every declared piece of runtime state that lives there,
#: relative to the file. The declaration's own form is already `.gitignore`'s: a trailing `/` is a
#: directory.
RUNTIME_STATE_IGNORE_LINES: tuple[str, ...] = tuple(
    path.removeprefix(_INSIDE_CONFIGURATION) for path in RUNTIME_STATE if path.startswith(_INSIDE_CONFIGURATION)
)


def ensure_runtime_state_ignored(repo_root: Path) -> bool:
    """Make `.arch-repo/.gitignore` list all declared runtime state. True when it had to be written.

    Appends what is missing and keeps every line already there, so a line someone added by hand
    survives.
    """
    arch_repo = repo_root / ARCH_REPO
    arch_repo.mkdir(parents=True, exist_ok=True)
    gitignore = arch_repo / _GITIGNORE
    present = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.exists() else []
    missing = [line for line in RUNTIME_STATE_IGNORE_LINES if line not in present]
    if not missing:
        return False
    gitignore.write_text("".join(f"{line}\n" for line in (*present, *missing)), encoding="utf-8")
    return True
