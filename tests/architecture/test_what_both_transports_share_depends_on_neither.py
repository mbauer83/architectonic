"""A module that sits below both transports imports neither of them, lazily or not.

`diagram_composition` exists so REST and MCP save a canvas the same way, and it took the body field
that re-homes a diagram (`Rehomeable`) from REST's contracts; the MCP scratchpad tools took their
request models from there too. Dependencies then pointed outward from the very module meant to be
shared. Every `*_wire` module, and the two compositions they serve, are held to it here.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.support.source_paths import REPO_ROOT, SRC

_INFRASTRUCTURE = SRC / "infrastructure"
_TRANSPORTS = ("src.infrastructure.rest", "src.infrastructure.mcp")


def _shared_modules() -> list[Path]:
    return sorted(
        [*_INFRASTRUCTURE.glob("*_wire.py"), _INFRASTRUCTURE / "diagram_composition.py",
         _INFRASTRUCTURE / "diagram_creation.py"]
    )


def _transport_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    named: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            named.append(node.module)
        elif isinstance(node, ast.Import):
            named.extend(alias.name for alias in node.names)
    return sorted(module for module in named if module.startswith(_TRANSPORTS))


def test_the_shared_modules_are_where_this_rule_says() -> None:
    names = {path.name for path in _shared_modules()}
    assert {"artifact_home_wire.py", "scratchpad_wire.py", "diagram_composition.py"} <= names
    assert all(path.is_file() for path in _shared_modules())


def test_nothing_both_transports_share_imports_either_transport() -> None:
    offenders = {
        str(path.relative_to(REPO_ROOT)): found
        for path in _shared_modules()
        if (found := _transport_imports(path))
    }
    assert offenders == {}, f"move what these take from a transport into a module below both: {offenders}"
