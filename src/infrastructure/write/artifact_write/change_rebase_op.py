"""Bringing a recorded change onto the enterprise artifact as it stands now.

Staleness is the steady state of anything that waits: the enterprise branch moves while changes sit
unreviewed. A product that can only *report* staleness leaves an author with no move except to redo
the work, which is why this is an operation rather than a status.

**Three outcomes, all nameable** (`change_rebase` decides which):

* **clean** — the recorded edit still applies and still verifies, so the change is restamped against
  what it was just proven against. Its fields do not change: they are the author's intent, and the
  intent is what re-applied.
* **superseded** — the artifact already says what the change asked. Reported, never acted on: closing
  it here would be this operation deciding that a coincidence is an integration, which is the
  judgement `integration_sweep` deliberately reserves for changes that were actually submitted.
* **conflicting** — the verifier's own refusal, carried verbatim. Nothing is written.

The rehearsal happens in a throwaway worktree, so a set full of conflicts leaves the enterprise
checkout exactly as it was — and so that a replay is a real write, judged by the real verifier,
rather than a simulation of one.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from src.application.modeling.change_rebase import RehearsedRebase
from src.application.modeling.proposal_standing import PendingProposal, enterprise_revision
from src.application.modeling.proposed_change import BASE_REVISION
from src.infrastructure.write.artifact_write.rebase_rehearsal import rehearse_against, rehearsing
from src.infrastructure.write.artifact_write.rebase_replay import rehearser_for

if TYPE_CHECKING:
    from src.application.artifacts.query import ArtifactRepository

logger = logging.getLogger(__name__)


class RebaseUnavailable(RuntimeError):
    """A rebase was asked for where it cannot be attempted, with the reason an operator can act on."""


@dataclass(frozen=True, slots=True)
class RebaseReport:
    """What the rehearsal concluded, and which changes were restamped because of it."""

    rehearsed: RehearsedRebase
    restamped: tuple[str, ...]

    def summary(self) -> str:
        return f"{self.rehearsed.summary()}; {len(self.restamped)} restamped"


def rebase_changes(
    proposals: tuple[PendingProposal, ...],
    *,
    enterprise_root: Path | None,
    repo: "ArtifactRepository",
    start_point: str = "HEAD",
    restamp: bool = True,
) -> RebaseReport:
    """Rehearse `proposals` against the enterprise head, restamping the ones that still apply.

    `enterprise_root` is None on a deployment that mounts no enterprise repository, where a rebase
    cannot be attempted at all — there is nothing to re-apply against. Refused rather than reported
    as a conflict, which would blame the change for the deployment's shape.
    """
    if enterprise_root is None:
        raise RebaseUnavailable(
            "This repository does not hold the enterprise content these changes are against, so "
            "there is nothing to bring them onto. A rebase runs where both repositories are mounted."
        )
    if not proposals:
        return RebaseReport(rehearsed=RehearsedRebase(()), restamped=())

    with rehearsing(enterprise_root, start_point=start_point) as worktree, rehearser_for(worktree) as rehearser:
        rehearsed = rehearse_against(
            worktree,
            [(proposal.proposal_id, proposal.edit) for proposal in proposals],
            read_current=rehearser.read_current,
            apply_edit=rehearser.apply_edit,
        )

    if not restamp:
        return RebaseReport(rehearsed=rehearsed, restamped=())
    return RebaseReport(rehearsed=rehearsed, restamped=_restamp_clean(rehearsed, proposals, repo))


def _restamp_clean(
    rehearsed: RehearsedRebase,
    proposals: tuple[PendingProposal, ...],
    repo: "ArtifactRepository",
) -> tuple[str, ...]:
    """Record the revision each clean change has now been proven against.

    Taken from the live repository, not from the worktree: the worktree carried the replay's own
    writes, so hashing an artifact there would stamp the change against content that exists nowhere.
    """
    by_id = {proposal.proposal_id: proposal for proposal in proposals}
    restamped: list[str] = []
    for classified in rehearsed.with_outcome("clean"):
        proposal = by_id.get(classified.proposal_id)
        revision = enterprise_revision(repo, classified.target_id) if proposal is not None else None
        if proposal is None or revision is None:
            continue
        if _write_base_revision(repo, proposal.proposal_id, revision):
            restamped.append(proposal.proposal_id)
    return tuple(restamped)


def _write_base_revision(repo: "ArtifactRepository", proposal_id: str, revision: str) -> bool:
    """Through the one owner of "record a field on a change", which the lifecycle already is."""
    from src.infrastructure.write.artifact_write.proposal_lifecycle import (  # noqa: PLC0415
        record_proposal_field,
    )

    record = repo.get_entity(proposal_id)
    if record is None:
        return False
    return record_proposal_field(
        record.path, artifact_id=proposal_id, field=BASE_REVISION, value=revision
    )
