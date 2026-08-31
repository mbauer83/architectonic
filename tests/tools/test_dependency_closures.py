"""The licence gate inventories exactly the closure `tools.supplychain.closures` calls shipped.

"Which pins ship" is one decision with more than one consumer: the licence inventory and the
notices describe that set, and the vulnerability gate audits it. While the selection lived inside
`check_licenses.collect_python`, the only way for a second consumer to have it was to copy the flags
— and a copied selection drifts without anything failing, which in a supply-chain gate means a
confident green over the wrong packages.

That is not hypothetical here. During the survey for this work, an audit taken with `--all-extras`
reported no vulnerabilities over a set that did not contain `fastapi`: it and the `/api/events`
websocket stack are declared in the `gui` dependency *group*, so an extras-only selection excludes
the only network-facing code in the product. `fastapi` is named below for that reason.

No test here asserts a package count. The lock changes whenever a dependency does, and a test that
fails because the project took an update is reporting a false regression. The invariants are the
relations between the sets.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.supplychain.closures import development_closure, shipped_closure

_ROOT = Path(__file__).resolve().parents[2]
_INVENTORY = _ROOT / "licenses" / "python.json"


def _inventoried() -> set[str]:
    document = json.loads(_INVENTORY.read_text(encoding="utf-8"))
    return {component["name"] for component in document["components"]}


def test_the_licence_inventory_covers_the_shipped_closure_exactly() -> None:
    """One decision, one owner: what the gate published is what the closure function returns."""
    shipped = set(shipped_closure().pins)
    assert shipped, "the shipped closure is empty — every assertion below would be vacuous"
    assert _inventoried() == shipped, (
        "the committed licence inventory and the shipped closure disagree:\n"
        f"  only in the inventory: {sorted(_inventoried() - shipped)}\n"
        f"  only in the closure:   {sorted(shipped - _inventoried())}\n"
        "Run `uv run python tools/licensing/check_licenses.py --ecosystem python --write` and commit."
    )


def test_the_shipped_closure_contains_the_rest_framework() -> None:
    """The regression that started this: `fastapi` is in a group, and an extras-only closure lost it."""
    assert "fastapi" in shipped_closure().pins


def test_the_development_closure_strictly_contains_the_shipped_one() -> None:
    """Two obligations, two sets. Equal sets would mean one selection had been written twice."""
    shipped = set(shipped_closure().pins)
    development = set(development_closure().pins)
    assert shipped < development


def test_both_closures_keep_their_environment_markers() -> None:
    """A scanner is handed these lines as a requirement file; stripped markers install `pywin32` on Linux."""
    for closure in (shipped_closure(), development_closure()):
        assert any(
            " ; " in line for line in closure.requirements.splitlines()
        ), f"the {closure.name} closure exported no marked requirement"


def test_neither_closure_emits_the_project_itself() -> None:
    """The editable project is not a third-party pin: no licence to inventory, no artifact to audit.

    It leaves the export as `-e .` rather than as a pin, so the assertion has to be over the
    requirement lines a consumer is handed — a parser that skips option lines would not notice it.
    """
    for closure in (shipped_closure(), development_closure()):
        editable = [
            line for line in closure.requirements.splitlines() if line.strip().startswith("-e")
        ]
        assert editable == [], f"the {closure.name} closure exports the project itself: {editable}"
        assert "architectonic" not in closure.pins, closure.name
