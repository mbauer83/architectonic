"""WU-0.3b: Every artifact-creation path delegates to IdentifierAllocator.

Static import guard: the five write-path files that previously called
generate_entity_id / generate_diagram_id directly must no longer do so; they
must import get_default_allocator instead.  Groups are excluded per plan D21.
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).parents[3] / "src"

_OLD_CALLERS = [
    SRC / "infrastructure/write/artifact_write/entity.py",
    SRC / "infrastructure/write/artifact_write/document.py",
    SRC / "infrastructure/write/artifact_write/admin_entity_ops.py",
    SRC / "infrastructure/write/artifact_write/_artifact_deduplication.py",
    SRC / "infrastructure/write/artifact_write/global_artifact_reference.py",
    SRC / "infrastructure/write/artifact_write/matrix.py",
    SRC / "infrastructure/gui/routers/_diagram_write.py",
    SRC / "infrastructure/gui/routers/admin.py",
]

_FORBIDDEN_DIRECT = {"generate_entity_id", "generate_diagram_id"}
_REQUIRED_ALLOCATOR_IMPORT = "get_default_allocator"


def _ast_names(path: Path) -> set[str]:
    """Return all Name and Attribute ids from a parsed AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def test_old_callers_no_longer_import_generate_functions():
    """Files that used to call generate_entity_id/generate_diagram_id directly must not do so."""
    violations: list[str] = []
    for path in _OLD_CALLERS:
        source = path.read_text(encoding="utf-8")
        for fn in _FORBIDDEN_DIRECT:
            if fn in source:
                violations.append(f"{path.name}: still references {fn!r}")
    assert not violations, "\n".join(violations)


def test_old_callers_import_allocator():
    """Files that allocate IDs must import get_default_allocator."""
    missing: list[str] = []
    for path in _OLD_CALLERS:
        source = path.read_text(encoding="utf-8")
        if _REQUIRED_ALLOCATOR_IMPORT not in source:
            missing.append(f"{path.name}: missing import of {_REQUIRED_ALLOCATOR_IMPORT!r}")
    assert not missing, "\n".join(missing)
