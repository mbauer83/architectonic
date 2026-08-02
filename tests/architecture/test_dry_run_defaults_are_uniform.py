"""`dry_run` means one thing on every write, and omitting it never commits.

Twenty-nine write operations take the flag. Twenty-five defaulted it to `True` — plan unless you say
otherwise — and four did not: the three document routes and the viewpoint delete. So the same flag
meant "preview" on most of the surface and "commit" on the rest, and a client written against the
majority silently committed writes it meant to preview.

Two mistakes were cancelling out, which is why it survived. The GUI's `deleteDocument` and
`deleteViewpointDefinition` sent no `dry_run` at all, relying on those outlier defaults to actually
delete — while the six sibling deletes in the same adapters pass `dry_run: false` explicitly. Fix
either side alone and document deletion silently becomes a no-op; neither side is wrong on its own
reading. That is a Shape-A crossing (handoff §1.1) between a route's default and a caller's omission,
and no test on either side could have seen it.

The flag is a *safety* default, so the safe value is the uniform one. This scans the declarations
rather than calling the routes, because what is being constrained is a default — the value a caller
gets by saying nothing, which no request can demonstrate the absence of.
"""

from __future__ import annotations

import ast

from tests.support.source_paths import REST_ROUTERS


def _dry_run_defaults() -> dict[str, bool]:
    """Every `dry_run` default the write surface declares, by `file:line`.

    Both forms count: a query/path parameter on a handler, and a field on a request-body model. They
    are the same decision — what happens when the caller says nothing — reached two ways.
    """
    found: dict[str, bool] = {}
    for path in sorted(REST_ROUTERS.rglob("*.py")):
        if "__pycache__" in path.as_posix():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        where = path.relative_to(REST_ROUTERS).as_posix()
        for node in ast.walk(tree):
            # A handler parameter: `dry_run: bool = True`.
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                args = node.args
                positional = args.posonlyargs + args.args
                for argument, default in zip(
                    positional[len(positional) - len(args.defaults):], args.defaults, strict=True
                ):
                    if argument.arg == "dry_run" and isinstance(default, ast.Constant):
                        found[f"{where}:{argument.lineno}"] = bool(default.value)
                for argument, kw_default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
                    if argument.arg == "dry_run" and isinstance(kw_default, ast.Constant):
                        found[f"{where}:{argument.lineno}"] = bool(kw_default.value)
            # A model field: `dry_run: bool = True` at class scope.
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id == "dry_run" and isinstance(node.value, ast.Constant):
                    found[f"{where}:{node.lineno}"] = bool(node.value.value)
    return found


def test_the_scanner_finds_the_declarations_it_means_to_check() -> None:
    # Without this, a scan that stopped matching would report a uniformly safe surface.
    defaults = _dry_run_defaults()
    assert len(defaults) >= 25, sorted(defaults)
    assert any("documents.py" in where for where in defaults)
    assert any("admin.py" in where for where in defaults)


def test_no_write_commits_when_the_caller_says_nothing() -> None:
    committing = sorted(where for where, default in _dry_run_defaults().items() if default is False)
    assert committing == [], (
        "these declare `dry_run=False`, so a caller who omits the flag commits a write they may have "
        "meant to preview. The flag is a safety default and the surface has one meaning for it: "
        f"{committing}"
    )
