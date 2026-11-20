"""What git treats as a repository's content is defined once, as everything but declared runtime state.

It was spelled five times. The save staged everything but `.arch/`; the pull, the content diff and
the sync status each named `model/`, `docs/` and `diagram-catalog/`; the repair staged everything but
the transaction journal. A list of members falls behind the layout, and this one had, twice — it
predated `projects/` and `scratchpads/`. So a pull moved the branch without installing a grouped
entity, the next save published the reversal of a teammate's work, and the status reported nothing to
save for the directories the save was about to commit.

The declaration is `repo_layout.RUNTIME_STATE`; its git dialect is `_git_command.CONTENT_PATHSPEC`.
What is asserted here is that neither can quietly gain a sibling:

* nothing else writes a git exclude pathspec — a second one is a second definition of content;
* no module that asks git about a repository names the layout's content directories — a member list
  there is the defect itself, however complete it is on the day it is written;
* the runtime-state names are spelled only where they are declared.

`tests/infrastructure/git/test_a_pull_brings_everything_the_commit_holds.py` and
`tests/tools/test_unsaved_work_is_reported_wherever_it_lives.py` hold the behaviour; this holds the
shape that keeps the behaviour from being re-derived one caller at a time.
"""

from __future__ import annotations

import ast
from pathlib import Path

from src.domain.repository import repo_layout
from src.infrastructure.git._git_command import CONTENT_PATHSPEC
from tests.support.source_paths import REPO_ROOT, SRC, python_sources

_DECLARATION = Path("src/domain/repository/repo_layout.py")
_GIT_DIALECT = Path("src/infrastructure/git/_git_command.py")

#: Exclude pathspecs that are not about an architecture repository's content, each with its reason.
_OTHER_EXCLUDES: dict[Path, str] = {
    Path("src/infrastructure/software_update/checkout.py"): (
        "the product's own source checkout, not an architecture repository: it has no `.arch-repo/` "
        "and its only runtime state is the workspace's `.arch/`"
    ),
}

#: Modules that ask git about a repository: the git package, and the status built on it.
_GIT_PACKAGE = SRC / "infrastructure" / "git"
_SYNC_STATUS = SRC / "infrastructure" / "rest" / "routers" / "sync" / "status_cache.py"

#: The layout's content directories. Naming one while asking git what is content is a member list.
_CONTENT_DIRECTORY_CONSTANTS = frozenset({"MODEL", "DOCS", "DIAGRAM_CATALOG", "PROJECTS", "SCRATCHPADS"})

_RUNTIME_STATE_NAMES = frozenset(
    {repo_layout.TRANSACTIONS, repo_layout.SYNC_WORKTREES, repo_layout.EXCHANGE_IDENTITY}
)


def _relative(path: Path) -> Path:
    return path.relative_to(REPO_ROOT)


def _string_constants(path: Path) -> list[str]:
    """Every string literal in the file that is code rather than prose: docstrings are left out,
    because a module may *describe* a pathspec it must not *write*."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    ]


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names}


def test_the_declaration_and_its_git_dialect_are_where_this_test_expects_them() -> None:
    # Without this, moving either would make every assertion below vacuously true.
    assert (REPO_ROOT / _DECLARATION).is_file() and (REPO_ROOT / _GIT_DIALECT).is_file()
    assert _GIT_PACKAGE.is_dir() and _SYNC_STATUS.is_file()
    assert repo_layout.RUNTIME_STATE, "an empty declaration would make everything content"


def test_every_declared_piece_of_runtime_state_is_excluded_from_content() -> None:
    """The dialect is derived, so it cannot omit an entry — asserted because it was once written out."""
    excludes = [spec for spec in CONTENT_PATHSPEC if spec.startswith(":(exclude")]

    assert len(excludes) == len(repo_layout.RUNTIME_STATE)
    assert all(any(path.rstrip("/") in spec for spec in excludes) for path in repo_layout.RUNTIME_STATE)
    assert CONTENT_PATHSPEC[0] == ".", "content is the whole repository before anything is excluded"


def test_only_the_git_dialect_writes_an_exclude_pathspec() -> None:
    offenders = {
        str(_relative(path))
        for path in python_sources(SRC)
        if _relative(path) not in {_GIT_DIALECT, *_OTHER_EXCLUDES}
        and any(":(exclude" in text for text in _string_constants(path))
    }

    assert offenders == set(), (
        "these write their own git exclude pathspec, which is a second definition of what a "
        "repository's content is. Use `_git_command.CONTENT_PATHSPEC` (or a command built on it: "
        f"`STAGE_ALL_BUT_RUNTIME_STATE`, `UNCOMMITTED_CONTENT_QUERY`): {sorted(offenders)}"
    )


def test_the_recorded_other_excludes_still_exist() -> None:
    """An allowance for a pathspec that has gone is an allowance for the next one written there."""
    stale = {
        str(path)
        for path in _OTHER_EXCLUDES
        if not any(":(exclude" in text for text in _string_constants(REPO_ROOT / path))
    }

    assert stale == set()


def test_nothing_that_asks_git_names_the_content_directories() -> None:
    offenders = {
        str(_relative(path)): sorted(named)
        for path in (*python_sources(_GIT_PACKAGE), _SYNC_STATUS)
        if (named := _CONTENT_DIRECTORY_CONSTANTS & _imported_names(path))
    }

    assert offenders == {}, (
        "these name the layout's content directories while asking git about a repository. A list of "
        "members is how `projects/` and `scratchpads/` came to be left out of a pull; ask about "
        f"`_git_command.CONTENT_PATHSPEC` instead: {offenders}"
    )


def test_the_runtime_state_names_are_spelled_only_in_the_declaration() -> None:
    offenders = {
        str(_relative(path)): sorted(found)
        for path in python_sources(SRC)
        if _relative(path) != _DECLARATION
        and (found := {name for text in _string_constants(path) for name in _RUNTIME_STATE_NAMES if name in text})
    }

    assert offenders == {}, (
        "these spell a runtime-state path themselves; import it from `repo_layout`, so that what is "
        f"declared runtime state and where it is written cannot drift apart: {offenders}"
    )
