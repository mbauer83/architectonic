"""Drive the GUI's own client over the write surface, against a disposable repository.

`UNEXERCISED` in `tools/gui/tests/conformance/readCoverage.conformance.test.ts` held **42** repository
methods — every mutating one plus the whole admin tier — for one reason, stated there: the only backend
available was serving the dogfood repository, and each of these authors or destroys. The read half of
that harness has been green for a release; this is the other half.

**Why an orchestrator in Python rather than a vitest setup hook.** The fixture is a Python thing: it is
built by the product's own MCP write tools and served by a real `arch-backend` subprocess, and
`fixture_backend` owns the cross-process lock that keeps one at a time. Re-implementing any of that in a
`globalSetup` would be a second owner of the same constraint. So this starts the backend, hands the
harness the origin and the ids the fixture published, and runs `vitest` as a child.

**Two runs, sequentially.** `--admin-mode` is process-wide — the admin routes answer 403 without it and
one backend cannot be both — so the engagement tier and the enterprise tier get a backend each, in turn.
The lock is what makes "in turn" a fact.

Usage:

    uv run tools/quality/gui_write_walk.py              # both tiers
    uv run tools/quality/gui_write_walk.py --tier engagement
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.quality.fixture_backend import FixtureBackend, fixture_backend  # noqa: E402

GUI_ROOT = REPO_ROOT / "tools" / "gui"
#: The vitest project the conformance suites live in. Named rather than globbed so a new suite in that
#: directory is a deliberate addition to this gate rather than an accidental one.
_CONFORMANCE_CONFIG = "vitest.writeconformance.config.ts"
_SUITE = "tests/conformance/writes.conformance.test.ts"


def _handoff(backend: FixtureBackend, *, admin_mode: bool) -> str:
    """What the harness needs to know about the workspace, as JSON.

    Passed rather than discovered, unlike the read harness's seed. A read harness can ask the server
    "give me the first entity" because any entity will do; a write walk needs the *unreferenced* one to
    delete and the datatype classifier to annotate, and those are roles only the generator knows it
    assigned. Discovery would mean the harness probing for them, which is what the fixture exists to
    replace.
    """
    workspace = backend.workspace
    source, target = workspace.connected_entities
    diagram, classifier, attribute = workspace.annotated_classifier
    return json.dumps({
        "fixtureEntity": source,
        "fixtureOtherEntity": target,
        "doomedEntity": workspace.unreferenced_entity,
        "fixtureDiagram": workspace.application_diagram,
        "annotated": {"diagram": diagram, "classifier": classifier, "attribute": attribute},
        "adminMode": admin_mode,
    })


def _run_harness(backend: FixtureBackend, *, admin_mode: bool) -> int:
    tier = "enterprise (--admin-mode)" if admin_mode else "engagement"
    print(f"\n── {tier} tier: {backend.base_url} ──", flush=True)
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["npx", "vitest", "run", "--config", _CONFORMANCE_CONFIG, _SUITE],  # noqa: S607
        cwd=str(GUI_ROOT),
        check=False,
        env={
            **os.environ,
            "E2E_BASE_URL": backend.base_url,
            "ARCH_GUI_WRITE_FIXTURE": _handoff(backend, admin_mode=admin_mode),
        },
    )
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--tier", choices=("engagement", "enterprise", "both"), default="both",
        help="which tier to walk; 'both' runs them sequentially, which is the gate",
    )
    args = parser.parse_args(argv)

    failures = 0
    if args.tier in ("engagement", "both"):
        with fixture_backend() as backend:
            failures += 1 if _run_harness(backend, admin_mode=False) != 0 else 0
    if args.tier in ("enterprise", "both"):
        with fixture_backend(admin_mode=True) as backend:
            failures += 1 if _run_harness(backend, admin_mode=True) != 0 else 0

    print(f"\n{failures} tier(s) failed" if failures else "\nboth tiers answered as declared")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
