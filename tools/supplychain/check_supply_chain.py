#!/usr/bin/env python
"""Supply-chain gate: nothing enters a committed lock that is known to be vulnerable or too young.

    check-supply-chain --ecosystem python --check
    check-supply-chain --ecosystem npm --check

Shaped like the licence gate beside it, so "run the supply-chain gate" means the same thing in both.

**The two ecosystems get different controls, because their tooling differs — not for symmetry.**
Both are audited for known vulnerabilities. Only Python has its release-age floor checked here, and
that is the whole asymmetry: npm enforces its floor at the moment a version could enter the lock,
through `min-release-age` in `tools/gui/.npmrc`, and writes nothing into the lock to prove it. uv has
no equivalent that is safe to leave switched on — both forms of `--exclude-newer` put a moving
timestamp into the committed lock — so for Python the gate over the lock is the only place the floor
can live. It costs nothing to run: `uv.lock` records an `upload-time` on every artifact it pins, so
the check reads the committed file and asks no registry anything.

The age check reads **every** lock entry, not a closure: the shipped export omits the editable
project, and the floor needs an answer for the project's own entry rather than a hole where one would
be. The vulnerability check reads the closures, because which pins ship and which pins CI executes
are two different obligations — `tools.supplychain.closures` owns both answers.

Both fail closed. A lock source the reader does not recognise is refused rather than skipped.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.supplychain import python_lock  # noqa: E402
from tools.supplychain.emergency_exceptions import REGISTER, expired  # noqa: E402
from tools.supplychain.release_age import FLOOR, Refused, judge  # noqa: E402
from tools.supplychain.vulnerabilities import (  # noqa: E402
    AuditReport,
    audit_npm,
    audit_python_closures,
)

_ECOSYSTEMS = ("npm", "python")


def _too_young(now: datetime) -> tuple[int, list[str]]:
    """Every entry of `uv.lock`, judged against the floor and the emergency register."""
    packages = python_lock.locked_packages()
    refusals = [
        f"{package}: {verdict.reason}"
        for package in packages
        if isinstance(
            verdict := judge(package, now=now, workspace=REPO_ROOT, register=REGISTER), Refused
        )
    ]
    return len(packages), refusals


def _spent_exceptions(now: datetime) -> list[str]:
    """A spent exception admits nothing, and stays a failure until it is taken out of the register."""
    return [
        f"{entry}: this emergency exception has expired — remove it from "
        "`tools/supplychain/emergency_exceptions.py`"
        for entry in expired(REGISTER, on=now.date())
    ]


def _report(ecosystem: str, age: str, refusals: list[str], audits: tuple[AuditReport, ...]) -> int:
    problems = list(refusals) + [
        f"{report.audience}:\n{report.output}" for report in audits if not report.clean
    ]
    if problems:
        print(f"supply-chain gate FAILED ({ecosystem}):")
        for problem in problems:
            print(f"  {problem}")
        return 1
    audited = ", ".join(str(report) for report in audits)
    print(f"supply-chain gate OK ({ecosystem}): {age}{audited}")
    return 0


def _check(ecosystem: str, now: datetime) -> int:
    if ecosystem == "npm":
        return _report(ecosystem, "release age enforced at resolution by .npmrc; ", [], audit_npm())
    entries, refusals = _too_young(now)
    hours = int(FLOOR.total_seconds() // 3600)
    return _report(
        ecosystem,
        f"{entries} locked entries all at least {hours}h old; ",
        refusals + _spent_exceptions(now),
        audit_python_closures(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--ecosystem", choices=_ECOSYSTEMS, required=True)
    parser.add_argument(
        "--check", action="store_true", required=True,
        help="CI gate: fail on a known vulnerability, or on a pin under the release-age floor",
    )
    args = parser.parse_args(argv)

    try:
        return _check(args.ecosystem, datetime.now(timezone.utc))
    except python_lock.UnreadableLockEntry as unjudgeable:
        print(f"supply-chain gate FAILED ({args.ecosystem}): {unjudgeable}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
