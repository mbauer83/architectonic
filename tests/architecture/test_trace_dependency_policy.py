"""Dependency contract for the motivation-coverage trace mechanism: a pure motivation trace
depends ONLY on model/graph state, never on assurance/security/signal/lock state. This is what
lets the memo key be trace-inputs-only — a lock/unlock or a signal-run activation must
never invalidate or influence a trace. Enforced structurally so it cannot regress silently."""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

_TRACE_MODULES = (
    "src/domain/viewpoints/viewpoint_trace_patterns.py",
    "src/domain/viewpoints/viewpoint_trace_pattern_parsing.py",
    "src/domain/viewpoints/viewpoint_trace_pattern_serialization.py",
    "src/domain/viewpoints/viewpoint_trace_pattern_validation.py",
    "src/domain/viewpoints/viewpoint_trace_result.py",
    "src/domain/viewpoints/viewpoint_set_parameters.py",
    "src/application/viewpoints/trace_index.py",
    "src/application/viewpoints/trace_obligations.py",
    "src/application/viewpoints/trace_evaluator.py",
    "src/application/viewpoints/trace_realizers.py",
    "src/application/viewpoints/trace_pipeline.py",
)

# Substrings that, in an imported module path, betray a dependency on confidential/assurance
# state. ``ports`` (which also declares the signal capability) is imported by module PATH, so
# these path substrings never false-positive on the legitimate RepositoryReadAccess import.
_FORBIDDEN_PATH_SUBSTRINGS = ("assurance", "security", "signal", "confidential", "sqlcipher", "_lock")


def _imported_modules(source: str) -> set[str]:
    tree = ast.parse(source)
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_trace_modules_import_no_assurance_or_signal_state() -> None:
    offenders: dict[str, set[str]] = {}
    for rel in _TRACE_MODULES:
        imports = _imported_modules((_ROOT / rel).read_text(encoding="utf-8"))
        bad = {m for m in imports if any(sub in m.lower() for sub in _FORBIDDEN_PATH_SUBSTRINGS)}
        if bad:
            offenders[rel] = bad
    assert offenders == {}, f"trace modules must not depend on assurance/signal/lock state: {offenders}"


def test_every_declared_trace_module_exists() -> None:
    missing = [rel for rel in _TRACE_MODULES if not (_ROOT / rel).is_file()]
    assert missing == [], f"stale trace-module list — these no longer exist: {missing}"
