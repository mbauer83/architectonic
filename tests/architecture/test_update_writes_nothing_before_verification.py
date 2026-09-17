"""An update verifies, rehearses and plans before it writes, and the dry run cannot reach a writing action.

The phase table is the order the update runs in, so the property "nothing changes before every check
has passed" is a property of that table: the first phase that writes comes after `planned`, and every
verification — the release's, the assets', the rehearsal's — belongs to the dry run that precedes it.
The second half is structural: the modules the dry run is composed from import nothing that can
change an installation. Asserted over the code, not by running it, so a shortcut that reached a
writing action from the dry run fails here before it can fail on someone's deployment.
"""

from __future__ import annotations

import ast
from pathlib import Path

from src.application.software_update.journal import FIRST_WRITING_PHASE, HANDOVER_PHASE, PHASE_ORDER

ROOT = Path(__file__).resolve().parents[2]

#: What the dry run is made of: reading releases, observing the installation, rehearsing, planning.
READ_ONLY_MODULES = (
    "src/application/software_update/evaluate.py",
    "src/application/software_update/plan.py",
    "src/application/software_update/plan_steps.py",
    "src/application/software_update/decisions.py",
    "src/infrastructure/software_update/github_releases.py",
    "src/infrastructure/software_update/observation.py",
    "src/infrastructure/software_update/rehearsal.py",
    "src/infrastructure/cli/_update_report.py",
)

#: What changes an installation: the phase runner, the reversal, the actions, the journal on disk.
WRITING_MODULES = (
    "src.application.software_update.apply",
    "src.application.software_update.rollback",
    "src.infrastructure.software_update.local_actions",
    "src.infrastructure.software_update.gui_bundle",
    "src.infrastructure.software_update.journal_store",
    "src.infrastructure.software_update.credentials",
    "src.infrastructure.cli._update_commit",
)


def test_the_first_writing_phase_follows_the_plan_and_the_handover_follows_the_writes() -> None:
    assert PHASE_ORDER[0] == "planned"
    assert PHASE_ORDER.index(FIRST_WRITING_PHASE) == 1
    assert PHASE_ORDER.index(HANDOVER_PHASE) > PHASE_ORDER.index(FIRST_WRITING_PHASE)
    assert PHASE_ORDER[-1] == "verified"


def test_the_observation_takes_only_the_compose_project_from_the_compose_driver() -> None:
    """The one writing module the dry run touches: `ps` and `port` to see whether a container serves, and
    the error those two raise."""
    tree = ast.parse((ROOT / "src/infrastructure/software_update/observation.py").read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "src.infrastructure.software_update.compose"
        for alias in node.names
    }
    assert imported == {"ComposeProject", "ComposeError"}


def test_the_dry_run_is_composed_from_modules_that_import_nothing_that_writes() -> None:
    offenders: list[str] = []
    for rel in READ_ONLY_MODULES:
        tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names.append(node.module)
            elif isinstance(node, ast.Import):
                names.extend(alias.name for alias in node.names)
            for name in names:
                if any(name == writer or name.startswith(f"{writer}.") for writer in WRITING_MODULES):
                    offenders.append(f"{rel} imports {name}")
    assert offenders == [], "\n".join(offenders)
