"""Response contracts for the FMEA projection of an analysis: the matrix, and a recorded judgement.

Derived from ``assurance_fmea_rows.matrix_rows`` and ``assurance_fmea_cells.cell_payload``, which are
what the handler serialises. Note what ``cell_payload`` does *not* emit: ``Cell.element_id`` and
``Cell.basis_digests`` are on the dataclass and absent from the wire — the element is the row's, and
each factor carries its own digest. A DTO written from the dataclass rather than from the payload
would have published two fields nothing sends.

Two vocabularies are the domain's own at type level, ``assessment_state`` and the action-priority
band. The band matters most: ``indeterminate`` is a member of it, not an absence, and the one
confusion this grid must never permit is an unrated cell reading as a low-priority one.
"""

from __future__ import annotations

from src.domain.assurance.failure_modes import AssessmentState
from src.domain.assurance.fmea_action_priority import ActionPriority
from src.infrastructure.rest.contracts.wire_shape import Closed


class FmeaFactorAssessment(Closed):
    """One recorded judgement about a factor: what was decided, by whom, and why.

    The same shape whether the judgement still applies or has been superseded by a basis that
    moved. A reader has to be able to see that someone judged this, what they judged and on what
    grounds — before deciding whether a new basis changes the answer, and equally before defending
    a band that a judgement is currently setting.
    """

    value: str
    author: str
    justification: str


class FmeaFactorView(Closed):
    """One factor's effective value, and where it came from.

    ``value`` is null when the factor has no value a reader should act on — occurrence is
    asserted-only, so it has no derived value to fall back to. ``basis_digest`` is the digest of the
    model inputs the derived value came from, published because a judgement applies only while its
    basis still holds and a caller recording one has to send the digest back.
    """

    value: str | None
    basis: str
    basis_digest: str
    #: The judgement this value is, when a person made one that still applies. Null when the value
    #: is derived: nobody asserted it, so there is no rationale to answer with.
    assessment: FmeaFactorAssessment | None
    superseded: FmeaFactorAssessment | None


class FmeaCellDismissal(Closed):
    """Who judged this cell not credible, and why.

    Both fields empty on a cell that was not dismissed. Dismissing is a judgement someone is
    accountable for — it has to be as cheap as filling the cell in, or analysts write filler to make
    the grid look finished — so it is recorded with an author and a reason and it counts as coverage.
    """

    by: str = ""
    reason: str = ""


class FmeaCellView(Closed):
    """One (element, guideword) cell.

    ``node_id`` is null for a cell no failure mode has been written against — the absence *is* the
    untouched state, and writing a node to say nothing has happened would make coverage depend on
    bookkeeping.

    ``factors`` is keyed by factor name. An open map with a closed value, deliberately: the factor set
    belongs to the FMEA vocabulary rather than to this contract.

    ``occurrence_rationale_draft`` is facts the model already knows, offered to whoever is about to
    judge. Nothing in it proposes a rank, which is why a form may pre-fill the rationale and must never
    pre-fill the value. ``occurrence_is_requested`` is false where occurrence cannot change the band,
    and the field is then not rendered at all.
    """

    guideword: str
    state: AssessmentState
    node_id: str | None
    action_priority: ActionPriority
    occurrence_is_requested: bool
    occurrence_rationale_draft: str
    next_action: str
    dismissal: FmeaCellDismissal
    factors: dict[str, FmeaFactorView]


class FmeaMatrixRow(Closed):
    """One candidate element, crossed with every guideword.

    ``element_name`` and ``element_type`` are empty when the architecture model cannot describe the
    element. The row still exists, keyed by its id — which is honest, where inventing a label for
    something nothing can describe would not be.

    ``answered_cells`` and ``unanswered_cells`` are both stated rather than one and a total: a
    dismissal counts as answered, so the split is the coverage figure and deriving it from a length
    would get it wrong. ``worst_action_priority`` is null when no cell has a failure mode at all.
    """

    element_id: str
    element_name: str
    element_type: str
    nominated_by: list[str]
    cells: list[FmeaCellView]
    answered_cells: int
    unanswered_cells: int
    worst_action_priority: ActionPriority | None


class FmeaMatrixResponse(Closed):
    """The failure-mode matrix of one analysis.

    Scoped to an analysis by construction: unscoped, this returned every failure mode in the store
    under a heading that said "all", and with two analyses it read as a single ranking. An analysis of
    another method has no matrix and answers a typed 409 rather than an empty grid that reads clean.

    ``occurrence_scale`` travels with the matrix because a recording surface has to offer the members
    of the scale and nothing else, and restating an ordinal set whose order is load-bearing in the
    client would be a second source of truth for it.
    """

    analysis_id: str
    rows: list[FmeaMatrixRow]
    count: int
    occurrence_scale: list[str]


class FmeaFactorRecordedResponse(Closed):
    """The revision a recorded judgement produced.

    ``revision`` always advances: this appends to a series rather than replacing a value, which is why
    the route is a POST. Sending the same judgement twice produces two revisions, and keeping the
    series is the point — a factor's history is the evidence that it was considered.
    """

    node_id: str
    factor: str
    value: str
    revision: int
    created_at: str
