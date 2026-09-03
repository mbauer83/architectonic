"""What a starting backend settles before it serves.

Three records can outlive the process that wrote them: a durable write transaction, a submission
prepared before a push, and a proposed change a reviewer has since applied. Each was written before
something irreversible, and each has to be resolved before anything reports a status — otherwise the
first served request answers from state that was true when a previous process died.

**None of them may prevent the backend from starting.** Two reach the network or the filesystem, and
a workspace whose origin is unreachable, or whose one proposal is unwritable, still has a repository
worth serving. So each is caught and logged, and only an actual change is reported at warning: a
startup that says "nothing in flight" on every boot is noise that hides the one time it matters.

Extracted from `arch_backend` when the second and third arrived. The entry point's job is the order
these run in — which is load-bearing and documented there — not how each one works.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.application.artifacts.query import ArtifactRepository

logger = logging.getLogger(__name__)


def settle_submissions_in_flight(enterprise_root: Path | None) -> None:
    """Settle a submission a previous process left in flight, beside the transaction recovery.

    A prepared submission is the same kind of durable record: written before an irreversible action,
    and needing to be settled before anything reports a status. It reaches the network, so **it may
    never prevent the backend from starting** — an unreachable remote leaves the record untouched and
    logs, which is also what the reconciliation itself concludes rather than guessing.
    """
    if enterprise_root is None:
        return
    from src.infrastructure.git.submission_saga import reconcile_submission  # noqa: PLC0415

    try:
        outcome = reconcile_submission(enterprise_root)
    except Exception:  # noqa: BLE001 — startup must survive any submission-state fault
        logger.exception("Could not reconcile the submission state in %s; continuing startup", enterprise_root)
        return
    if outcome.advanced:
        logger.warning("Submission reconciliation on startup: %s", outcome.summary)


def close_changes_already_integrated(repo: ArtifactRepository) -> None:
    """Close proposed changes the enterprise repository already carries.

    After the repository is built, because the sweep spans both mounts: the proposals are in the
    engagement repository and their targets in the enterprise one. Before the duplicate scans, so a
    served request never sees a change reported as pending against an artifact that already carries
    it.

    Like the submission reconciliation above, it may never prevent the backend from starting — it
    reads and writes files, and a fault in one proposal is not a reason to refuse to serve the rest
    of the repository.
    """
    from src.infrastructure.write.artifact_write.integration_cleanup import (  # noqa: PLC0415
        close_integrated_changes,
    )

    try:
        report = close_integrated_changes(repo)
    except Exception:  # noqa: BLE001 — startup must survive any sweep fault
        logger.exception("Could not sweep integrated changes; continuing startup")
        return
    if report.changed_anything:
        logger.info("Integration sweep on startup: %s", report.summary())
