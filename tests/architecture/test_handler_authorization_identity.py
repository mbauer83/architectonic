"""Every mutating handler passes the operation id its own decorator declares.

This is the per-mutator guard for the defect that a set equality cannot see. The path used to be
written down in four places, and the copy inside each handler was invisible to any test comparing
two registries: rename the decorator, leave the ``authorized_write`` tuple, and the live write
failed closed while the suite stayed green.

The oracle here is the **source**, not the manifest: the decorator's method and path are read from
the router module's syntax tree and compared against the manifest row of whatever operation id the
handler actually passes. A handler that passes a valid id belonging to a different operation fails
too, which a lookup-succeeds check would not catch.

Static rather than behavioural on purpose. Driving all 38 mutators over HTTP needs a valid body and
a plausible repository state per mutator, and would test the fixtures at least as much as the
identity. ``build_rest_request`` already fails an unmanifested id closed at request time, and
`tests/tools/test_gui_router_write_authorization.py` covers success and denial end-to-end for a
representative subset.
"""

from __future__ import annotations

import ast

import pytest

from src.infrastructure.rest.route_policy import BY_OPERATION
from src.infrastructure.rest.routers.rest_mutation_manifest import REST_MUTATION_MANIFEST
from tests.support.source_paths import REST_ROUTERS

_ROUTERS = REST_ROUTERS

_AUTHORIZED_WRITE_NAMES = frozenset({"authorized_write", "authorized_write_async"})


def _router_prefixes(tree: ast.AST) -> dict[str, str]:
    """Router variable → its ``APIRouter(prefix=…)``, so a decorator path can be completed.

    The admin router mounts at ``/admin/api``, and its decorators are therefore relative. Reading
    the prefix rather than special-casing the module keeps this true for the next router that takes
    one.
    """
    prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name != "APIRouter":
            continue
        prefix = next(
            (
                str(keyword.value.value)
                for keyword in node.value.keywords
                if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant)
            ),
            "",
        )
        for target in node.targets:
            if isinstance(target, ast.Name):
                prefixes[target.id] = prefix
    return prefixes


def _decorator_route(
    node: ast.FunctionDef | ast.AsyncFunctionDef, prefixes: dict[str, str]
) -> tuple[str, str] | None:
    """``(METHOD, path)`` from a ``@router.<verb>("<path>")`` decorator, or None."""
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
            continue
        verb = decorator.func.attr.upper()
        if verb not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
            continue
        if decorator.args and isinstance(decorator.args[0], ast.Constant):
            router = decorator.func.value
            prefix = prefixes.get(router.id, "") if isinstance(router, ast.Name) else ""
            return verb, prefix + str(decorator.args[0].value)
    return None


def _authorized_write_operations(node: ast.AST) -> list[str]:
    """Operation ids passed to ``authorized_write`` anywhere inside *node*."""
    operations = []
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        name = (
            call.func.attr
            if isinstance(call.func, ast.Attribute)
            else call.func.id
            if isinstance(call.func, ast.Name)
            else None
        )
        if name not in _AUTHORIZED_WRITE_NAMES:
            continue
        first = call.args[0] if call.args else None
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            operations.append(first.value)
    return operations


def _handler_authorizations() -> list[tuple[str, str, tuple[str, str], str]]:
    """``(module, handler, decorator route, operation id)`` for every gated handler."""
    found = []
    # Recursive: the routers are a package per served surface, and a flat glob would scan none of
    # the handlers inside them — a gate that silently checks nothing.
    for module in sorted(_ROUTERS.rglob("*.py")):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        prefixes = _router_prefixes(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            route = _decorator_route(node, prefixes)
            if route is None:
                continue
            for operation in _authorized_write_operations(node):
                found.append((module.name, node.name, route, operation))
    return found


@pytest.fixture(scope="module")
def authorizations() -> list[tuple[str, str, tuple[str, str], str]]:
    found = _handler_authorizations()
    # A guard on the parser: if the decorator or call shape changed, this file would silently
    # verify nothing at all.
    assert len(found) >= 20, f"only found {len(found)} gated handlers — the parser is stale"
    return found


def test_every_gated_handler_names_a_manifested_operation(
    authorizations: list[tuple[str, str, tuple[str, str], str]],
) -> None:
    unmanifested = [
        (module, handler, operation)
        for module, handler, _route, operation in authorizations
        if operation not in REST_MUTATION_MANIFEST
    ]
    assert unmanifested == [], f"handlers passing an unclassified operation: {unmanifested}"


def test_every_gated_handler_names_the_operation_its_decorator_declares(
    authorizations: list[tuple[str, str, tuple[str, str], str]],
) -> None:
    """The stale-tuple regression, per mutator: the identity a handler authorizes under is the
    identity of the route it is mounted at."""
    mismatched = []
    for module, handler, route, operation in authorizations:
        row = BY_OPERATION.get(operation)
        if row is None:
            continue  # reported by the test above
        if row.key != route:
            mismatched.append((f"{module}:{handler}", route, operation, row.key))
    assert mismatched == [], f"handler authorizes under a different route than it serves: {mismatched}"


def test_no_gated_handler_passes_a_route_tuple(
    authorizations: list[tuple[str, str, tuple[str, str], str]],
) -> None:
    """A tuple would mean the path is written down in the handler again, which is the shape of
    the original defect. Every recovered first argument is a string operation id."""
    for _module, _handler, _route, operation in authorizations:
        assert isinstance(operation, str)
        assert "/" not in operation, operation
