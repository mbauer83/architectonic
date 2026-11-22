"""Each kind's verifier declares the rule codes its modules emit, exactly.

A declaration nothing checks drifts: a rule added to a verifier's modules would emit a code its
`RULE_CODES` does not name, and the declaration would claim less than the verifier checks. So the
declaration is held equal to the codes spelled anywhere in the modules the verifier imports, followed
through the project's own imports. That over-counts a shared rule module a kind reaches but does not
call — a declaration is what a verifier *can* emit, and an honest over-count is the safe side.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from src.application.verification import (
    _verifier_diagram,
    _verifier_document,
    _verifier_entity,
    _verifier_icon,
    _verifier_outgoing,
    artifact_verifier_syntax,
)
from tests.support.source_paths import REPO_ROOT

_CODE = re.compile(r"\A[EW]\d{3}\Z")
#: The facade imports every verifier, so following it would make each declare all of them.
_NOT_FOLLOWED = frozenset({
    "src.application.verification.artifact_verifier",
    "src.application.verification.artifact_verifier_registry",
})


def _source(module: str) -> Path | None:
    relative = module.replace(".", "/")
    for candidate in (REPO_ROOT / f"{relative}.py", REPO_ROOT / relative / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _imports(tree: ast.Module) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src."):
            found |= {node.module, *(f"{node.module}.{alias.name}" for alias in node.names)}
        elif isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names if alias.name.startswith("src.")}
    return {module for module in found if _source(module) is not None}


def _codes_spelled(tree: ast.Module) -> set[str]:
    declared = {
        id(constant)
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign | ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "RULE_CODES" for t in
                (node.targets if isinstance(node, ast.Assign) else [node.target]))
        for constant in ast.walk(node)
    }
    return {
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and _CODE.match(node.value)
        and id(node) not in declared
    }


def _reachable_codes(start: str) -> set[str]:
    seen: set[str] = set()
    pending = [start]
    codes: set[str] = set()
    while pending:
        module = pending.pop()
        if module in seen or (module in _NOT_FOLLOWED and module != start):
            continue
        seen.add(module)
        source = _source(module)
        assert source is not None, module
        tree = ast.parse(source.read_text(encoding="utf-8"))
        codes |= _codes_spelled(tree)
        pending.extend(_imports(tree))
    return codes


@pytest.mark.parametrize(
    "module",
    [_verifier_entity, _verifier_outgoing, _verifier_diagram, _verifier_document, _verifier_icon,
     artifact_verifier_syntax],
    ids=lambda module: module.__name__.rsplit(".", 1)[-1],
)
def test_a_verifier_declares_exactly_the_codes_its_modules_emit(module) -> None:
    emitted = _reachable_codes(module.__name__)

    assert module.RULE_CODES == emitted, (
        f"undeclared: {sorted(emitted - module.RULE_CODES)}; declared but emitted nowhere: "
        f"{sorted(module.RULE_CODES - emitted)}"
    )
