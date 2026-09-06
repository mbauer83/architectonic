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

**And the branch goes when the last change on it does.** A review branch exists to carry changes to a
reviewer; once every change it carried has been integrated there is nothing left for it to be about,
and leaving it published invites someone to review work that is already upstream. Four conditions
have to hold together, because this is a destructive git action reached from a background sweep: the
sweep closed something, *nothing* live remains anywhere, the branch is `pending` rather than
`accumulating` — abandoning an accumulating branch would destroy work nobody has submitted — and the
tree is clean. Any one of them failing leaves the branch alone, which is always the safe direction.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.application.artifacts.query import ArtifactRepository
from src.application.modeling.integration_sweep import SweepReport, sweep_integrated_changes
from src.application.modeling.proposal_standing import pending_proposals
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
        _retire_a_finished_review_branch(repo)
    return report


def _retire_a_finished_review_branch(repo: ArtifactRepository) -> str | None:
    """Take down the review branch once every change it carried has been integrated.

    Returns the branch retired, or None — which is the answer whenever any of the four conditions in
    the module docstring does not hold. Never raises into the sweep: a branch that could not be taken
    down is tidying left undone, and failing here would leave the changes it just closed looking
    unclosed to a caller reading an exception rather than the report.
    """
    from src.infrastructure.git import enterprise_branch_lifecycle, enterprise_sync_state  # noqa: PLC0415

    enterprise = next((mount.root for mount in repo.repo_mounts if mount.scope == "enterprise"), None)
    if enterprise is None:
        return None
    if any(pending_proposals(repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE)).values()):
        return None
    if not enterprise_sync_state.load(enterprise).is_pending():
        return None
    try:
        retired = enterprise_branch_lifecycle.abandon_enterprise_branch(enterprise)
    except (ValueError, RuntimeError, OSError):
        logger.exception("Could not retire the review branch after its changes were integrated")
        return None
    logger.info("Review branch retired, every change it carried is upstream: %s", retired)
    return retired
