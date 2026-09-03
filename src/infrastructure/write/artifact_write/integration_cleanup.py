"""Binding the integration sweep to real repositories, and telling the index what it changed.

`integration_sweep` decides which submitted changes the enterprise artifact already carries. It takes
the two capabilities it cannot have — reading an enterprise artifact and writing a proposal's state —
as injected functions, so the decision is testable against records rather than against a repository
on disk. This is where those two are supplied.

The sweep spans both mounts: the proposals live in the engagement repository and their targets in the
enterprise one. So it reads through the combined index rather than either root, which is also what
makes `proposes-change-to` resolvable at all.

**Every closed proposal is broadcast.** A state written straight to disk leaves every cached index
for that repository holding the old value, and the next read reports a change as still submitted after
it was closed. `notify_paths_changed` is the one call that reaches every live index whose mounts
overlap the path, which `tests/architecture/test_index_broadcast_policy.py` exists to enforce.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.application.artifacts.query import ArtifactRepository
from src.application.modeling.integration_sweep import SweepReport, sweep_integrated_changes
from src.application.modeling.proposed_change import PROPOSED_CHANGE_TYPE
from src.domain.ontology_representation.artifact_types import DocumentRecord, EntityRecord
from src.infrastructure.artifact_index import notify_paths_changed
from src.infrastructure.write.artifact_write.proposal_lifecycle import (
    ProposalTransitionRefused,
    mark_proposal_state,
)

logger = logging.getLogger(__name__)


def close_integrated_changes(repo: ArtifactRepository) -> SweepReport:
    """Close every submitted change the enterprise repository already carries.

    Safe to call repeatedly: the state write is idempotent and answers False for a proposal already
    closed, so a pass that finds nothing new touches no file and broadcasts nothing.
    """
    closed_paths: list[Path] = []

    def target_of(artifact_id: str) -> EntityRecord | DocumentRecord | None:
        return repo.get_entity(artifact_id) or repo.get_document(artifact_id)

    def close(proposal: EntityRecord) -> bool:
        try:
            changed = mark_proposal_state(
                proposal.path, artifact_id=proposal.artifact_id, state="integrated"
            )
        except (ProposalTransitionRefused, OSError):
            # One unwritable proposal must not stop the others being closed; it stays submitted,
            # which is the safe direction, and the exception says why.
            logger.exception("Could not close integrated change %s", proposal.artifact_id)
            return False
        if changed:
            closed_paths.append(proposal.path)
        return changed

    report = sweep_integrated_changes(
        repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE), target_of=target_of, close=close
    )
    if closed_paths:
        notify_paths_changed(closed_paths)
        logger.info("Integration sweep: %s", report.summary())
    return report
