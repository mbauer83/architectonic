"""Architectural fitness function: `combined_artifact_index` must only ever be called with a
root pair that came from `resolve_workspace_repo_roots` (or the equivalent already-resolved
`_repo_root`/`_enterprise_root` state threaded through `gui_state`/`context.py`), never a
caller-supplied arbitrary pair.

`combined_artifact_index` is deliberately narrower than `shared_artifact_index` (exactly two
required positional `Path` arguments) specifically so this discipline is checkable: a call
site passing a literal
`Path(...)` construction or a string-literal path directly as an argument would bypass whatever
resolution the rest of the codebase relies on. This test is the mechanical guard against that —
in the same spirit as `tests/architecture/test_index_broadcast_policy.py`'s allowlist audit.
"""

from __future__ import annotations

import re
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_SRC_ROOT = _PROJECT_ROOT / "src"
_CALL_RE = re.compile(r"(?<!def )combined_artifact_index\(([^)]*)\)")


def test_combined_artifact_index_is_never_called_with_a_locally_constructed_path() -> None:
    violations: list[str] = []
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        rel = path.relative_to(_PROJECT_ROOT).as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            match = _CALL_RE.search(line)
            if match is None:
                continue
            args = match.group(1)
            if "Path(" in args or '"' in args or "'" in args:
                violations.append(f"{rel}:{lineno}: {line.strip()}")
    assert not violations, (
        "Found a combined_artifact_index(...) call with a literal/locally-constructed Path "
        "argument — this bypasses resolve_workspace_repo_roots (or the equivalent already-"
        "resolved gui_state/context.py roots) and could combine two paths that were never "
        "meant to be treated as the active engagement/enterprise pair. Resolve the roots "
        "through resolve_workspace_repo_roots (or thread through the already-resolved roots) "
        "instead of constructing Path(...) inline at the call site.\n" + "\n".join(violations)
    )
