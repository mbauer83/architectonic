"""Moving a proposed change through its own lifecycle, in place.

A proposal is stored as an internal artifact, and its state is one frontmatter field. Advancing it is
not an artifact *edit* — nothing a proposal says about the change it carries is altered, and
`proposal-state` is not in the editable vocabulary precisely because an author must not set it by
hand. So this is a narrow operation rather than a route through the general write path.

The field is rewritten in place rather than by re-rendering the file: only the YAML region is
replaced, so both fences, the body and the file's line endings survive a transition that is supposed
to change one word. That is the same treatment the repository upgrade steps give a field they re-pin,
and for the same reason — a rewrite that reformats everything makes the diff useless for review and
risks losing whatever the renderer does not know about.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml  # type: ignore[import-untyped]

from src.application.modeling.proposed_change import (
    BASE_REVISION,
    PROPOSAL_STATE,
    STATES,
    ProposalState,
)
from src.domain.repository.frontmatter import parse_frontmatter, replace_frontmatter_text

if TYPE_CHECKING:
    from src.application.artifacts.query import ArtifactRepository


class ProposalTransitionRefused(ValueError):
    """A transition that would leave the proposal describing something that did not happen."""


def mark_proposal_state(path: Path, *, artifact_id: str, state: ProposalState) -> bool:
    """Record `state` on the proposal at `path`. Returns whether the file changed."""
    if state not in STATES:
        raise ProposalTransitionRefused(f"{state!r} is not a proposal state; expected one of {', '.join(STATES)}")
    return record_proposal_field(path, artifact_id=artifact_id, field=PROPOSAL_STATE, value=state)


def record_proposal_field(path: Path, *, artifact_id: str, field: str, value: str) -> bool:
    """Record one frontmatter field on the proposal at `path`. Returns whether the file changed.

    Idempotent: a proposal already carrying the value is left byte-identical rather than rewritten,
    so a sweep that runs on every startup does not touch a file per boot — and does not make the
    enterprise repository look dirty to the next status read.

    Two fields move this way and only these two: the lifecycle state, and the base revision a rebase
    has just proven the change against. Both are facts recorded *about* a change rather than part of
    the edit it carries, which is why neither is in the editable vocabulary and why an author cannot
    set either by hand. The mechanism was written twice before it was named once.
    """
    source = path.read_text(encoding="utf-8")
    frontmatter = parse_frontmatter(source)
    if not frontmatter:
        raise ProposalTransitionRefused(f"{artifact_id} has no frontmatter to record {field!r} in")
    if frontmatter.get(field) == value:
        return False

    dumped = yaml.safe_dump({**frontmatter, field: value}, sort_keys=False)
    if not isinstance(dumped, str):
        raise TypeError("yaml.safe_dump returned non-string output")
    path.write_text(replace_frontmatter_text(source, dumped.strip()), encoding="utf-8")
    return True


def restamp_base_revision(
    repo: "ArtifactRepository", *, proposal_id: str, target_id: str
) -> bool:
    """Record what the change has now been proven against: the enterprise artifact as it stands.

    Both moments that prove a change need this, and they used to be one function and one open-coded
    sequence. A rebase re-applies it to a moved artifact; a submission replays it into the enterprise
    repository, which moves the artifact by the change's own hand — and a base left at the older
    revision then reads as staleness, sending an author to rebase what they have just submitted.

    Taken from the live repository, never from a rehearsal worktree: that carries the replay's own
    writes, so hashing there would stamp the change against content existing nowhere.
    """
    from src.application.modeling.proposal_standing import enterprise_revision  # noqa: PLC0415

    revision = enterprise_revision(repo, target_id)
    record = repo.get_entity(proposal_id)
    if revision is None or record is None:
        return False
    return record_proposal_field(
        record.path, artifact_id=proposal_id, field=BASE_REVISION, value=revision
    )


class DiscardRefused(ValueError):
    """Taking this change back would leave the branch carrying it, so nothing was changed."""


def discard_change(
    repo: "ArtifactRepository", *, artifact_id: str, enterprise_root: "Path | None"
) -> tuple["Path", bool]:
    """Take a change back, returning its file and whether the file changed.

    One operation, because there were two: REST and MCP each found the record, checked the state and
    wrote `abandoned` in their own words, so a rule added to either was absent from the other — and
    the rule below is one neither had.

    **A change on a published branch cannot be taken back on its own.** Marking it `abandoned` does
    not remove its effect from the branch a reviewer is reading, so the record would say withdrawn
    while the branch still offered the work for merging, and a later rebase could not repair it:
    the replacement carries the live set, and the withdrawn change's effect on the old branch is
    then work the set does not account for, which refuses the rebase outright.

    The remedy composes out of what already exists. Withdraw the submission — the branch goes, no
    branch is published, and the reconciliation returns its changes to `draft`, where taking one
    back is an ordinary local act.
    """
    from src.application.modeling.proposed_change import PENDING_STATES, SUBMITTED_STATE
    from src.infrastructure.git import enterprise_sync_state

    record = repo.get_entity(artifact_id)
    if record is None:
        raise DiscardRefused(f"There is no change '{artifact_id}' in this repository.")
    state = str(record.extra.get(PROPOSAL_STATE, ""))
    if state not in PENDING_STATES:
        raise DiscardRefused(
            f"'{artifact_id}' has already ended; a change that is integrated or abandoned is a "
            "record of what happened and is not changed again."
        )
    if (
        state == SUBMITTED_STATE
        and enterprise_root is not None
        and enterprise_sync_state.load(enterprise_root).is_pending()
    ):
        raise DiscardRefused(
            f"'{artifact_id}' is on a branch that has been published for review, and taking it "
            "back here would not take it off that branch. Withdraw the submission first: the "
            "branch goes, and the changes it carried return to draft."
        )
    return record.path, mark_proposal_state(record.path, artifact_id=artifact_id, state="abandoned")
