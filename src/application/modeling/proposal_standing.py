"""Which artifacts carry local changes, and which parts of them — the read side of a proposal.

A reader of an artifact must be able to see whether what is shown is the enterprise baseline or the
baseline plus changes not yet accepted upstream. `src/domain/baseline_standing.py` is the value that
says so; this module works it out from the proposals in the repository.

**Batch-shaped, and reading no index of its own.** Proposals are few — one per pending edit against one
enterprise artifact — while a list read answers over hundreds of records. So the proposals are gathered
once per call and grouped by target, rather than each record asking. That is also why there is no
reverse map in the index for this: the index maintains one for global references at three sites (each
entity, each un-index, and the full rebuild), and a second map of the same shape earns its maintenance
cost only if a measurement says the grouping is hot. None does yet.

**`conflicting` is not decided here.** The condition vocabulary has three values, and this resolver
produces two of them: `current` when the enterprise artifact is still what the change was written
against, `stale` when it has moved. Whether a change *conflicts* is the outcome of rehearsing a rebase
in a real worktree, which is a later milestone's work — and inventing a second, cheaper meaning for the
word here is how one name comes to mean two things in one system.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeAlias

from src.application.derivation.refresh import compute_revision
from src.application.modeling.enterprise_reference import enterprise_target
from src.application.modeling.proposal_edit import ProposalEdit, UnproposableEdit, from_mapping
from src.application.modeling.proposed_change import (
    BASE_REVISION,
    PENDING_STATES,
    PROPOSAL_STATE,
    PROPOSED_CHANGE_TYPE,
    PROPOSES_CHANGE_TO,
    RECORDED_EDIT,
)
from src.domain.baseline_standing import BASELINE, BaselineStanding, ChangeCondition, Proposed

if TYPE_CHECKING:
    from src.application.artifacts.query import ArtifactRepository

from src.domain.ontology_representation.artifact_types import (
    ConnectionRecord,
    DiagramRecord,
    DocumentRecord,
    EntityRecord,
    ScratchpadNoteRecord,
    ScratchpadRecord,
)

#: What the resolver is given for one artifact's current content. `None` where the artifact cannot be
#: read — an enterprise repository that is not mounted, or a target that no longer exists. A revision
#: that cannot be taken makes staleness undecidable, which reads as `current` rather than as a guess
#: in the alarming direction: telling an author their work is stale when the evidence is missing costs
#: them a rebase they did not need.
RevisionReader = Callable[[str], str | None]

#: Every record kind a read can hand back. Only an entity can proxy an enterprise artifact, so only
#: an entity has a subject different from itself — but the others still need an answer, because a
#: search returns them beside entities and every hit carries a standing.
StandingBearer: TypeAlias = (
    EntityRecord | ConnectionRecord | DiagramRecord | DocumentRecord | ScratchpadRecord | ScratchpadNoteRecord
)


@dataclass(frozen=True, slots=True)
class PendingProposal:
    """One live change, reduced to what a reader of its target needs to know."""

    proposal_id: str
    target_id: str
    changed_fields: tuple[str, ...]
    base_revision: str
    #: Where the change is in its own lifecycle. `draft` may be revised in place; `submitted` has
    #: been put to someone and is replaced rather than edited. The decode already reads it to filter
    #: the live states, and which of the two it is decides what a further edit does.
    state: str
    #: What the change says the artifact should be. Kept rather than reduced to `changed_fields`,
    #: because a reader of the target needs the *values* to be shown their own pending work — the
    #: decode has already read them, and discarding them here only means reading the file twice.
    edit: ProposalEdit


def pending_proposals(entities: Iterable[EntityRecord]) -> Mapping[str, tuple[PendingProposal, ...]]:
    """Every live change, grouped by the enterprise artifact it is against.

    A record that does not decode — no target, no readable edit, a state outside the vocabulary — is
    left out rather than raised on. The verifier already refuses those (E145 to E149) and says exactly
    what is wrong with them; a read path that failed instead would take the whole page down over one
    malformed file, and hide every other artifact's standing behind it.
    """
    grouped: dict[str, list[PendingProposal]] = {}
    for record in entities:
        if record.artifact_type != PROPOSED_CHANGE_TYPE:
            continue
        proposal = _decode(record)
        if proposal is not None:
            grouped.setdefault(proposal.target_id, []).append(proposal)
    return {target: tuple(sorted(items, key=lambda p: p.proposal_id)) for target, items in grouped.items()}


def standing_for(
    target_id: str,
    pending: Mapping[str, tuple[PendingProposal, ...]],
    *,
    revision_of: RevisionReader,
) -> BaselineStanding:
    """How the artifact at `target_id` stands, given the live changes against it."""
    proposals = pending.get(target_id, ())
    if not proposals:
        return BASELINE
    return Proposed(
        proposal_ids=tuple(p.proposal_id for p in proposals),
        changed_fields=_union_of_changed_fields(proposals),
        base_revision=proposals[0].base_revision,
        condition=_condition(proposals, revision_of(target_id)),
    )


def _union_of_changed_fields(proposals: tuple[PendingProposal, ...]) -> tuple[str, ...]:
    """Every field any live change touches, in a stable order.

    The union rather than the first proposal's: two changes against one artifact are ordinary, and a
    reader asking which parts are local wants both answers, not whichever was written first.
    """
    return tuple(sorted({field for proposal in proposals for field in proposal.changed_fields}))


def _condition(proposals: tuple[PendingProposal, ...], current: str | None) -> ChangeCondition:
    if current is None:
        return "current"
    return "current" if all(p.base_revision == current for p in proposals) else "stale"


def _decode(record: EntityRecord) -> PendingProposal | None:
    target = record.extra.get(PROPOSES_CHANGE_TO)
    if not isinstance(target, str) or not target.strip():
        return None
    state = str(record.extra.get(PROPOSAL_STATE, ""))
    if state not in PENDING_STATES:
        return None
    edit = record.extra.get(RECORDED_EDIT)
    if not isinstance(edit, Mapping):
        return None
    try:
        recorded = from_mapping(edit)
    except (UnproposableEdit, KeyError, TypeError, ValueError):
        return None
    base = record.extra.get(BASE_REVISION)
    if not isinstance(base, str) or not base.strip():
        return None
    return PendingProposal(
        proposal_id=record.artifact_id,
        target_id=target.strip(),
        changed_fields=tuple(sorted(recorded.fields)),
        base_revision=base.strip(),
        state=state,
        edit=recorded,
    )


def standing_subject(record: StandingBearer) -> str:
    """The artifact whose standing this record shows.

    A change is proposed against an *enterprise* artifact, which an engagement repository holds as a
    reference proxying it. So a reference reports the standing of what it stands for, and everything
    else reports its own — which for an ordinary engagement entity is the baseline, since nothing can
    be proposed against it, and for an enterprise artifact read directly is its own pending changes.

    Every record kind a read can return, in one place: a search answers over five of them, and each
    serialiser working the subject out for itself is how one of them would come to disagree.
    """
    match record:
        case EntityRecord():
            return enterprise_target(record.extra) or record.artifact_id
        case _:
            return record.artifact_id


def standing_reader(repo: "ArtifactRepository | None") -> Callable[[str], BaselineStanding]:
    """A reader answering how any artifact stands, for the span of one response.

    The pending changes are gathered **once** and closed over, so an answer covering several hundred
    artifacts derives them once rather than per row. Callers hold it for one response and discard it;
    a snapshot is what a single response should be answering from.

    In application rather than beside any one transport, because REST, the MCP tools and the CLI all
    need the same answer and none of them may reach through another to get it. Staleness is decided
    against `compute_revision` — the content hash the stale-write contract already uses — so there is
    one notion of "what the artifact was" rather than a second grown for this.
    """
    if repo is None:
        return lambda _artifact_id: BASELINE
    pending = pending_proposals(repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE))
    if not pending:
        # Nothing is proposed anywhere, which is the ordinary state of a repository. Skip the
        # per-artifact revision reads entirely rather than hashing files to confirm it.
        return lambda _artifact_id: BASELINE

    return lambda artifact_id: standing_for(
        artifact_id, pending, revision_of=lambda target: enterprise_revision(repo, target)
    )


def enterprise_revision(repo: "ArtifactRepository", target_id: str) -> str | None:
    """What the enterprise artifact at `target_id` is right now, or None where it cannot be read.

    **The one answer to that question**, because two of them would be a silent bug rather than a
    disagreement anyone notices: a change records this when it is written, and the standing compares
    the recorded value against it to decide whether the change has gone stale. Computed over a
    different file at one of the two sites — the reference rather than what it stands for — and every
    change reads stale from the moment it is recorded, on a deployment that mounts the enterprise
    repository and nowhere else. Which is exactly what happened.

    None where the enterprise repository is not mounted. Staleness is then undecidable rather than
    false, and `_condition` treats it as `current` — the honest reading, since nothing has been
    observed to move.
    """
    record = repo.get_entity(target_id)
    return compute_revision(record.path) if record is not None and record.path.exists() else None


def pending_reader(repo: "ArtifactRepository | None") -> Callable[[str], tuple[PendingProposal, ...]]:
    """The live changes against any artifact, for the span of one response.

    The sibling of `standing_reader`, gathering the same pending set the same way, for the caller
    that needs the changes' *values* rather than a verdict about them — a detail read composing an
    author's own pending work over the baseline it cannot write.

    Two readers rather than one returning both, because the list surfaces want the verdict for
    hundreds of rows and would carry every recorded edit to use none of them.
    """
    if repo is None:
        return lambda _artifact_id: ()
    pending = pending_proposals(repo.list_entities(artifact_type=PROPOSED_CHANGE_TYPE))
    if not pending:
        return lambda _artifact_id: ()
    return lambda artifact_id: pending.get(artifact_id, ())


def standing_subject_by_id(repo: "ArtifactRepository", artifact_id: str) -> str:
    """`standing_subject` for a caller holding only an id.

    A summary carries no frontmatter, so whether the artifact is a reference to an enterprise one has
    to be read from the record. The lookup is an index hit, and the rule itself stays in one place —
    a caller working it out from the id alone would be the second reader this module exists to avoid.
    """
    record = repo.get_entity(artifact_id)
    return standing_subject(record) if record is not None else artifact_id
