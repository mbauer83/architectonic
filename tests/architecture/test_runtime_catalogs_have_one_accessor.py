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

**And handlers are given them.** ``install_module_registry`` puts the catalogs on the application and
``runtime_catalogs_dependency`` hands them to a handler — which is what lets a test override them.
Eleven router modules read process state instead, one of them *inside a handler that already took the
dependency and ignored it*, so a test overriding it passed against catalogs the handler never
consulted. Every handler-reachable reader takes the dependency now, threaded into the helpers it calls;
the three modules left are reached from write paths and background threads, where there is no request,
and each says so below.
"""

from __future__ import annotations

import ast
from pathlib import Path

from tests.support.source_paths import REST_ROUTERS, SRC

_BOOTSTRAP = SRC / "infrastructure" / "app_bootstrap.py"

#: The one expression this file is about: the catalogs of the process-wide registry.
_PROCESS_CATALOGS = "build_runtime_catalogs(get_module_registry())"

#: Router modules that read the process's catalogs rather than being given them, and why each has to.
#: Shrink-only: every handler-reachable reader was converted in 0.2.0, and what is left is genuinely
#: request-less. A *new* entry means a handler took process state where the dependency was available.
_READS_PROCESS_STATE: dict[str, str] = {
    "state.py": (
        "One reader left: `resolve_gar` needs the ontology to tell an internal "
        "global-artifact-reference type from an authorable one, and it is reached through "
        "`connection_to_dict` from `diagrams/_context.py`, which the write path calls with no "
        "request in hand. `get_write_deps`/`get_admin_write_deps` were the handler-reachable ones "
        "and they take their catalogs now — all twenty-nine call sites are request handlers, so a "
        "test overriding the dependency used to reach every read and no write at all."
    ),
    "diagrams/_context.py": (
        "Diagram-context helpers reached from both the read routes and the write path; the write "
        "path has no request."
    ),
    "diagrams/_matrix_markdown.py": (
        "Renders a matrix body for the read route and for the writer that stores it — the writer "
        "has no request."
    ),
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
    declared = set(_READS_PROCESS_STATE)
    assert reading - declared == set(), (
        "A router module started reading the process's catalogs. Take "
        f"`runtime_catalogs_dependency`, which a test can override: {sorted(reading - declared)}"
    )
    assert declared - reading == set(), (
        "These no longer read process catalogs — remove them from the list, which only shrinks: "
        f"{sorted(declared - reading)}"
    )
    for name, reason in _READS_PROCESS_STATE.items():
        assert len(reason.strip()) > 30, f"{name} is listed with no reason"


def test_the_scanner_reads_the_expression_it_is_looking_for() -> None:
    # Without this, a normalisation that stopped matching would report a clean tree.
    assert _mentions_process_catalogs(_BOOTSTRAP)
    assert len(_python_sources()) > 300
    assert len(_READS_PROCESS_STATE) > 0
