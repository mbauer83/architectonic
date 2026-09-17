"""Only the REST and backend layers import the web framework; nothing else may, even lazily.

`fastapi` and `uvicorn` are in the `gui` dependency group. Everything that builds the module
registry — the diagram types, the write path, the renderers, the type generator — imports
`app_bootstrap`, and one `Request` annotation in that module made all of them need the framework
at import time. The first real release-workflow run failed on exactly that, with no web server in
sight. Asserted over the code, lazy imports included, because the leak was one line.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB_FRAMEWORK = ("fastapi", "starlette", "uvicorn")
ALLOWED_PREFIXES = ("src/infrastructure/rest/", "src/infrastructure/backend/")


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


def test_no_module_outside_the_rest_and_backend_layers_imports_the_web_framework() -> None:
    offenders = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(ALLOWED_PREFIXES):
            continue
        leaked = sorted(m for m in _imports(path) if m.split(".")[0] in WEB_FRAMEWORK)
        if leaked:
            offenders.append(f"{rel}: {', '.join(leaked)}")
    assert offenders == [], "\n".join(offenders)
