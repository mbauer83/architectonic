"""The write path resolves a *stored* diagram's type without assuming a module provides it.

A repository outlives any one deployment's module set. A diagram names its type in its own
frontmatter, and modules are conditional: the assurance family requires the `confidential_store`
capability, so on a host without the store `bowtie` is a type the catalog holds and the registry
does not. `find_diagram_type` / `find_renderer` answer that honestly; `get_diagram_type` raises,
which is right only where the caller *chose* the type from the registry a moment earlier.

**Why a gate and not a note.** The write path used the raising one, and it passed locally for weeks.
The module registry is `lru_cache`d per process, so whether the assurance module is registered
depends on which test built the registry first in an xdist worker — the full suite was green while
the same file run alone produced 88 errors, which is what CI then reported. A rule that only holds
when the tests happen to run in a particular order is not a rule, so the shape is checked here
instead: source-level, order-independent, and true on any machine.

The rule is scoped to the write package because that is where a stored type is resolved during an
ordinary edit. Rendering is exempt and says why below.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from tests.support.source_paths import REPO_ROOT

_WRITE_PACKAGE = REPO_ROOT / "src" / "infrastructure" / "write"

#: Raising lookups that are correct where they are, each for a reason this test has to state.
_EXEMPT: dict[Path, str] = {
    Path("src/infrastructure/write/artifact_write/diagram_render.py"): (
        "rendering a body *is* the renderer's operation, so there is no untouched answer to give — "
        "a type no module provides cannot be rendered, and refusing is the honest outcome."
    ),
}


def _raising_lookups(path: Path) -> list[int]:
    """Lines where this file calls `get_diagram_type`, by any spelling of the import."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Name) and node.func.id == "get_diagram_type")
            or (isinstance(node.func, ast.Attribute) and node.func.attr == "get_diagram_type")
        )
    )


def _write_path_sources() -> list[Path]:
    return sorted(p for p in _WRITE_PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)


def test_the_write_package_is_where_this_rule_applies() -> None:
    """Without this, moving the package would make the rule vacuously satisfied."""
    assert _write_path_sources(), f"no sources under {_WRITE_PACKAGE}"


def test_nothing_in_the_write_path_resolves_a_stored_type_by_raising() -> None:
    offenders: dict[str, list[int]] = {}
    for path in _write_path_sources():
        relative = path.relative_to(REPO_ROOT)
        if relative in _EXEMPT:
            continue
        if lines := _raising_lookups(path):
            offenders[str(relative)] = lines

    assert offenders == {}, (
        "these resolve a stored diagram's type with the raising accessor, so a repository holding a "
        f"diagram whose module this deployment does not register breaks an ordinary edit: {offenders}. "
        "Use `find_diagram_type` / `find_renderer` from `src.infrastructure.diagram_type_registry` "
        "and decide what an absent module means here — for a body, it means untouched."
    )


@pytest.mark.parametrize("path,reason", sorted(_EXEMPT.items()))
def test_every_exemption_is_real_and_carries_its_reason(path: Path, reason: str) -> None:
    """An exemption for a file that no longer raises is a rule nobody is following any more."""
    assert (REPO_ROOT / path).is_file(), f"{path} is exempted and is not there"
    assert _raising_lookups(REPO_ROOT / path), f"{path} no longer raises — drop the exemption"
    assert len(reason) > 60, f"{path}: an exemption with no stated reason is a hole"
