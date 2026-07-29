"""AST-based dependency policy test.

Walks every *.py under src/, collects all Import/ImportFrom nodes including
lazy (function-nested) ones, classifies each module's package role, and
asserts the matrix from docs/architecture/dependency-policy.md.

Runs in baseline mode: architecture_baseline.json lists current known
violations; the test fails only on *new* violations not present there.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_BASELINE_PATH = Path(__file__).parent / "architecture_baseline.json"
_SRC_ROOT = _PROJECT_ROOT / "src"
_MUTATION_ADAPTER = "src.infrastructure.mutation_adapters"
_MUTATION_ADAPTER_IMPORTERS = frozenset(
    {
        "src/infrastructure/git/enterprise_git_ops.py",
        "src/infrastructure/git/git_sync_m4.py",
        "src/infrastructure/git/repair_adapter.py",
        "src/infrastructure/repository_upgrade/guard.py",
        "src/infrastructure/write/artifact_write/_cascade_helpers.py",
        "src/infrastructure/write/artifact_write/_group_fs.py",
        "src/infrastructure/write/artifact_write/cascade_delete.py",
        "src/infrastructure/write/artifact_write/m4_transaction.py",
    }
)

# Entry-point modules that wire the full object graph; allowed to import from any package.
_COMPOSITION_ROOTS: frozenset[str] = frozenset(
    {
        "src/infrastructure/app_bootstrap.py",
        "src/infrastructure/cli/artifact_query_cli.py",
        "src/infrastructure/cli/arch_assurance.py",
        "src/infrastructure/cli/_assurance_commands.py",
        "src/infrastructure/cli/_security_commands.py",
        "src/infrastructure/mcp/arch_mcp_stdio.py",
        "src/infrastructure/mcp/arch_mcp_stdio_write.py",
        "src/infrastructure/mcp/arch_mcp_stdio_assurance.py",
        "src/infrastructure/mcp/mcp_artifact_server.py",
        "src/infrastructure/mcp/mcp_assurance_server.py",
        "src/infrastructure/gui/gui_server.py",
        "src/infrastructure/backend/arch_backend.py",
        "src/infrastructure/backend/arch_backend_app.py",
    }
)

# Allowed import-target roles per source role.
# Intra-package imports (a file importing a sibling/child in the same package) are
# always permitted and are represented by including the package's own role.
_ALLOWED: dict[str, frozenset[str]] = {
    "domain": frozenset({"domain"}),
    "application": frozenset({"domain", "application"}),
    "config": frozenset({"config", "domain"}),
    "ontologies": frozenset({"domain", "ontologies"}),
    "diagram_types": frozenset({"domain", "infrastructure", "diagram_types"}),
    "infrastructure": frozenset(
        {"application", "domain", "ontologies", "diagram_types", "config", "infrastructure"}
    ),
    "composition": frozenset(
        {
            "domain",
            "application",
            "config",
            "ontologies",
            "diagram_types",
            "infrastructure",
            "composition",
        }
    ),
}


def _file_role(rel_path: str) -> str:
    if rel_path in _COMPOSITION_ROOTS:
        return "composition"
    parts = Path(rel_path).parts
    if len(parts) < 2 or parts[0] != "src":
        return "unknown"
    return parts[1]  # 'domain', 'application', 'config', …


def _import_role(module: str) -> str | None:
    """Return the src-package role of an imported module, or None for stdlib/third-party."""
    if not module.startswith("src."):
        return None
    parts = module.split(".", 2)
    return parts[1] if len(parts) >= 2 else None


def _collect_imports(tree: ast.AST) -> list[str]:
    """Return deduplicated list of imported module names, including lazy ones."""
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            seen.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                seen.add(alias.name)
    return sorted(seen)


def _mutation_boundary_violations(rel: str, tree: ast.AST) -> list[str]:
    violations: list[str] = []
    imports_adapter = any(
        module == _MUTATION_ADAPTER or module.startswith(f"{_MUTATION_ADAPTER}.")
        for module in _collect_imports(tree)
    )
    if imports_adapter and rel not in _MUTATION_ADAPTER_IMPORTERS:
        violations.append(f"{rel}::unauthorized-mutation-adapter-import")
    if rel.startswith("src/infrastructure/write/") or rel == "src/infrastructure/git/enterprise_git_ops.py":
        for node in ast.walk(tree):
            if _is_direct_subprocess_git_call(node):
                violations.append(f"{rel}:{getattr(node, 'lineno', 0)}::direct-subprocess-git")
    return violations


def _is_direct_subprocess_git_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr not in {"run", "call", "check_call", "check_output", "Popen"}:
        return False
    owner = node.func.value
    if not isinstance(owner, ast.Name) or owner.id != "subprocess" or not node.args:
        return False
    command = node.args[0]
    return (
        isinstance(command, (ast.List, ast.Tuple))
        and bool(command.elts)
        and isinstance(command.elts[0], ast.Constant)
        and command.elts[0].value == "git"
    )


def _load_baseline() -> set[str]:
    if not _BASELINE_PATH.exists():
        return set()
    return set(json.loads(_BASELINE_PATH.read_text()))


def test_dependency_policy() -> None:
    baseline = _load_baseline()
    new_violations: list[str] = []

    for py_file in sorted(_SRC_ROOT.rglob("*.py")):
        rel = py_file.relative_to(_PROJECT_ROOT).as_posix()
        source_role = _file_role(rel)
        if source_role == "unknown":
            continue
        allowed = _ALLOWED.get(source_role, frozenset())

        try:
            tree = ast.parse(py_file.read_text(), filename=str(py_file))
        except SyntaxError:
            continue

        new_violations.extend(_mutation_boundary_violations(rel, tree))
        for module in _collect_imports(tree):
            target_role = _import_role(module)
            if target_role is None:
                continue  # stdlib or third-party — always allowed
            if target_role not in allowed:
                key = f"{rel}::{module}"
                if key not in baseline:
                    new_violations.append(key)

    if new_violations:
        formatted = "\n".join(f"  {v}" for v in sorted(new_violations))
        raise AssertionError(
            f"New dependency-policy violations (add to baseline to acknowledge):\n{formatted}"
        )


def test_mutation_boundary_fixture_detects_bypass() -> None:
    tree = ast.parse(
        "import subprocess\n"
        "from src.infrastructure.mutation_adapters import run_git\n"
        "subprocess.run(['git', 'commit'])\n"
    )

    violations = _mutation_boundary_violations(
        "src/infrastructure/write/unreviewed_bypass.py",
        tree,
    )

    assert violations == [
        "src/infrastructure/write/unreviewed_bypass.py::unauthorized-mutation-adapter-import",
        "src/infrastructure/write/unreviewed_bypass.py:3::direct-subprocess-git",
    ]
