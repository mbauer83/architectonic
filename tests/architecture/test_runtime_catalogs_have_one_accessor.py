"""The catalogs for *this process* are built in one place.

``build_runtime_catalogs(get_module_registry())`` — the catalogs of the process-wide registry — is a
pure function of a singleton, and twelve modules across five packages each wrapped it in a private
``@lru_cache(maxsize=1)``: the same three lines, added wherever a caller next needed catalogs and had
none to hand. Twelve memos of one value, and twelve places to remember if the registry ever stops
being immutable after bootstrap.

The rule is narrow on purpose. ``build_runtime_catalogs`` with an *explicitly supplied* registry is a
different question — a CLI, an upgrade step or the complete-vocabulary catalog each builds catalogs
for a registry it names, and there is nothing shared to consolidate. What is refused is a second
private memo of the process singleton's catalogs.

Twelve was the memoised count. Twenty-eight further sites called the same expression *inline*, so
they rebuilt the whole thing — merging every ontology's specialization catalogue and profile registry —
on each call. All forty go through the one memo now.

**What is not yet true, and is recorded rather than asserted.** ``install_module_registry`` puts the
catalogs on the application and ``runtime_catalogs_dependency`` hands them to a handler — which is
what lets a test override them. Nine router modules still read process state instead, so a test
overriding the dependency does not reach them and passes against catalogs the handler never
consulted. Converting each is a signature change per handler, and several of the readers are
module-level helpers with no request in hand. The list below is the work; it must shrink, never grow.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.support.source_paths import REST_ROUTERS, SRC

_BOOTSTRAP = SRC / "infrastructure" / "app_bootstrap.py"

#: The one expression this file is about: the catalogs of the process-wide registry.
_PROCESS_CATALOGS = "build_runtime_catalogs(get_module_registry())"

#: Router modules still reading process catalogs rather than taking the dependency. Shrink-only.
_READS_PROCESS_STATE = {
    "assurance/_aibom.py",
    "connections/read_routes.py",
    "connections/router.py",
    "diagrams/_context.py",
    "diagrams/_matrix_markdown.py",
    "entities/listing.py",
    "entities/router.py",
    "entities/search.py",
    "state.py",
    "viewpoints/_write.py",
    "viewpoints/authoring.py",
}


def _python_sources() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.as_posix())


def _mentions_process_catalogs(path: Path) -> bool:
    """Whether the source builds catalogs from the process registry, however it is spaced."""
    normalised = "".join(path.read_text(encoding="utf-8").split())
    return "".join(_PROCESS_CATALOGS.split()) in normalised


def test_only_the_bootstrap_builds_the_process_catalogs() -> None:
    offenders = sorted(
        path.relative_to(SRC.parent).as_posix()
        for path in _python_sources()
        if path != _BOOTSTRAP and _mentions_process_catalogs(path)
    )
    assert offenders == [], (
        "These modules build the process registry's catalogs themselves. Call "
        "`app_bootstrap.process_runtime_catalogs()` — or, in a request handler, take them from "
        f"`runtime_catalogs_dependency`: {offenders}"
    )


def test_the_bootstrap_builds_them_behind_one_memo() -> None:
    tree = ast.parse(_BOOTSTRAP.read_text(encoding="utf-8"))
    wanted = "".join(_PROCESS_CATALOGS.split())
    holders = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and wanted in "".join(ast.unparse(node).split())
    ]
    assert holders == ["process_runtime_catalogs"], holders
    assert _mentions_process_catalogs(_BOOTSTRAP)


def test_the_routers_reading_process_state_are_exactly_the_recorded_ones() -> None:
    reading = {
        path.relative_to(REST_ROUTERS).as_posix()
        for path in sorted(REST_ROUTERS.rglob("*.py"))
        if "process_runtime_catalogs" in path.read_text(encoding="utf-8")
    }
    assert reading - _READS_PROCESS_STATE == set(), (
        "A router module started reading the process's catalogs. Take "
        f"`runtime_catalogs_dependency`, which a test can override: {sorted(reading - _READS_PROCESS_STATE)}"
    )
    assert _READS_PROCESS_STATE - reading == set(), (
        "These no longer read process catalogs — remove them from the list, which only shrinks: "
        f"{sorted(_READS_PROCESS_STATE - reading)}"
    )


def test_the_scanner_reads_the_expression_it_is_looking_for() -> None:
    # Without this, a normalisation that stopped matching would report a clean tree.
    assert _mentions_process_catalogs(_BOOTSTRAP)
    assert len(_python_sources()) > 300
    assert len(_READS_PROCESS_STATE) > 0
