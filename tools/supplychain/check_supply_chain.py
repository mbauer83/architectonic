#!/usr/bin/env python
"""Supply-chain gate: nothing enters a committed lock that is too young or known to be vulnerable.

Two controls, one entry point per ecosystem, shaped like the licence gate beside it so that "run the
supply-chain gate" means the same thing in both:

    check-supply-chain --ecosystem python --check   # CI gate: release age + known vulnerabilities
    check-supply-chain --ecosystem npm --write      # record the publish times the npm half needs

The age control reads **every** lock entry, not a closure: the shipped export omits the editable
project, and the floor has to have an answer for the project's own entry rather than a hole where
one would be. The vulnerability control reads the closures, because which pins ship and which pins
CI executes are two different obligations — `tools.supplychain.closures` owns both answers.

Both controls fail closed. An unrecognised lock source is refused rather than skipped, and a registry
that cannot say when a version was published fails the run rather than passing it.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.supplychain import npm_lock, python_lock  # noqa: E402
from tools.supplychain.emergency_exceptions import REGISTER, expired  # noqa: E402
from tools.supplychain.npm_release_evidence import (  # noqa: E402
    EVIDENCE,
    PublishTimes,
    RegistryUnavailable,
    recorded_times,
    render,
)
from tools.supplychain.release_age import (  # noqa: E402
    FLOOR,
    LockedPackage,
    Refused,
    judge,
)
from tools.supplychain.vulnerabilities import (  # noqa: E402
    AuditReport,
    audit_npm,
    audit_python_closures,
)

_ECOSYSTEMS = ("npm", "python")


def _too_young(packages: tuple[LockedPackage, ...], now: datetime) -> list[str]:
    refusals = []
    for package in packages:
        verdict = judge(package, now=now, workspace=REPO_ROOT, register=REGISTER)
        if isinstance(verdict, Refused):
            refusals.append(f"{package}: {verdict.reason}")
    return refusals


def _spent_exceptions(now: datetime) -> list[str]:
    """A spent exception admits nothing, and stays a failure until it is taken out of the register."""
    return [
        f"{entry}: this emergency exception has expired — remove it from "
        "`tools/supplychain/emergency_exceptions.py`"
        for entry in expired(REGISTER, on=now.date())
    ]


def _python_age(now: datetime) -> tuple[int, list[str]]:
    packages = python_lock.locked_packages()
    return len(packages), _too_young(packages, now)


def _npm_age(now: datetime, times: PublishTimes) -> tuple[int, list[str]]:
    packages = npm_lock.locked_packages(times)
    return len(packages), _too_young(packages, now)


def _report(ecosystem: str, entries: int, refusals: list[str], audits: tuple[AuditReport, ...]) -> int:
    problems = list(refusals) + [f"{report.audience}:\n{report.output}" for report in audits if not report.clean]
    if problems:
        print(f"supply-chain gate FAILED ({ecosystem}):")
        for problem in problems:
            print(f"  {problem}")
        return 1
    audited = ", ".join(str(report) for report in audits)
    print(
        f"supply-chain gate OK ({ecosystem}): {entries} locked entries all at least "
        f"{int(FLOOR.total_seconds() // 3600)}h old; {audited}"
    )
    return 0


def _check(ecosystem: str, now: datetime) -> int:
    if ecosystem == "python":
        entries, refusals = _python_age(now)
        return _report(ecosystem, entries, refusals + _spent_exceptions(now), audit_python_closures())
    times = PublishTimes(recorded_times())
    entries, refusals = _npm_age(now, times)
    refusals += _spent_exceptions(now)
    if times.queried:
        print(
            f"note: {len(times.queried)} pin(s) had no recorded publish time and were queried live. "
            f"Run --write and commit {EVIDENCE.relative_to(REPO_ROOT)}."
        )
    return _report(ecosystem, entries, refusals, audit_npm())


def _write(ecosystem: str) -> int:
    """Record the evidence the npm half needs. `uv.lock` carries its own, so Python has none to write."""
    if ecosystem == "python":
        print("nothing to record for python: uv.lock carries an upload-time on every locked artifact")
        return 0
    times = PublishTimes(recorded_times())
    npm_lock.locked_packages(times)
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    observed = times.observed()
    EVIDENCE.write_text(render(observed), encoding="utf-8")
    print(f"wrote {EVIDENCE.relative_to(REPO_ROOT)} ({len(observed)} publish times)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--ecosystem", choices=_ECOSYSTEMS, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="CI gate: fail on a young pin or a known vulnerability")
    mode.add_argument("--write", action="store_true", help="record the publish times the npm age check reads")
    args = parser.parse_args(argv)

    try:
        if args.write:
            return _write(args.ecosystem)
        return _check(args.ecosystem, datetime.now(timezone.utc))
    except (RegistryUnavailable, python_lock.UnreadableLockEntry) as unanswerable:
        print(f"supply-chain gate FAILED ({args.ecosystem}): {unanswerable}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
