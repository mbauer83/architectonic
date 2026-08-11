"""Where the source packages a static check reads actually live.

Several fitness functions parse source rather than importing it — a decorator's arguments, a handler's
returned dict literals, whether a call goes through the allocator. Each one therefore names a package
by path, and each one had spelled that path itself.

The 0.2.0 rename of ``src/infrastructure/gui`` to ``src/infrastructure/rest`` is what makes that a
problem worth one module: nothing imports these strings, so nothing broke at the rename, and finding
every copy meant grepping the tree for the segments in whatever order each module happened to join
them. A path a check depends on and no import mentions belongs in one place.

Only paths more than one module reads. A check that parses one file names that file where it is used;
naming it here would put a constant between a test and the single thing it is about.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

#: The repository root: two levels above ``tests/support``.
REPO_ROOT = Path(__file__).resolve().parents[2]

SRC = REPO_ROOT / "src"

#: The developer scripts. Not `src`, and checks that hold a rule for the whole codebase have to say so
#: explicitly or silently exempt them — which is how `tools/` came to be outside several of them.
TOOLS = REPO_ROOT / "tools"

#: The REST routers package — the handlers, their decorators and their authorization calls.
REST_ROUTERS = SRC / "infrastructure" / "rest" / "routers"

#: The write boundary: every path that creates or edits an artifact.
ARTIFACT_WRITE = SRC / "infrastructure" / "write" / "artifact_write"

#: Directories under a search root that hold vendored, generated or cached files rather than code this
#: repository authors. A walk that forgets `__pycache__` reads compiled bytecode and fails on the decode.
_NOT_AUTHORED_HERE = frozenset({"node_modules", "__pycache__", ".venv"})


def python_sources(*roots: Path) -> Iterator[Path]:
    """Every Python file this repository authors under `roots`, sorted.

    A rule that holds for the whole codebase needs the same walk each time it is asserted, and the walks
    had started to differ in which directories they skipped — which decides whether the check reads a
    `.pyc` and dies, or silently covers less than it claims.
    """
    yield from sorted(
        path
        for root in roots
        for path in root.rglob("*.py")
        if _NOT_AUTHORED_HERE.isdisjoint(path.parts)
    )
