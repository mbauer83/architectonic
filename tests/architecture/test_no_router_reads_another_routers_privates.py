"""A router does not import another router package's private modules or names.

A candidate's picture routes imported `_geometry` and `_repo_root` from the diagram layout router and
`_read_diagram_impl` from the diagram read router, so each router's reasons to change leaked into the
other, and the picture reading they shared could not be reached without importing a router. What both
answer from now has an owner below either one: `src/infrastructure/picture_reading/` for the reading,
`routers/picture_reads.py` for its REST side.

The rule: inside `src/infrastructure/rest/routers/`, a module may import a private module (`_x`) or a
private name only from its own package. The shared helpers at the routers root (`_openapi`,
`_candidate_access`, …) are the routers' common ground and stay importable by every router. The crossings
that predate the rule are recorded below, shrink-only: each is a helper one router package owns and
another borrows, and the next change to either should give it a shared owner.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.support.source_paths import REST_ROUTERS

_PREFIX = "src.infrastructure.rest.routers"

#: Crossings that predate the rule, by importing module. Shrink-only: a new entry is a new leak.
_RECORDED: dict[str, frozenset[str]] = {
    "assurance/_write.py": frozenset({"src.infrastructure.rest.routers.entities._creator"}),
    "authoring_guidance.py": frozenset({"src.infrastructure.rest.routers.entities._filter"}),
    "diagrams/_context.py": frozenset({"src.infrastructure.rest.routers.viewpoints._scope"}),
    "diagrams/_palette.py": frozenset({"src.infrastructure.rest.routers.entities._display_search"}),
    "diagrams/_serving.py": frozenset({"src.infrastructure.rest.routers.viewpoints._freshness"}),
    "entities/_display_search.py": frozenset({
        "src.infrastructure.rest.routers.diagrams._context",
        "src.infrastructure.rest.routers.viewpoints._scope",
    }),
}


def _package_of(path: Path) -> tuple[str, ...]:
    return path.relative_to(REST_ROUTERS).parent.parts


def _crossings(path: Path) -> list[str]:
    return _crossings_in(path.read_text(encoding="utf-8"), _package_of(path))


def _crossings_in(source: str, own: tuple[str, ...]) -> list[str]:
    """The private modules and names *source*, a module of package *own*, imports from another router package."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ImportFrom) or not node.module or not node.module.startswith(_PREFIX + "."):
            continue
        parts = tuple(node.module.removeprefix(_PREFIX + ".").split("."))
        package, leaf = parts[:-1], parts[-1]
        if not package or package == own:
            continue
        if leaf.startswith("_"):
            found.append(f"{node.module}")
        found.extend(f"{node.module}.{alias.name}" for alias in node.names if alias.name.startswith("_"))
    return found


def _all_crossings() -> dict[str, frozenset[str]]:
    return {
        path.relative_to(REST_ROUTERS).as_posix(): frozenset(crossing)
        for path in sorted(REST_ROUTERS.rglob("*.py"))
        if (crossing := _crossings(path))
    }


def test_no_router_imports_another_router_packages_privates() -> None:
    offenders = {
        module: sorted(crossing - _RECORDED.get(module, frozenset()))
        for module, crossing in _all_crossings().items()
        if crossing - _RECORDED.get(module, frozenset())
    }
    assert offenders == {}, (
        "These router modules import another router package's private modules or names. Give what they "
        f"share an owner both import (`routers/picture_reads.py` is one): {offenders}"
    )


def test_the_recorded_crossings_only_shrink() -> None:
    found = _all_crossings()
    healed = {
        module: sorted(recorded - found.get(module, frozenset()))
        for module, recorded in _RECORDED.items()
        if recorded - found.get(module, frozenset())
    }
    assert healed == {}, f"These crossings are gone; remove them from the record, which only shrinks: {healed}"


def test_the_rule_sees_a_crossing() -> None:
    """A guard on the guard: the imports the candidate picture routes made are ones it reports, and a
    module's own package is not a crossing."""
    old = (
        "from src.infrastructure.rest.routers.diagrams._layout import DrawShapesBody, _geometry\n"
        "from src.infrastructure.rest.routers.diagrams.router import _read_diagram_impl\n"
    )
    assert _crossings_in(old, ()) == [
        "src.infrastructure.rest.routers.diagrams._layout",
        "src.infrastructure.rest.routers.diagrams._layout._geometry",
        "src.infrastructure.rest.routers.diagrams.router._read_diagram_impl",
    ]
    assert _crossings_in(old, ("diagrams",)) == []
