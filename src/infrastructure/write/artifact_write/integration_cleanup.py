"""Binding the integration sweep to real repositories, and telling the index what it changed.

`integration_sweep` decides which submitted changes the enterprise artifact already carries. It takes
the two capabilities it cannot have — reading an enterprise artifact and writing a proposal's state —
as injected functions, so the decision is testable against records rather than against a repository
on disk. This is where those two are supplied.

**The artifact is read from `origin/main`, never from the enterprise checkout.** The proposals live
in the engagement repository, but their targets are read through `upstream_artifacts`, which says
why: an enterprise checkout on a working branch carries this deployment's own submitted changes, so
reading the target there made every change read as integrated the moment it was submitted. Upstream
is the only reference under which "the artifact carries this" means "somebody took it up".

Reading upstream costs a checkout, so it is only paid when there is something to judge — `sweepable`
answers that from the proposals alone, and a backend start with no submitted change reads nothing.

**Every closed proposal is broadcast.** A state written straight to disk leaves every cached index
for that repository holding the old value, and the next read reports a change as still submitted after
it was closed. `notify_paths_changed` is the one call that reaches every live index whose mounts
overlap the path, which `tests/architecture/test_index_broadcast_policy.py` exists to enforce.

**And the branch goes when everything on it is upstream.** A review branch exists to carry work to a
reviewer; once upstream holds all of it there is nothing left for it to be about, and leaving it
published invites someone to review what is already merged. This is a destructive git action reached
from a background sweep, so the conditions are stated narrowly and every one of them failing leaves
the branch alone: the sweep closed something, no live change remains anywhere, the branch is
`pending` rather than `accumulating` — abandoning an accumulating branch destroys work nobody has
submitted — the tree is clean, and **the branch carries nothing upstream does not already have**.

That last condition is the one that makes it safe, and it was missing. "No change is still pending"
is not "the branch is finished": the same branch carries promotions, which are not changes and have
their own review. Retiring on the change count alone would delete promoted work that nobody had
merged, from the remote, with no way back.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from src.application.artifacts.query import ArtifactRepository
from src.application.modeling.integration_sweep import (
    SweepReport,
    sweep_integrated_changes,
    sweepable,
)
from src.application.modeling.proposal_standing import pending_proposals
from src.application.modeling.proposed_change import PROPOSED_CHANGE_TYPE
from src.domain.ontology_representation.artifact_types import EntityRecord
from src.infrastructure.artifact_index import notify_paths_changed
from src.infrastructure.write.artifact_write.proposal_lifecycle import (
    ProposalTransitionRefused,
    mark_proposal_state,
)
from src.infrastructure.write.artifact_write.upstream_artifacts import (
    UpstreamUnavailable,
    upstream_artifacts,
)

logger = logging.getLogger(__name__)


def close_integrated_changes(repo: ArtifactRepository) -> SweepReport:
    """Close every submitted change the enterprise repository already carries.

    Safe to call repeatedly: the state write is idempotent and answers False for a proposal already
    closed, so a pass that finds nothing new touches no file and broadcasts nothing.
    """
    closed_paths: list[Path] = []
    proposals = repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE)
    submitted = sweepable(proposals)
    enterprise = _enterprise_mount(repo)
    if not submitted or enterprise is None:
        return SweepReport(closed=(), left_open=())

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

    try:
        with upstream_artifacts(enterprise) as target_of:
            report = sweep_integrated_changes(submitted, target_of=target_of, close=close)
    except UpstreamUnavailable:
        # Not knowing is not evidence. Every change stays submitted, which is the direction that
        # cannot lose anybody's work, and the reason is logged rather than resolved by guessing.
        logger.warning("Could not read upstream to reconcile changes; none were closed", exc_info=True)
        return SweepReport(closed=(), left_open=())
    report, demoted_paths = _return_stranded_changes_to_draft(report, repo=repo, enterprise=enterprise)
    if closed_paths or demoted_paths:
        notify_paths_changed([*closed_paths, *demoted_paths])
        logger.info("Integration sweep: %s", report.summary())
    if closed_paths:
        _retire_a_finished_review_branch(repo)
    return report


def _return_stranded_changes_to_draft(
    report: SweepReport, *, repo: ArtifactRepository, enterprise: Path
) -> tuple[SweepReport, list[Path]]:
    """A change cannot be awaiting review when no branch is published for it to be awaiting it on.

    D6's transition, and the invariant behind it: a branch reaching `synced` must leave nothing
    `submitted`. Stated over *whether a branch is published* rather than over that one status,
    because the same stranding happens when the branch is abandoned and a new one opened — the
    repository is then `accumulating`, and the change is on a branch that no longer exists either
    way. `pending` is precisely the state in which a branch is published, so its absence is the
    condition.

    Back to `draft`, not to a terminal state. Nobody rejected the work: it is simply not in front of
    anyone any more, and the author's own edit is still the thing they meant. From `draft` they can
    revise it or submit it again, which is what makes this the self-healing direction.

    Reached only where the sweep read upstream successfully, so a change that *is* integrated has
    already been closed above and is not among the ones demoted here.
    """
    from src.infrastructure.git import enterprise_sync_state  # noqa: PLC0415

    if not report.left_open or enterprise_sync_state.load(enterprise).is_pending():
        return report, []

    demoted: list[str] = []
    paths: list[Path] = []
    for stranded in report.left_open:
        record = repo.get_entity(stranded.proposal_id)
        if record is None:
            continue
        try:
            changed = mark_proposal_state(record.path, artifact_id=record.artifact_id, state="draft")
        except (ProposalTransitionRefused, OSError):
            logger.exception("Could not return stranded change %s to draft", stranded.proposal_id)
            continue
        if changed:
            demoted.append(stranded.proposal_id)
            paths.append(record.path)
    if demoted:
        logger.warning(
            "Returned %d change(s) to draft: no branch is published for them to be awaiting review on",
            len(demoted),
        )
    return replace(report, returned_to_draft=tuple(demoted)), paths


def _enterprise_mount(repo: ArtifactRepository) -> Path | None:
    """The enterprise repository this deployment mounts, or None where it mounts none."""
    return next((mount.root for mount in repo.repo_mounts if mount.scope == "enterprise"), None)


def _retire_a_finished_review_branch(repo: ArtifactRepository) -> str | None:
    """Take down the review branch once upstream holds everything on it.

    Returns the branch retired, or None — which is the answer whenever any of the conditions in the
    module docstring does not hold. Never raises into the sweep: a branch that could not be taken
    down is tidying left undone, and failing here would leave the changes it just closed looking
    unclosed to a caller reading an exception rather than the report.
    """
    from src.infrastructure.git import enterprise_branch_lifecycle, enterprise_sync_state  # noqa: PLC0415
    from src.infrastructure.git.git_repository_state import content_is_upstream  # noqa: PLC0415

    enterprise = _enterprise_mount(repo)
    if enterprise is None:
        return None
    if any(pending_proposals(repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE)).values()):
        return None
    state = enterprise_sync_state.load(enterprise)
    if not state.is_pending() or state.branch is None:
        return None
    if not content_is_upstream(enterprise, state.branch):
        # The branch still carries something upstream does not have — promoted work, most likely,
        # which is not a change and has its own review. Deleting it from the remote because the
        # last *change* on it closed would take that with it.
        return None
    try:
        retired = enterprise_branch_lifecycle.abandon_enterprise_branch(enterprise)
    except (ValueError, RuntimeError, OSError):
        logger.exception("Could not retire the review branch after its changes were integrated")
        return None
    logger.info("Review branch retired, every change it carried is upstream: %s", retired)
    return retired
