"""Where a location a client names may lead: inside the configured repositories, and nowhere else.

The one owner of that question, for reads and writes alike. A client names a location in three
shapes, and each has its check here:

* **a repository root** (`repo_root`, `enterprise_root`): it must *be* one of the configured roots
  once both are resolved — `confine_root`;
* **a location inside the repositories** (a file to verify, a file a write publishes): once resolved,
  it must lie inside one of them — `confine_within`;
* **a name that becomes one component of a path** (a group's slug, a file name): it must be exactly
  one component, so joining it to a directory cannot climb out of it — `require_segment`.

"Resolved" means `Path.resolve`: relative spellings, `..` and symlinks are followed before the
comparison, so neither `repo/../elsewhere` nor a link inside a repository pointing out of it passes.

A refusal names the configured repositories, never what was found at the location asked for, so
asking cannot be used to learn whether something exists outside them.

The write path's authorization policy (`mutation_policy`) asks the same two questions of the roots a
mutation names, through `is_root` and `is_within` below.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

#: Exactly one path component: not empty, not `.` or `..`, and no separator, drive colon or NUL.
#: A regular expression so that a request contract can declare it as the pattern of a field — it
#: is then the same rule, published, rather than a second spelling of it. Spelled without lookahead,
#: which the request validator's regular-expression engine does not support.
SEGMENT_PATTERN = (
    r"^(?:[^/\\:\x00.][^/\\:\x00]*|\.[^/\\:\x00.][^/\\:\x00]*|\.\.[^/\\:\x00]+)$"
)
_SEGMENT = re.compile(SEGMENT_PATTERN)


class LocationRefused(ValueError):
    """A client named a location outside the configured repositories, or a name that would lead out."""


def canonical(path: Path) -> Path:
    """The location `path` names, with `..`, relative spellings and symlinks followed."""
    return path.expanduser().resolve()


def is_root(path: Path, root: Path) -> bool:
    """Whether `path` names the directory `root` names."""
    return canonical(path) == canonical(root)


def is_within(path: Path, root: Path) -> bool:
    """Whether `path` names `root` or something inside it."""
    return canonical(path).is_relative_to(canonical(root))


def _named(roots: Iterable[Path]) -> str:
    listed = ", ".join(str(root) for root in roots)
    return listed or "none"


def confine_root(candidate: Path, configured: Iterable[Path]) -> Path:
    """The configured root `candidate` names, as configured; refused when it names none of them."""
    roots = tuple(configured)
    for root in roots:
        if is_root(candidate, root):
            return root
    raise LocationRefused(
        f"A repository root must be one of the configured repositories ({_named(roots)})."
    )


def confine_within(candidate: Path, configured: Iterable[Path]) -> Path:
    """`candidate` resolved, when it lies inside a configured repository; refused otherwise."""
    roots = tuple(configured)
    if any(is_within(candidate, root) for root in roots):
        return canonical(candidate)
    raise LocationRefused(
        f"A location must lie inside the configured repositories ({_named(roots)})."
    )


def require_segment(value: str, *, what: str) -> str:
    """`value`, when it is exactly one path component; refused when joining it could leave a directory."""
    if _SEGMENT.fullmatch(value) is None:
        raise LocationRefused(
            f"{what} must be a single name, without '/', '\\', '..' or a drive or root: got {value!r}."
        )
    return value


def path_inside(root: Path, *parts: str | Path) -> Path:
    """`root` joined with `parts`, refused when the result would lie outside `root`.

    For a path the write path composes from a name a client chose — an artifact id, a collection's
    slug. The joined path is returned as composed, not resolved, so it keeps the spelling of `root`
    that the rest of the write path compares against.
    """
    candidate = root.joinpath(*parts)
    confine_within(candidate, (root,))
    return candidate
