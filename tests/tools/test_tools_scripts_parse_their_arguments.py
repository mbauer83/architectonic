"""Every runnable script under ``tools/`` parses its arguments before doing anything.

Four of them did not, and the consequence is the same each time: ``--help``, the one interrogative a
command offers, *ran the command*.

* ``export_doc_diagrams.py`` re-exported five SVGs.
* ``generate_types.py`` regenerated ``types.generated.ts``.
* ``generate_timeout_policy.py`` scanned for the substring ``"--check"``, so every other argument —
  ``--help`` included — fell through to the write branch and rewrote a committed document.
* ``dump_openapi.py`` had the worst version, writing the OpenAPI document to a file named ``--help``,
  and grew an ``argparse`` for it in 0.2.0.

Three of the four *write*, so "asking a script what it does" silently modified the working tree. That
is not a usability nit: it is a script whose dry-run interrogative has a side effect, on a repository
where the committed generated artefacts are gated.

The check is a source scan rather than a subprocess sweep, deliberately. What is being forbidden is a
*shape* — a ``main`` that never consults a parser — and a subprocess run of nineteen scripts would
need a repository, a backend and a module registry between them, which is how a guard becomes too
slow to run and then too stale to trust.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "tools"

#: Vendored or generated trees that are not this project's scripts.
_EXCLUDED_PARTS = frozenset({"node_modules", "__pycache__", "dist", ".venv"})


def _runnable_scripts() -> list[Path]:
    """Scripts with a ``__main__`` guard — the ones a person can invoke."""
    found = []
    for path in sorted(TOOLS.rglob("*.py")):
        if _EXCLUDED_PARTS & set(path.parts):
            continue
        if "__main__" in path.read_text(encoding="utf-8"):
            found.append(path)
    return found


def _mentions_a_parser(path: Path) -> bool:
    """Whether the module builds an ``argparse`` parser anywhere.

    An import alone is not enough: the point is that something is *parsed*, and a module can import
    ``argparse`` for a type annotation while still branching on ``sys.argv`` by hand.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(
        isinstance(node, ast.Attribute)
        and node.attr == "ArgumentParser"
        and isinstance(node.value, ast.Name)
        and node.value.id == "argparse"
        for node in ast.walk(tree)
    )


def _scans_argv_for_a_flag(path: Path) -> list[str]:
    """Comparisons of a flag literal against ``argv`` — the substring form, which mis-sorts ``--help``."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare) or not isinstance(node.left, ast.Constant):
            continue
        if not isinstance(node.left.value, str) or not node.left.value.startswith("-"):
            continue
        if any(isinstance(op, ast.In) for op in node.ops):
            offenders.append(ast.unparse(node))
    return offenders


def test_the_scanner_finds_the_scripts_it_means_to_check() -> None:
    scripts = _runnable_scripts()
    assert len(scripts) >= 15, [p.name for p in scripts]
    names = {p.name for p in scripts}
    for expected in ("export_doc_diagrams.py", "generate_types.py", "generate_timeout_policy.py"):
        assert expected in names


@pytest.mark.parametrize("script", _runnable_scripts(), ids=lambda p: p.relative_to(TOOLS).as_posix())
def test_a_runnable_script_builds_an_argument_parser(script: Path) -> None:
    assert _mentions_a_parser(script), (
        f"{script.relative_to(ROOT)} has a __main__ guard and no argparse parser, so `--help` runs "
        "the command instead of describing it. A script that genuinely takes no arguments still "
        "needs the parser — that is how it refuses one."
    )


@pytest.mark.parametrize("script", _runnable_scripts(), ids=lambda p: p.relative_to(TOOLS).as_posix())
def test_no_script_decides_a_flag_by_searching_argv(script: Path) -> None:
    offenders = _scans_argv_for_a_flag(script)
    assert offenders == [], (
        f"{script.relative_to(ROOT)} tests for a flag with `in`, which sorts every *other* argument "
        f"into the else branch — `--help` included: {offenders}"
    )
