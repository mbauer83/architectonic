"""The generic write path reaches a notation through the capabilities its renderer declares.

`_diagram_instance_labels` imported the ArchiMate occurrences module to relabel a kept body, so every
diagram type's edit ran ArchiMate's reading of `diagram-entities`. That step is now the renderer
capability `InstancePresentationRestatingRenderer`, asked with `isinstance`. The imports recorded
below predate the rule: the register may shrink as each becomes a capability, and may not grow.
"""

from __future__ import annotations

import ast

from tests.support.source_paths import REPO_ROOT

_WRITE_PATH = REPO_ROOT / "src" / "infrastructure" / "write" / "artifact_write"

#: (module, imported notation module). Shrink-only.
_RECORDED: frozenset[tuple[str, str]] = frozenset({
    ("diagram_body_preparation.py", "src.infrastructure.rendering.archimate_relation_rendering"),
    ("diagram_membership.py", "src.infrastructure.rendering.diagram_builder"),
    ("diagram_sync.py", "src.infrastructure.rendering.archimate_entity_declarations"),
    ("diagram_sync.py", "src.infrastructure.rendering.diagram_builder"),
})

_NOTATION_MODULES = ("archimate", "diagram_builder")


def _notation_imports() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    for path in sorted(_WRITE_PATH.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            module = node.module if isinstance(node, ast.ImportFrom) else None
            if module and module.startswith("src.infrastructure.rendering."):
                leaf = module.rsplit(".", 1)[-1]
                if any(marker in leaf for marker in _NOTATION_MODULES):
                    found.add((path.name, module))
    return found


def test_no_new_write_path_module_imports_a_notation() -> None:
    assert _notation_imports() <= _RECORDED, sorted(_notation_imports() - _RECORDED)


def test_the_register_names_only_imports_that_still_exist() -> None:
    assert _RECORDED <= _notation_imports(), sorted(_RECORDED - _notation_imports())
