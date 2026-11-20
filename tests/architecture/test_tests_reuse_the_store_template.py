"""A test initialises a confidential store itself only when initialisation is what it tests.

`init_store` costs ~0.3 s; the suite once called it 586 times, mostly to obtain an empty store.
`tests/support/assurance_store_template.py` initialises one per process and copies it, which is
what a test that only needs a store should use (`provision_store`, `unlocked_store_at`, or the
`unlocked_store` fixture).

The register below names every test file still allowed to call `init_store`, and why. It only
shrinks: a new caller fails here until it either uses the template or earns a row by testing
something the copy does not reproduce — the generated key, the replace of an existing store, the
sidecars or the `.gitignore` initialisation leaves.
"""

from __future__ import annotations

import ast
from pathlib import Path

_TESTS = Path(__file__).resolve().parents[1]

#: file (relative to tests/) → what about initialisation it tests.
INITIALISES_ON_PURPOSE: dict[str, str] = {
    "support/assurance_store_template.py": "the one per-process initialisation every copy is made from",
    "assurance/test_a_held_store_is_not_replaced.py": "that init refuses to replace a store held open",
    "assurance/test_a_provisioned_store_is_what_init_leaves.py": "compares a copy against a real init",
    "assurance/test_credential_scoping.py": "that init writes only its own path's accounts",
    "assurance/test_key_rotation_and_wal_safety.py": "re-initialising and rotating a store's key",
    "assurance/test_store_confinement_pragmas.py": "the pragmas init writes into a new store",
    "integration/test_assurance_wal_confidentiality.py": "the sidecars and .gitignore init leaves",
}


def _calls_init_store(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            callee = node.func
            name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", None)
            if name == "init_store":
                return True
    return False


def _callers() -> set[str]:
    return {
        path.relative_to(_TESTS).as_posix()
        for path in _TESTS.rglob("*.py")
        if _calls_init_store(path)
    }


def test_only_registered_tests_initialise_a_store() -> None:
    unregistered = sorted(_callers() - INITIALISES_ON_PURPOSE.keys())

    assert not unregistered, (
        f"{unregistered} call init_store; use tests.support.assurance_store_template "
        "(provision_store / unlocked_store_at) unless initialisation itself is under test"
    )


def test_the_register_names_no_file_that_no_longer_initialises() -> None:
    stale = sorted(INITIALISES_ON_PURPOSE.keys() - _callers())

    assert not stale, f"{stale} no longer call init_store; remove their rows"
