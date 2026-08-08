"""The backend serves from exactly one process, and its concurrency controls assume that.

`WorkspaceMutationGate`, the write queues, the verification pass admission and the index lock are
all process-global. Under `workers=N` uvicorn forks N processes, each with its own copy of every one
of them — so the gate would guard nothing across processes, two passes would run believing
themselves the only one, and the failure would show as intermittent corruption rather than as an
error. Nothing prevents that today except the absence of the argument, which is exactly the kind of
absence that a later change removes without noticing.
"""

from __future__ import annotations

import ast
from pathlib import Path

_SERVER = Path(__file__).resolve().parents[2] / "src/infrastructure/backend/arch_backend.py"


def test_the_uvicorn_configuration_never_asks_for_more_than_one_worker() -> None:
    tree = ast.parse(_SERVER.read_text(encoding="utf-8"))
    configured = [
        keyword.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "Config"
        for keyword in node.keywords
    ]

    assert configured, "no uvicorn.Config call found — this test is watching the wrong place"
    assert "workers" not in configured, (
        "uvicorn.Config gained a `workers` argument. Every concurrency control in this backend is "
        "process-global; forking makes each fork guard only itself."
    )
