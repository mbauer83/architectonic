"""A router test must mount its router on an app that carries the product's response contracts.

``tests/support/api_app.build_api_app`` exists because a router on a bare ``FastAPI()`` behaves
differently from the same router in the product: no typed error envelope, no request id, no declared
``Cache-Control``. A test written against the bare app asserts a shape no client receives, which is
how a confidentiality header came to be verified by a green suite and absent in production.

The helper alone did not hold the line — thirty-six modules still composed their own app, and the
seven converted by hand stayed converted only until the next module was written. So the rule is a
test: a module that constructs ``FastAPI`` *and* calls ``include_router`` is composing an app the
helper should have built.

Keyed on ``include_router`` rather than on constructing ``FastAPI``, because mounting something that
is not a router is a different thing and does not need the contracts. ``test_spa_static_fallback``
builds a bare app to ``mount`` a static-files handler on it; nothing about a typed error envelope is
in question there, and listing it as an exemption would be an entry a reader has to check against a
rule it was never subject to.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TESTS_ROOT = _REPO_ROOT / "tests"

#: Modules that legitimately compose their own app, and why.
_EXEMPT: dict[str, str] = {
    "tests/support/api_app.py": (
        "The helper itself: this is the one place the product's contracts are assembled."
    ),
    "tests/support/route_introspection.py": (
        "Reads a router's declared OpenAPI paths. It never issues a request, so no response passes "
        "through the middleware the contracts install — and including them would make the "
        "introspection depend on them."
    ),
}


def _module_calls(tree: ast.Module) -> tuple[bool, bool]:
    """Whether the module constructs ``FastAPI`` and whether it calls ``include_router``."""
    constructs = False
    includes = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        if isinstance(function, ast.Name) and function.id == "FastAPI":
            constructs = True
        elif isinstance(function, ast.Attribute):
            if function.attr == "FastAPI":
                constructs = True
            elif function.attr == "include_router":
                includes = True
    return constructs, includes


def _offenders() -> list[str]:
    found = []
    for path in sorted(_TESTS_ROOT.rglob("*.py")):
        relative = path.relative_to(_REPO_ROOT).as_posix()
        if relative in _EXEMPT:
            continue
        constructs, includes = _module_calls(ast.parse(path.read_text(encoding="utf-8")))
        if constructs and includes:
            found.append(relative)
    return found


def test_no_test_module_mounts_a_router_on_an_app_it_built_itself() -> None:
    offenders = _offenders()
    assert offenders == [], (
        "These modules compose their own FastAPI app and mount a router on it. Use "
        "`tests.support.api_app.build_api_app(*routers)`, which carries the typed error envelope, "
        "the request id and the Cache-Control directive the product's app carries — a response "
        "asserted against a bare app is a shape no client receives:\n  "
        + "\n  ".join(offenders)
    )


def test_every_exemption_is_a_module_that_would_otherwise_be_refused() -> None:
    # A stale exemption is the failure mode this whole file exists to prevent, one level up: it
    # excuses whatever is later written under that path. An exemption earns its place only while the
    # rule would actually catch the module.
    for relative, reason in _EXEMPT.items():
        path = _REPO_ROOT / relative
        assert path.is_file(), f"{relative} is exempt but does not exist"
        assert reason.strip(), f"{relative} is exempt with no reason"
        constructs, includes = _module_calls(ast.parse(path.read_text(encoding="utf-8")))
        assert constructs and includes, (
            f"{relative} no longer builds its own app and mounts a router on it. Drop the exemption."
        )


def test_the_scanner_reads_the_construction_it_is_looking_for() -> None:
    # Without this, a walk that stopped matching would report zero offenders over an empty scan.
    helper = ast.parse((_REPO_ROOT / "tests/support/api_app.py").read_text(encoding="utf-8"))
    assert _module_calls(helper) == (True, True)
    unrelated = ast.parse("from fastapi import FastAPI\napp = FastAPI()\n")
    assert _module_calls(unrelated) == (True, False)
    assert len(list(_TESTS_ROOT.rglob("*.py"))) > 200
