"""The supply-chain gate fails closed, and audits the closures rather than a set of its own.

Three things are asserted here that no fixture over the policy alone can reach:

* **A registry that cannot answer fails the run.** A supply-chain control that passes when it could
  not check is the same confident non-answer as the audit that ran over 29 packages of the scanner's
  own environment and reported them clean.
* **A lock source the reader does not recognise is refused**, not skipped.
* **The vulnerability gate audits `shipped_closure()` and `development_closure()`** — the same two
  answers the licence gate consumes — so the two gates cannot drift onto different package sets.

The assertions over the real lockfiles state relations, never counts: the locks change whenever a
dependency does, and a test that fails for that is reporting a false regression.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from tools.supplychain import check_supply_chain, npm_lock, npm_release_evidence, python_lock
from tools.supplychain import vulnerabilities as vuln
from tools.supplychain.closures import development_closure, shipped_closure
from tools.supplychain.npm_release_evidence import PublishTimes, RegistryUnavailable, pin
from tools.supplychain.release_age import Refused, assess

_ROOT = Path(__file__).resolve().parents[2]


def _refusals(packages: tuple[object, ...]) -> list[str]:
    now = datetime.now(timezone.utc)
    return [
        f"{package}: {verdict.reason}"
        for package in packages
        if isinstance(verdict := assess(package.source, now=now, workspace=_ROOT), Refused)  # type: ignore[attr-defined]
    ]


def _offline_times() -> PublishTimes:
    """Recorded evidence only. A pin with none is a missing `--write`, not a reason to go online."""

    def refuse(name: str) -> dict[str, str]:
        raise RegistryUnavailable(
            f"{name}: no recorded publish time. Run "
            "`uv run tools/supplychain/check_supply_chain.py --ecosystem npm --write` and commit."
        )

    return PublishTimes(npm_release_evidence.recorded_times(), fetch=refuse)


def test_every_python_pin_clears_the_floor() -> None:
    assert _refusals(python_lock.locked_packages()) == []


def test_every_npm_pin_clears_the_floor_from_recorded_evidence_alone() -> None:
    """Offline on purpose: the committed evidence must cover the committed lock."""
    assert _refusals(npm_lock.locked_packages(_offline_times())) == []


def test_the_gate_fails_when_the_registry_cannot_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    def unreachable(name: str) -> dict[str, str]:
        raise RegistryUnavailable(f"{name}: connection refused")

    monkeypatch.setattr(check_supply_chain, "recorded_times", dict)
    monkeypatch.setattr(npm_release_evidence, "fetch_package_times", unreachable)
    assert check_supply_chain.main(["--ecosystem", "npm", "--check"]) == 1


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


def test_the_recorded_evidence_is_keyed_the_way_the_reader_asks_for_it() -> None:
    """The writer and the reader spell a pin once, in `pin()`; a scoped name has two `@`."""
    recorded = npm_release_evidence.recorded_times()
    assert recorded, "no committed publish times — every offline assertion above would be vacuous"
    scoped = [key for key in recorded if key.startswith("@")]
    assert scoped, "no scoped package in the evidence; the two-`@` key shape would be untested"
    name, _, version = scoped[0].rpartition("@")
    assert pin(name, version) == scoped[0]
