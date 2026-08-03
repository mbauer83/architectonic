"""Every gate CI runs is named in `AGENTS.md`, so "run the gates" means the same thing in both.

A gate that exists only in `.github/workflows/ci.yml` is a gate nobody runs before pushing. It is not
caught by anything else either: the local list looks complete, every command in it passes, and the
failure arrives from a machine that took ten minutes to tell you. That happened on 2026-08-03 with a
release already tagged — `npm run test:coverage` was in CI while `AGENTS.md` said `npm test`, and the
difference was the coverage thresholds. Two genuine defects were sitting behind it.

**What counts as a gate.** Anything CI runs through `uv run`, `npm run`, or `coverage report` that is
not provisioning. Provisioning is enumerated in `_SETUP` below, and the distinction is not stylistic:
`uv sync` and `arch-assurance unlock` prepare a machine, while `ruff check` and `test:coverage` render
a verdict. Only verdicts need to be reachable by hand.

**How it matches.** Each command is reduced to the token that identifies it — the npm script name, the
tool path, the module — and that token must appear somewhere in `AGENTS.md`. Flags are deliberately not
compared: CI passes `--concurrency auto` to eslint and shards pytest, and requiring the documented form
to match character for character would make the document track CI's parallelism rather than its gates.
What must not differ is *which* commands there are.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

import pytest
import yaml  # type: ignore[import-untyped]

_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _ROOT / ".github" / "workflows" / "ci.yml"
_AGENTS = _ROOT / "AGENTS.md"

#: Provisioning, not verdicts. Matched as a prefix against the reduced command.
_SETUP = (
    "uv sync",
    "uv run get-plantuml",
    "uv run arch-init",
    "uv run arch-import-guidance",
    "uv run arch-assurance",
    "uv run arch-backend",
    "npx playwright install",
    "pip install",
    "coverage combine",
    "coverage xml",
)

#: Only these three forms carry a gate. A bare shell line (`cp`, `curl`, a `for` loop) is fixture
#: setup for the e2e job; if a gate is ever added as one, it belongs behind a `uv run`/`npm run`
#: entry point anyway, which is the same rule the rest of `tools/` follows.
_GATE_PREFIXES = ("uv run ", "npm run ", "coverage report")


def _commands() -> Iterator[tuple[str, str]]:
    """`(job, command)` for every line CI runs, with shell continuations joined."""
    doc = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    for job, spec in doc["jobs"].items():
        for step in spec.get("steps", []):
            script = step.get("run")
            if not script:
                continue
            joined = script.replace("\\\n", " ")
            for line in joined.splitlines():
                stripped = re.sub(r"\s+", " ", line.strip())
                if stripped and not stripped.startswith("#"):
                    yield job, stripped


def _identifying_token(command: str) -> str | None:
    """The part of a command that says *which* gate it is, or None when it is not one.

    `${{ matrix.group }}`-style interpolation is stripped first: it parameterises a run, never
    identifies a different gate.
    """
    command = re.sub(r"\$\{\{[^}]*\}\}", "", command).strip()
    if not command.startswith(_GATE_PREFIXES):
        return None
    if command.startswith(_SETUP):
        return None
    if command.startswith("npm run "):
        return f"npm run {command.split()[2]}"
    if command.startswith("coverage report"):
        return "coverage report"
    rest = command[len("uv run "):].split()
    # `uv run python -m mod` / `uv run python path.py` / `uv run tool subcommand`
    if rest[0] == "python":
        rest = rest[1:]
        if rest and rest[0] == "-m":
            rest = rest[1:]
    if not rest:
        return None
    if rest[0] in {"ruff", "zuban"}:
        return f"{rest[0]} {rest[1]}" if len(rest) > 1 else rest[0]
    return rest[0]


@pytest.fixture(scope="module")
def gates() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for job, command in _commands():
        token = _identifying_token(command)
        if token is not None:
            found.setdefault(token, []).append(job)
    return found


def test_ci_actually_declares_gates(gates: dict[str, list[str]]) -> None:
    """The precondition: a parse that found nothing would make the next test vacuous."""
    assert len(gates) >= 10, sorted(gates)
    for expected in ("pytest", "npm run build", "zuban check"):
        assert expected in gates, sorted(gates)


def test_every_ci_gate_is_named_in_agents_md(gates: dict[str, list[str]]) -> None:
    documented = _AGENTS.read_text(encoding="utf-8")
    missing = {
        token: jobs for token, jobs in sorted(gates.items()) if token not in documented
    }
    assert missing == {}, (
        "CI runs gates that AGENTS.md does not name:\n  "
        + "\n  ".join(f"{token} (job: {', '.join(jobs)})" for token, jobs in missing.items())
        + "\n\nAdd them to the 'Quality gates' section, or move the command out of CI. A gate only in "
        "CI is a gate nobody runs before pushing, which is how a tagged release went red."
    )


def test_the_frontend_coverage_gate_is_the_documented_one(gates: dict[str, list[str]]) -> None:
    """The specific confusion that cost a release, pinned so it cannot come back.

    `npm test` and `npm run test:coverage` run the same tests; only the second applies the thresholds.
    If CI ever moves to the bare form the thresholds stop being enforced anywhere, which is worth a
    failing test rather than a silent loss of the floor.
    """
    assert "npm run test:coverage" in gates, sorted(gates)
    assert "npm run test:coverage" in _AGENTS.read_text(encoding="utf-8")
