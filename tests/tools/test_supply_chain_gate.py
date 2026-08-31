"""The supply-chain gate fails closed, and audits the closures rather than a set of its own.

Three things are asserted here that no fixture over the policy alone can reach:

* **A lock source the reader does not recognise is refused**, not skipped. A gate that passes what it
  does not understand is the same confident non-answer as an audit run against the wrong environment.
* **The vulnerability gate audits `shipped_closure()` and `development_closure()`** — the same two
  answers the licence gate consumes — so the two gates cannot drift onto different package sets.
* **The npm floor and the Python floor state one number.** npm enforces its own at resolution time and
  writes nothing into the lock to prove it, so the two spellings can only be held together here.

The assertions over the real lockfile state relations, never counts: the lock changes whenever a
dependency does, and a test that fails for that is reporting a false regression.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools.supplychain import python_lock
from tools.supplychain import vulnerabilities as vuln
from tools.supplychain.closures import development_closure, shipped_closure
from tools.supplychain.release_age import FLOOR, Refused, assess

_ROOT = Path(__file__).resolve().parents[2]


def test_every_python_pin_clears_the_floor() -> None:
    now = datetime.now(timezone.utc)
    refused = [
        f"{package}: {verdict.reason}"
        for package in python_lock.locked_packages()
        if isinstance(verdict := assess(package.source, now=now, workspace=_ROOT), Refused)
    ]
    assert refused == []


def test_an_unrecognised_lock_source_is_refused_rather_than_skipped() -> None:
    with pytest.raises(python_lock.UnreadableLockEntry):
        python_lock._source_of({"name": "invented", "source": {"quantum": "?"}})


def test_the_vulnerability_gate_audits_exactly_the_two_closures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    audited: list[object] = []

    def record(closure: object) -> vuln.AuditReport:
        audited.append(closure)
        return vuln.AuditReport(audience=closure.name, packages=0, clean=True, output="")  # type: ignore[attr-defined]

    monkeypatch.setattr(vuln, "audit_python", record)
    vuln.audit_python_closures()

    assert [closure.name for closure in audited] == ["shipped", "development"]  # type: ignore[attr-defined]
    assert set(audited[0].pins) == set(shipped_closure().pins)  # type: ignore[attr-defined]
    assert set(audited[1].pins) == set(development_closure().pins)  # type: ignore[attr-defined]
    assert "fastapi" in audited[0].pins  # type: ignore[attr-defined]


def test_the_scanner_enforcing_the_supply_chain_is_inside_it() -> None:
    """A tool that audits the closure and is not in it resolves outside the floor at every run."""
    assert "pip-audit" in development_closure().pins


def test_the_npm_resolution_floor_states_the_same_number_as_the_python_one() -> None:
    """One floor, two mechanisms: npm counts days at resolution, the gate counts hours over the lock.

    npm enforces `min-release-age` when it builds the tree and records nothing in
    `package-lock.json`, so there is no committed evidence to check afterwards and no second gate to
    write. What can drift is the number, and this is the only place the two spellings meet.
    """
    declared = [
        line.split("=", 1)[1].strip()
        for line in (_ROOT / "tools" / "gui" / ".npmrc").read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("min-release-age")
    ]
    assert declared == [str(int(FLOOR.total_seconds() // 86400))]
