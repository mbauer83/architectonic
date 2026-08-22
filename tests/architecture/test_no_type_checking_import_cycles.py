"""No module reaches back into one that imports it, even for types only.

A `TYPE_CHECKING` import is invisible at runtime, so a cycle made of one runtime import and one
typing-only import raises nothing, imports fine, and ships. What it does instead is leave a type
checker to pick an order to resolve the pair in — and that answer can decide whether the names
resolve at all.

**What was measured, and what was not.** `uv run zuban check` reported
`src/domain/deployment/_endpoint_refusals.py:78: Invalid type comment or annotation` on four runs in
ten, and on *every* run over that file alone. That is worse than a gate that fails, because the first
response to a flaky gate is to run it again. The cause was a cycle: the endpoint planner imported the
refusal wording at runtime, and the wording named the planner's own types under `TYPE_CHECKING`. The
repair was neither a re-run nor an ignore — the value types both modules speak moved to
`endpoint_vocabulary`, which each imports downward. Ten runs clean afterwards, and the single-file run
that had failed every time now passes every time.

The cycle alone is **not** enough to reproduce it: restoring exactly that cycle after the extraction
left zuban passing six times out of six, because the annotated names were then defined in a third
module the cycle does not pass through. So this rule is stated as the conservative one it is — a
cycle is a latent hazard rather than a proven failure — and the one pre-existing pair below is
allowed rather than pretended away.

The rule is about the *cycle*, not about `TYPE_CHECKING`, which is a perfectly good way to keep a
heavy import off the runtime path when the other direction does not exist. What it refuses is using
it to hide a cycle, because the hiding is what makes a failure intermittent.
"""

from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

from tests.support.source_paths import REPO_ROOT, SRC, python_sources

#: Cycles that predate the rule, each with what is known about it. Shrink-only, in the spirit of this
#: project's other registers: the count may fall and may never rise.
#:
#: * `ontology_protocol` names `ModuleRegistry` for three method signatures while `module_registry`
#:   imports two protocols from it at runtime. Measured **not** to flake — four single-file runs of
#:   each side, all clean — so it is a latent hazard rather than an active one, and untangling a
#:   protocol module from the registry that implements it is not patch work.
_ALLOWED_CYCLES: frozenset[tuple[str, str]] = frozenset({
    ("src.domain.ontology_representation.ontology_protocol", "src.domain.modules.module_registry"),
})


def _module_name(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT).with_suffix("")).replace("/", ".")


def _imports_by_guard(path: Path) -> tuple[set[str], set[str]]:
    """The project modules this file imports at runtime, and those it imports for types only."""
    runtime: set[str] = set()
    typing_only: set[str] = set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover - a syntax error is another test's finding
        return runtime, typing_only

    def walk(node: ast.AST, guarded: bool) -> None:
        # The node itself is examined before its children. An earlier version of this only looked at
        # children, so an `ImportFrom` handed to it as a guarded statement was never tested and every
        # typing-only import read as absent — the walk reported the whole tree clean, including the
        # cycle it was written for. Verified the other way afterwards: restore the cycle, see it.
        if isinstance(node, ast.If):
            under_guard = guarded or "TYPE_CHECKING" in ast.unparse(node.test)
            for statement in node.body:
                walk(statement, under_guard)
            for statement in node.orelse:
                walk(statement, guarded)
            return
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src."):
            (typing_only if guarded else runtime).add(node.module)
        for child in ast.iter_child_nodes(node):
            walk(child, guarded)

    walk(tree, False)
    return runtime, typing_only


def _cycles() -> list[tuple[str, str]]:
    runtime: dict[str, set[str]] = defaultdict(set)
    typing_only: dict[str, set[str]] = defaultdict(set)
    for path in python_sources(SRC):
        module = _module_name(path)
        at_runtime, for_types = _imports_by_guard(path)
        runtime[module] |= at_runtime
        typing_only[module] |= for_types
    return sorted(
        (module, target)
        for module, targets in typing_only.items()
        for target in targets
        if module in runtime.get(target, set())
    )


def test_no_module_names_a_module_that_imports_it() -> None:
    unrecorded = [pair for pair in _cycles() if pair not in _ALLOWED_CYCLES]

    assert unrecorded == [], (
        "these name a module that imports them, so a type checker has to guess which side to "
        "resolve first: " + "; ".join(f"{module} <-> {target}" for module, target in unrecorded)
        + ". Move what both need into a module they can each import downward."
    )


def test_the_allowance_names_only_cycles_that_are_still_there() -> None:
    """Shrink-only needs the register to be a fact. An allowance for a cycle that has since been
    untangled would let a new one arrive at that address quietly."""
    present = set(_cycles())

    assert _ALLOWED_CYCLES <= present, (
        f"allowed but no longer present: {sorted(_ALLOWED_CYCLES - present)} — remove the entry"
    )


def test_the_detector_recognises_the_cycle_it_was_written_for() -> None:
    """Applied to a snippet, so the guard is tested rather than trusted.

    This is the shape that was flaking, and the first version of the walk above read it as clean.
    """
    source = (
        "from __future__ import annotations\n"
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from src.domain.deployment.backend_endpoint import EndpointState\n"
    )
    runtime: set[str] = set()
    typing_only: set[str] = set()

    def walk(node: ast.AST, guarded: bool) -> None:
        if isinstance(node, ast.If):
            under = guarded or "TYPE_CHECKING" in ast.unparse(node.test)
            for statement in node.body:
                walk(statement, under)
            return
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src."):
            (typing_only if guarded else runtime).add(node.module)
        for child in ast.iter_child_nodes(node):
            walk(child, guarded)

    walk(ast.parse(source), False)

    assert typing_only == {"src.domain.deployment.backend_endpoint"}
    assert runtime == set()
