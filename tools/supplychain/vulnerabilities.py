#!/usr/bin/env python
"""Audit both closures for known vulnerabilities — the shipped one and the one CI executes.

**Two audiences, decided on the record.** The shipped closure is what a user is exposed to. The
development closure is what CI executes, which is an attack surface of its own: a compromised test
plugin runs with repository write access. A licence obligation attaches only to what you convey, so
the licence gate correctly covers the first alone. A vulnerability obligation does not have that
shape, so this gate audits both and reports them separately.

**`uv run`, never `uvx`.** A scanner run through `uvx` audits its own ephemeral environment: the
first run during this work reported no known vulnerabilities across 29 packages — pip-audit's own
dependencies — and nothing about that output looks wrong. `pip-audit` is pinned in the development
group for the same reason: a tool that enforces the supply chain belongs inside it.

**`--no-deps` is required**, or pip-audit re-resolves the requirements and dies building `lxml` in a
temporary environment. Environment markers stay intact, so the Windows-only pins are skipped rather
than installed on Linux.

**The npm threshold is `moderate`, deliberately.** `high` would keep the gate quieter, but the whole
tree is what CI executes with repository write access and it is also what builds the shipped bundle,
so the separation `--omit=dev` would draw is weaker than it looks. Measured on 2026-08-31: zero
advisories at every severity, so the stricter of the two candidates costs nothing to adopt today.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from tools.supplychain.closures import Closure, development_closure, shipped_closure

REPO_ROOT = Path(__file__).resolve().parents[2]
GUI = REPO_ROOT / "tools" / "gui"

#: Colour off, deterministically: an escape sequence in captured output is noise a reader has to
#: discount, and on a terminal it is the only difference between two runs of the same gate.
_QUIET_ENV = {"NO_COLOR": "1", "TERM": "dumb"}

#: The severity at or above which an npm advisory fails the gate. See the module docstring.
NPM_AUDIT_LEVEL = "moderate"


@dataclass(frozen=True, slots=True)
class AuditReport:
    """What one audit found, and over which set."""

    audience: str
    packages: int
    clean: bool
    output: str

    def __str__(self) -> str:
        verdict = "no known vulnerabilities" if self.clean else "VULNERABLE"
        return f"{self.audience}: {self.packages} packages — {verdict}"


def audit_python(closure: Closure) -> AuditReport:
    """Audit one Python closure. The export is written to a temporary file, never redirected by a shell."""
    with tempfile.TemporaryDirectory() as workspace:
        requirements = Path(workspace) / "requirements.txt"
        requirements.write_text(closure.requirements, encoding="utf-8")
        done = subprocess.run(
            ["uv", "run", "pip-audit", "-r", str(requirements), "--no-deps", "--strict"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=False,
            env={**os.environ, **_QUIET_ENV},
        )
    return AuditReport(
        audience=f"python/{closure.name}",
        packages=len(closure.pins),
        clean=done.returncode == 0,
        output=(done.stdout + done.stderr).strip(),
    )


def audit_python_closures() -> tuple[AuditReport, ...]:
    return audit_python(shipped_closure()), audit_python(development_closure())


def audit_npm() -> tuple[AuditReport, ...]:
    """Audit the npm tree. One run: the shipped bundle is built by the tree that surrounds it."""
    done = subprocess.run(
        ["npm", "audit", f"--audit-level={NPM_AUDIT_LEVEL}"],
        cwd=GUI, capture_output=True, text=True, check=False,
        env={**os.environ, **_QUIET_ENV},
    )
    return (
        AuditReport(
            audience="npm/installed tree",
            packages=_locked_entries(),
            clean=done.returncode == 0,
            output=(done.stdout + done.stderr).strip(),
        ),
    )


def _locked_entries() -> int:
    document = json.loads((GUI / "package-lock.json").read_text(encoding="utf-8"))
    return sum(1 for location in document.get("packages", {}) if location)
