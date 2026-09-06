"""The local changes this repository is holding, as someone looking at a list of them needs them.

A change is stored as an internal artifact addressed to an *enterprise* id, and neither of those is
something a reader can act on: they cannot open the enterprise artifact, and they never authored the
change file. So a row names the artifact the way this repository addresses it — through the reference
that stands for it — and says what the change does to it in the vocabulary of fields, not of files.

**The condition is computed, never stored.** Whether a change has gone stale is a fact about the
enterprise artifact *now*, and `proposal_standing` owns deciding it. This module asks; it does not
grow a second opinion, which is how one word comes to mean two things.

**Every change shows both values.** A row carries, per field, what the change asks for and what the
artifact says now. That is what "stale" needs in order to be actionable — otherwise an author is told
their work needs attention and nothing about what to do — and it is equally what an ordinary change
needs, because the only place an author can otherwise see their own pending values is the edit form
they would have to open.

This was at first restricted to stale changes, on the reasoning that a current change and the
artifact agree. They do not: a change's fields differ from the artifact by definition, since that is
what makes them a change. They agree only once it has been integrated, and then it is closed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from src.application.modeling.edit_field_catalogue import ArtifactKind
from src.application.modeling.edit_field_values import comparable
from src.application.modeling.integration_detection import current_values_of
from src.application.modeling.proposal_standing import (
    PendingProposal,
    enterprise_revision,
    pending_proposals,
    standing_for,
)
from src.application.modeling.proposed_change import PROPOSED_CHANGE_TYPE
from src.domain.baseline_standing import ChangeCondition, Proposed

if TYPE_CHECKING:
    from src.application.artifacts.query import ArtifactRepository


@dataclass(frozen=True, slots=True)
class FieldDivergence:
    """One field of a stale change: what it asks for, and what the artifact says now.

    Both rendered as text, because this is for reading rather than for replaying — the recorded value
    is what a replay uses and it is already stored. `None` where the value has no single line to show
    (a properties table, an attribute-type map): naming the field as diverging is still worth saying,
    and inventing a rendering for a structured value here would be a second, worse spelling of what
    the artifact view already draws properly.
    """

    field: str
    proposed: str | None
    current: str | None


@dataclass(frozen=True, slots=True)
class RecordedChange:
    """One live local change against one promoted artifact."""

    change_id: str
    target_id: str
    #: What the artifact is called. Not how this repository addresses it internally: a reference is
    #: machinery, kept out of every list and every search, and a row that published one invited a
    #: client to link it — which is how a page showing a proxy and a description written for no one
    #: got in front of a reader.
    target_name: str
    kind: ArtifactKind
    changed_fields: tuple[str, ...]
    state: str
    condition: ChangeCondition
    #: What the change asks for beside what the artifact says now, per field. Empty only where the
    #: artifact cannot be read — an engagement deployment mounting no enterprise repository.
    divergence: tuple[FieldDivergence, ...]


def recorded_changes(repo: "ArtifactRepository | None") -> tuple[RecordedChange, ...]:
    """Every live change, ordered by the artifact it changes.

    By name rather than by id, because that is the order a reader is scanning in, and by change id
    within an artifact so two changes against one artifact keep a stable order between reads.
    """
    if repo is None:
        return ()
    pending = pending_proposals(repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE))
    if not pending:
        return ()
    rows = [
        _row(
            proposal,
            _name_of(repo, target, proposal.reference_id),
            _condition_of(repo, target, pending),
            current_values_of(repo.get_entity(target) or repo.get_document(target)),
        )
        for target, proposals in pending.items()
        for proposal in proposals
    ]
    return tuple(sorted(rows, key=lambda row: (row.target_name.casefold(), row.change_id)))


def _name_of(repo: "ArtifactRepository", target: str, reference_id: str) -> str:
    """What the promoted artifact is called.

    From the artifact itself where this repository can read it, which is also the only spelling that
    is right for a document — a document's frontmatter says `title`, so a name taken from the
    reference's own fields named every promoted document by its id.

    The reference is the fallback rather than the source: an engagement deployment mounts no
    enterprise content, and there the reference is the only local record of what the artifact is
    called. Promotion copies the name onto it for exactly this.
    """
    summary = repo.summarize_artifact(target)
    if summary is not None and summary.name:
        return summary.name
    reference = repo.get_entity(reference_id)
    return reference.name if reference is not None and reference.name else target


def _condition_of(
    repo: "ArtifactRepository",
    target: str,
    pending: Mapping[str, tuple[PendingProposal, ...]],
) -> ChangeCondition:
    standing = standing_for(target, pending, revision_of=lambda t: enterprise_revision(repo, t))
    return standing.condition if isinstance(standing, Proposed) else "current"


def _divergence(
    proposal: PendingProposal,
    current: Mapping[str, Any] | None,
) -> tuple[FieldDivergence, ...]:
    """Which of the change's fields the artifact disagrees with, and what each side says.

    Compared through `comparable`, the same normalisation staleness and integration are decided by,
    so "differs" means one thing across the whole lifecycle. A field the artifact has no reading for
    is left out rather than shown as diverging from nothing, and a repository that cannot read the
    artifact at all shows none.
    """
    if current is None:
        return ()
    return tuple(
        FieldDivergence(field=field, proposed=_as_text(proposed), current=_as_text(current[field]))
        for field, proposed in sorted(proposal.edit.fields.items())
        if field in current
        and current[field] is not None
        and comparable(current[field]) != comparable(proposed)
    )


def _as_text(value: Any) -> str | None:
    """The value as one line of prose, or None where it has none to give."""
    return value if isinstance(value, str) else None


def _row(
    proposal: PendingProposal,
    name: str,
    condition: ChangeCondition,
    current: Mapping[str, Any] | None,
) -> RecordedChange:
    return RecordedChange(
        change_id=proposal.proposal_id,
        target_id=proposal.target_id,
        target_name=name,
        kind=proposal.edit.kind,
        changed_fields=proposal.changed_fields,
        state=proposal.state,
        condition=condition,
        divergence=_divergence(proposal, current),
    )
