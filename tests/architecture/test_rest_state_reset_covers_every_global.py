"""The between-test reset of `state.py` names every global that module actually has.

`tests/support/rest_state.py` lives outside `state.py`, so its list of global names is a second place
to keep in step — the exact drift this suite refuses everywhere else. This holds the two equal, so a
global added to `state.py` and not to the reset fails here rather than leaking into whichever test
runs next on the same xdist worker.

Read from the module's own annotations rather than from a hand-kept list: `state.py` declares its
state as annotated module-level assignments, which is a fact about the source and not a convention
this test invents.
"""

from __future__ import annotations

import ast

from tests.support.rest_state import INITIAL_STATE
from tests.support.source_paths import REST_ROUTERS

_STATE_MODULE = REST_ROUTERS / "state.py"

#: Module-level names that are not server state: the lock guarding it, and the constants beside it.
_NOT_STATE = frozenset({"_state_lock"})


def _module_private_globals() -> set[str]:
    """Underscore-prefixed module-level assignments — how `state.py` spells its state."""
    tree = ast.parse(_STATE_MODULE.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in tree.body:
        targets = (
            [node.target] if isinstance(node, ast.AnnAssign) else getattr(node, "targets", [])
        )
        for target in targets:
            if isinstance(target, ast.Name) and target.id.startswith("_"):
                found.add(target.id)
    return found - _NOT_STATE


def test_the_scan_reads_the_module_it_means_to() -> None:
    # Without this, a parse that stopped finding names would report a complete reset.
    names = _module_private_globals()
    assert "_repo" in names, sorted(names)
    assert "_admin_mode" in names, sorted(names)


def test_the_reset_names_every_global_the_module_declares() -> None:
    declared = _module_private_globals()
    missing = sorted(declared - set(INITIAL_STATE))
    assert missing == [], (
        "these `state.py` globals are not reset between tests, so whatever a test leaves in them is "
        f"inherited by the next test on the same worker: {missing}"
    )


def test_the_reset_names_nothing_the_module_no_longer_has() -> None:
    stranded = sorted(set(INITIAL_STATE) - _module_private_globals())
    assert stranded == [], f"the reset names globals `state.py` no longer declares: {stranded}"
