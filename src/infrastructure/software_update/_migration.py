"""How `arch-repair upgrade --commit`'s exit and report are read, once, for every deployment kind.

The exit table is that command's (`arch_repair_upgrade._EXIT_BY_OUTCOME`): 0 applied, 3 blocked and
21 infrastructure failure both wrote nothing, 1 and 20 stopped after writing. The `--json` report,
when there is one, names the checkpoint set the run took — the one thing a rollback needs from a run
that stopped part-way.
"""

from __future__ import annotations

import json
import subprocess

from src.application.software_update.ports import MigrationIncomplete, MigrationResult

#: Exits after which nothing was written: blocked on a finding, or refused before the first write.
WROTE_NOTHING = frozenset({3, 21})


class MigrationRefused(RuntimeError):
    """The data upgrade wrote nothing and said why; the update fails without a data rollback."""


def migration_result(result: subprocess.CompletedProcess[str], *, doing: str) -> MigrationResult:
    """The outcome of a committing run; raises for every exit that is not a clean apply."""
    checkpoint_id = _checkpoint_set_id(result.stdout)
    if result.returncode == 0:
        return MigrationResult(checkpoint_set=checkpoint_id, committed=checkpoint_id is not None)
    detail = f"{doing} exited {result.returncode}: {result.stderr.strip()[-2000:]}"
    if result.returncode in WROTE_NOTHING:
        raise MigrationRefused(detail)
    raise MigrationIncomplete(detail, checkpoint_set=checkpoint_id)


def _checkpoint_set_id(stdout: str) -> str | None:
    try:
        report: object = json.loads(stdout) if stdout.strip() else {}
    except ValueError:
        return None
    checkpoint = report.get("checkpoint_set") if isinstance(report, dict) else None
    return str(checkpoint["id"]) if isinstance(checkpoint, dict) and checkpoint.get("id") else None
